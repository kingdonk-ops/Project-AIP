"""IDENTITY-10 integration tests on real Postgres: portal sign-in end to end (in-process OIDC stub,
real JIT and session issue), audience/cookie mismatches, portal logout and CSRF, the portal idle cap
and the back-channel logout of a portal session.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.identity.invites import create_invite
from aip.modules.identity.oidc import BACKCHANNEL_LOGOUT_EVENT, KeycloakOidcClient
from aip.modules.identity.preauth_cookie import COOKIE_NAME
from aip.modules.identity.routes import (
    get_identity_settings,
    get_login_service,
    get_portal_login_service,
)
from aip.modules.identity.service import LoginService
from aip.modules.identity.sessions import IssuedSession, issue_session
from aip.platform.db.session import with_tenant

from ..conftest import FakeDirectory, StubProvider, make_settings
from .conftest import ORIGIN, cookies, new_session, su_execute, su_fetch, unsafe

PORTAL_ORIGIN = "https://portal.example.test"
PORTAL_SECRET = "test_only_portal_secret"
ME = "/api/v1/me"
DAVE_ID = UUID("00000000-0000-4000-8000-0000000da7e0")  # a kaefer-demo portal user
CLIENT = "client.a@rio.example"


@pytest.fixture(autouse=True)
def _portal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTAL_ORIGIN", PORTAL_ORIGIN)


class Stubs:
    def __init__(self) -> None:
        self.settings = make_settings(
            APP_ORIGIN=ORIGIN,
            PORTAL_ORIGIN=PORTAL_ORIGIN,
            PORTAL_OIDC_CLIENT_SECRET=PORTAL_SECRET,
        )
        self.staff = StubProvider(issuer=self.settings.issuer)
        self.portal = StubProvider(
            issuer=self.settings.issuer, client_id="aip-portal", client_secret=PORTAL_SECRET
        )

    def services(self) -> tuple[LoginService, LoginService]:
        s = self.settings
        staff = KeycloakOidcClient(
            issuer=s.issuer,
            token_endpoint=s.token_endpoint,
            jwks_uri=s.jwks_uri,
            client_id="aip-api",
            client_secret=s.oidc_client_secret.get_secret_value(),
            redirect_uri=s.redirect_uri,
            transport=httpx.MockTransport(self.staff.handler),
        )
        portal = KeycloakOidcClient(
            issuer=s.issuer,
            token_endpoint=s.token_endpoint,
            jwks_uri=s.jwks_uri,
            client_id="aip-portal",
            client_secret=PORTAL_SECRET,
            redirect_uri=s.portal_redirect_uri,
            transport=httpx.MockTransport(self.portal.handler),
        )
        return (
            LoginService(s, FakeDirectory(), staff),
            LoginService(s, FakeDirectory(), portal, audience="portal"),
        )


@pytest.fixture
def stubs(app: FastAPI) -> Stubs:
    stubs = Stubs()
    staff, portal = stubs.services()
    app.dependency_overrides[get_identity_settings] = lambda: stubs.settings
    app.dependency_overrides[get_login_service] = lambda: staff
    app.dependency_overrides[get_portal_login_service] = lambda: portal
    return stubs


@pytest.fixture
async def portal_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, client=("203.0.113.9", 1234))
    async with httpx.AsyncClient(transport=transport, base_url=PORTAL_ORIGIN) as c:
        yield c


async def _invite_sent(email: str, user_class: str = "portal") -> UUID:
    async with with_tenant(TENANT_A_ID) as conn:
        created = await create_invite(
            conn,
            tenant_id=TENANT_A_ID,
            email=email,
            user_class=user_class,  # pyright: ignore[reportArgumentType]
        )
    return created.user_id


async def _mark_sent(db: TenantDb) -> None:
    await su_execute(db, "UPDATE user_invite SET status = 'sent', sent_at = now()")


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


async def _sign_in(
    client: httpx.AsyncClient,
    provider: StubProvider,
    email: str,
    *,
    portal: bool = True,
    **claims: Any,
) -> httpx.Response:
    prefix = "/api/v1/auth/portal" if portal else "/api/v1/auth"
    start = await client.post(f"{prefix}/login/start", json={"email": email, "returnTo": "/inbox"})
    assert start.status_code == 200, start.text
    url = start.json()["redirectUrl"]
    code = provider.authorize(url, sub=str(uuid4()), **claims)
    pre = start.cookies.get(COOKIE_NAME)
    assert pre
    return await client.get(
        f"{prefix}/oidc/callback",
        params={"code": code, "state": _query(url)["state"]},
        headers={"cookie": f"{COOKIE_NAME}={pre}"},
    )


def _set_cookie_names(response: httpx.Response) -> set[str]:
    return {c.split("=", 1)[0] for c in response.headers.get_list("set-cookie")}


async def test_a_portal_user_signs_in_with_only_portal_cookies(
    db: TenantDb, stubs: Stubs, portal_client: httpx.AsyncClient
) -> None:
    user_id = await _invite_sent(CLIENT)
    await _mark_sent(db)
    r = await _sign_in(portal_client, stubs.portal, CLIENT)
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/inbox"
    names = _set_cookie_names(r)
    assert {"__Host-aip_portal_sid", "__Host-aip_portal_csrf"} <= names
    assert not names & {"__Host-aip_sid", "__Host-aip_csrf"}
    sid = r.cookies.get("__Host-aip_portal_sid")
    assert sid

    rows = await su_fetch(db, "SELECT audience, aal FROM user_session WHERE user_id = $1", user_id)
    assert rows == [("portal", 2)]
    status = await su_fetch(db, "SELECT status FROM app_user WHERE id = $1", user_id)
    assert status == [("active",)]
    invite = await su_fetch(db, "SELECT status FROM user_invite WHERE user_id = $1", user_id)
    assert invite == [("accepted",)]

    me = await portal_client.get(ME, headers={"cookie": f"__Host-aip_portal_sid={sid}"})
    assert me.status_code == 200, me.text
    assert me.json()["user"]["userClass"] == "portal"
    assert [m["membershipType"] for m in me.json()["memberships"]] == ["client"]


async def test_each_callback_refuses_the_other_class(
    db: TenantDb,
    stubs: Stubs,
    client: httpx.AsyncClient,
    portal_client: httpx.AsyncClient,
) -> None:
    portal_user = await _invite_sent(CLIENT)
    staff_user = await _invite_sent("gina@rio.example", user_class="staff")
    await _mark_sent(db)

    r = await _sign_in(client, stubs.staff, CLIENT, portal=False)
    assert (r.status_code, r.json()["code"]) == (403, "PORTAL_SIGN_IN_REQUIRED")
    r = await _sign_in(portal_client, stubs.portal, "gina@rio.example")
    assert (r.status_code, r.json()["code"]) == (403, "STAFF_SIGN_IN_REQUIRED")

    assert await su_fetch(db, "SELECT count(*) FROM user_session") == [(0,)]
    for user_id in (portal_user, staff_user):
        state = await su_fetch(
            db,
            "SELECT u.status, u.keycloak_user_id IS NULL, i.status FROM app_user u"
            " JOIN user_invite i ON i.user_id = u.id WHERE u.id = $1",
            user_id,
        )
        assert state == [("invited", True, "sent")]  # nothing linked, activated or accepted
    denied = await su_fetch(
        db,
        "SELECT detail->>'reason' FROM auth_event WHERE event_type = 'login.denied'"
        " ORDER BY occurred_at",
    )
    assert denied == [("portal_sign_in_required",), ("staff_sign_in_required",)]


async def _portal_session(user_id: UUID = DAVE_ID, kc_sid: str | None = None) -> IssuedSession:
    async with with_tenant(TENANT_A_ID) as conn:
        return await issue_session(
            conn,
            user_id=user_id,
            user_class="portal",
            aal=2,
            amr=["pwd", "otp"],
            authenticated_at=datetime.now(UTC),
            kc_sid=kc_sid,
            audience="portal",
        )


@pytest.fixture
async def dave(db: TenantDb) -> UUID:
    await su_execute(
        db,
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
        f"('{DAVE_ID}', '{TENANT_A_ID}', 'portal', 'dave@rio.example', 'Dave', 'active')",
    )
    return DAVE_ID


def _cleared(response: httpx.Response, audience: str) -> None:
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "SESSION_EXPIRED"
    infix = "_portal" if audience == "portal" else ""
    cleared = response.headers.get_list("set-cookie")
    assert all("Max-Age=0" in c for c in cleared)
    assert {c.split("=", 1)[0] for c in cleared} == {
        f"__Host-aip{infix}_sid",
        f"__Host-aip{infix}_csrf",
    }


async def test_a_session_under_the_other_audiences_cookie_is_refused(
    db: TenantDb, dave: UUID, client: httpx.AsyncClient
) -> None:
    portal = await _portal_session(dave)
    staff = await new_session(TENANT_A_ID, ALICE_ID)
    ok = await client.get(ME, headers={"cookie": f"__Host-aip_portal_sid={portal.sid}"})
    assert ok.status_code == 200, ok.text
    _cleared(await client.get(ME, headers={"cookie": f"__Host-aip_sid={portal.sid}"}), "app")
    _cleared(
        await client.get(ME, headers={"cookie": f"__Host-aip_portal_sid={staff.sid}"}), "portal"
    )
    # A portal-audience row for a staff user (never issued by identity) is refused too.
    await su_execute(
        db, f"UPDATE user_session SET audience = 'portal' WHERE id = '{staff.session_id}'"
    )
    _cleared(
        await client.get(ME, headers={"cookie": f"__Host-aip_portal_sid={staff.sid}"}), "portal"
    )


async def test_issue_session_refuses_a_mismatched_audience(dave: UUID) -> None:
    with pytest.raises(ValueError):
        async with with_tenant(TENANT_A_ID) as conn:
            await issue_session(
                conn,
                user_id=dave,
                user_class="portal",
                aal=2,
                amr=[],
                authenticated_at=datetime.now(UTC),
                kc_sid=None,
            )


async def test_portal_logout_needs_the_portal_origin_and_token(
    db: TenantDb, dave: UUID, client: httpx.AsyncClient
) -> None:
    portal = await _portal_session(dave)
    jar = f"__Host-aip_portal_sid={portal.sid}; __Host-aip_portal_csrf={portal.csrf}"
    refused = await client.post(
        "/api/v1/auth/logout", headers={"cookie": jar, "origin": PORTAL_ORIGIN}
    )
    assert (refused.status_code, refused.json()["detail"]["code"]) == (403, "CSRF_FAILED")
    wrong_origin = await client.post(
        "/api/v1/auth/logout",
        headers={"cookie": jar, "origin": ORIGIN, "x-csrf-token": portal.csrf},
    )
    assert wrong_origin.status_code == 403

    r = await client.post(
        "/api/v1/auth/logout",
        headers={"cookie": jar, "origin": PORTAL_ORIGIN, "x-csrf-token": portal.csrf},
    )
    assert r.status_code == 204, r.text
    assert _set_cookie_names(r) == {"__Host-aip_portal_sid", "__Host-aip_portal_csrf"}
    rows = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE id = $1", portal.session_id
    )
    assert rows == [("logout",)]


async def test_staff_requests_are_unchanged(client: httpx.AsyncClient) -> None:
    staff = await new_session(TENANT_A_ID, ALICE_ID)
    assert (await client.get(ME, headers=cookies(staff))).status_code == 200
    r = await client.post("/api/v1/auth/logout", headers=unsafe(staff))
    assert r.status_code == 204
    assert _set_cookie_names(r) == {"__Host-aip_sid", "__Host-aip_csrf"}


async def test_portal_idle_is_capped_at_the_tenants_staff_idle(db: TenantDb, dave: UUID) -> None:
    await su_execute(
        db,
        "INSERT INTO tenant_auth_policy (tenant_id, session_policy) VALUES "
        f'(\'{TENANT_A_ID}\', \'{{"staff": {{"idleMin": 10}}, "portal": {{"idleMin": 60}}}}\')',
    )
    portal = await _portal_session(dave)
    rows = await su_fetch(
        db, "SELECT idle_seconds FROM user_session WHERE id = $1", portal.session_id
    )
    assert rows == [(600,)]


async def test_a_portal_logout_token_ends_the_portal_session(
    db: TenantDb, dave: UUID, stubs: Stubs, client: httpx.AsyncClient
) -> None:
    portal = await _portal_session(dave, kc_sid="kc-portal-1")
    token = stubs.staff.sign(
        {
            "iss": stubs.settings.issuer,
            "aud": "aip-portal",
            "iat": int(time.time()),
            "jti": str(uuid4()),
            "events": {BACKCHANNEL_LOGOUT_EVENT: {}},
            "sid": "kc-portal-1",
        }
    )
    r = await client.post(
        "/api/v1/auth/oidc/backchannel-logout",
        content=f"logout_token={token}",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    rows = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE id = $1", portal.session_id
    )
    assert rows == [("keycloak_logout",)]
