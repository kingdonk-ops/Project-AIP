"""IDENTITY-04 against the real Keycloak (same server choice as ``test_keycloak_flows.py``).

- Brokered sign-ins carry the upstream IdP's ``amr`` as ``upstream_amr``: the kaefer mock IdP
  reports MFA (session aal 2), the acme one does not (aal 1).
- The invite journey: the ``identity.send_invite`` job creates one Keycloak user with the three
  required actions and ``aip_user_id``, Keycloak emails the link (Mailpit), the invitee verifies,
  sets a password and configures TOTP headlessly, and the first sign-in activates the user and
  accepts the invite. An admin MFA reset then removes the OTP credential.

Mailpit: ``AIP_TEST_MAILPIT_URL`` (its REST API, e.g. ``http://localhost:8025``). Without it the
journey is skipped, except in CI's compose job (``AIP_TEST_KEYCLOAK_URL`` set), where it fails.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from collections.abc import AsyncIterator
from html import unescape
from typing import Any
from urllib.parse import urljoin
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from tests.fixtures.postgres import TenantDb

from aip.modules.identity import repository as repo
from aip.modules.identity.api import JitLoginHandler, get_external_login_handler
from aip.modules.identity.invites import create_invite
from aip.modules.identity.jit import JitProvisioner
from aip.modules.identity.jobs import send_invite
from aip.modules.identity.keycloak_admin import KeycloakAdmin, KeycloakAdminSettings
from aip.modules.identity.sessions import derive_aal
from aip.modules.ops import api as ops

from .browser import Browser, Page, drive, forms
from .conftest import TENANT_A_ID
from .test_keycloak_flows import (  # noqa: F401 - module-scoped fixtures shared with IDENTITY-01
    APP_ORIGIN,
    Keycloak,
    _callback,  # pyright: ignore[reportPrivateUsage]
    _credentials,  # pyright: ignore[reportPrivateUsage]
    _login_start,  # pyright: ignore[reportPrivateUsage]
    api,
    kc_app,
    kc_settings,
    keycloak,
)
from .totp import totp

ADMIN_SECRET = os.environ.get("AIP_TEST_KEYCLOAK_ADMIN_CLIENT_SECRET", "aip_admin_dev_only_secret")
PASSWORD = "Correct-Horse-42!"
CALLBACK = f"{APP_ORIGIN}/api/v1/auth/oidc/callback"


@pytest.fixture
async def admin(keycloak: Keycloak) -> AsyncIterator[KeycloakAdmin]:  # noqa: F811
    client = KeycloakAdmin(
        KeycloakAdminSettings.model_validate(
            {"KEYCLOAK_URL": keycloak.url, "KEYCLOAK_ADMIN_CLIENT_SECRET": ADMIN_SECRET}
        )
    )
    yield client
    await client.aclose()


@pytest.fixture
def mailpit() -> str:
    url = os.environ.get("AIP_TEST_MAILPIT_URL")
    if not url:
        message = "no Mailpit: set AIP_TEST_MAILPIT_URL"
        if os.environ.get("CI") and os.environ.get("AIP_TEST_KEYCLOAK_URL"):  # the compose job
            pytest.fail(message)
        pytest.skip(message)
    return url.rstrip("/")


async def _brokered(api: httpx.AsyncClient, email: str, password: str) -> dict[str, Any]:  # noqa: F811
    b = Browser(stop_prefix=CALLBACK)
    try:
        body, cookie = await _login_start(api, email)
        first = b.get(body["redirectUrl"])
        end = first if isinstance(first, str) else drive(b, first, _credentials(email, password))
        assert isinstance(end, str), end.url if isinstance(end, Page) else end
    finally:
        b.close()
    r = await _callback(api, end, cookie)
    assert r.status_code == 200, r.text
    return r.json()


async def test_brokered_sign_ins_carry_the_upstream_amr(api: httpx.AsyncClient) -> None:  # noqa: F811
    alice = await _brokered(api, "alice@kaefer.test", "alice_dev_only_password")
    assert set(alice["upstream_amr"]) == {"pwd", "mfa"}
    assert derive_aal(alice["acr"], alice["amr"], alice["upstream_amr"]) == 2
    bob = await _brokered(api, "bob@acme.test", "bob_dev_only_password")
    assert bob["upstream_amr"] == ["pwd"]
    assert derive_aal(bob["acr"], bob["amr"], bob["upstream_amr"]) == 1


_JOB = text("SELECT * FROM jobs WHERE job_type = 'identity.send_invite' ORDER BY created_at")


async def _run_send_invite(idb: TenantDb, admin: KeycloakAdmin) -> None:
    async with idb.with_tenant(TENANT_A_ID) as conn:
        rows = (await conn.execute(_JOB)).mappings().all()
        for row in rows:
            await send_invite(conn, ops.JobView.model_validate(dict(row)), admin)


def _mail_link(mailpit: str, email: str) -> str:
    found: dict[str, Any] = {}
    for _ in range(20):
        found = httpx.get(f"{mailpit}/api/v1/search", params={"query": f"to:{email}"}).json()
        if found.get("messages"):
            break
        time.sleep(0.5)
    messages = found.get("messages") or []
    assert len(messages) == 1, messages
    assert messages[0]["Subject"] == "You have been invited to AIP"
    message = httpx.get(f"{mailpit}/api/v1/message/{messages[0]['ID']}").json()
    links = re.findall(r'href="([^"]*action-token[^"]*)"', message["HTML"])
    assert links, message["HTML"][:2000]
    return unescape(links[0])


def _proceed_link(page: Page) -> str | None:
    """Keycloak's "click here to proceed" link on its info pages."""
    for href in re.findall(r'href="([^"]+)"', page.html):
        target = unescape(href)
        if "/login-actions/" in target:
            return urljoin(page.url, target)
    return None


def _complete_actions(browser: Browser, link: str) -> bytes:
    """Follow the invite link: set the password and configure TOTP. Returns the TOTP secret."""
    current: Page | str = browser.get(link)
    secret: bytes | None = None
    for _ in range(10):
        if isinstance(current, str):
            break
        page = current
        password = page.form_with("password-new")
        setup = page.form_with("totpSecret")
        if password is not None:
            current = browser.submit(
                page, password, {"password-new": PASSWORD, "password-confirm": PASSWORD}
            )
        elif setup is not None:
            secret = setup.fields["totpSecret"].encode()
            current = browser.submit(page, setup, {"totp": totp(secret), "userLabel": "test"})
        elif not forms(page.html) and (follow := _proceed_link(page)) is not None:
            current = browser.get(follow)
        else:
            break
    assert secret is not None, "the invite never asked to configure TOTP"
    return secret


async def test_the_invite_journey(
    api: httpx.AsyncClient,  # noqa: F811
    kc_app: FastAPI,  # noqa: F811
    idb: TenantDb,
    admin: KeycloakAdmin,
    mailpit: str,
) -> None:
    email = f"carol-{secrets.token_hex(4)}@client.test"
    async with idb.with_tenant(TENANT_A_ID) as conn:
        created = await create_invite(
            conn, tenant_id=TENANT_A_ID, email=email, first_name="Carol", last_name="Client"
        )
    assert created.method == "local"

    await _run_send_invite(idb, admin)
    async with idb.with_tenant(TENANT_A_ID) as conn:
        invite = await repo.get_invite(conn, created.invite_id)
        user = await repo.get_user(conn, created.user_id)
    assert invite is not None and invite.status == "sent"
    assert user is not None and user.keycloak_user_id is not None
    kc_user = await admin.get_user(user.keycloak_user_id)
    assert sorted(kc_user["requiredActions"]) == [
        "CONFIGURE_TOTP",
        "UPDATE_PASSWORD",
        "VERIFY_EMAIL",
    ]
    assert kc_user["attributes"]["aip_user_id"] == [str(created.user_id)]
    assert kc_user["emailVerified"] is False

    link = _mail_link(mailpit, email)
    browser = Browser(stop_prefix=CALLBACK)
    try:
        secret = _complete_actions(browser, link)
    finally:
        browser.close()
    kc_user = await admin.get_user(user.keycloak_user_id)
    assert kc_user["emailVerified"] is True and not kc_user.get("requiredActions")

    assert await admin.find_user_by_email(email) == user.keycloak_user_id

    jit = JitLoginHandler(JitProvisioner(connect=idb.with_tenant, connect_pre=idb.no_tenant))
    kc_app.dependency_overrides[get_external_login_handler] = lambda: jit
    signin = Browser(stop_prefix=CALLBACK)
    try:
        body, cookie = await _login_start(api, email)
        page = drive(signin, signin.get(body["redirectUrl"]), _credentials(email, PASSWORD))
        assert isinstance(page, Page) and page.form_with("otp") is not None, "expected the OTP form"
        end = signin.submit(page, page.form_with("otp"), {"otp": totp(secret, at=time.time() + 30)})  # pyright: ignore[reportArgumentType]
        assert isinstance(end, str), end.url if isinstance(end, Page) else end
    finally:
        signin.close()
    r = await _callback(api, end, cookie)
    assert r.status_code == 200, r.text
    assert r.json()["userId"] == str(created.user_id)
    async with idb.with_tenant(TENANT_A_ID) as conn:
        user = await repo.get_user(conn, created.user_id)
        invite = await repo.get_invite(conn, created.invite_id)
    assert user is not None and user.status == "active"
    assert invite is not None and invite.status == "accepted"

    await admin.reset_mfa(UUID(str(kc_user["id"])))
    types = {c["type"] for c in await admin.credentials(kc_user["id"])}
    assert "otp" not in types and "password" in types
    assert "CONFIGURE_TOTP" in (await admin.get_user(kc_user["id"]))["requiredActions"]
