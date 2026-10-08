"""The real Keycloak: both realms, the theme and the blocklist imported (IDENTITY-01).

Keycloak, in order:

1. ``AIP_TEST_KEYCLOAK_URL`` (+ ``AIP_TEST_KEYCLOAK_ADMIN``/``AIP_TEST_KEYCLOAK_ADMIN_PASSWORD``): a
   running server that imported ``infra/keycloak`` with ``APP_ORIGIN=https://app.example.test``,
   ``KC_HOSTNAME`` = that URL and ``KEYCLOAK_PUBLIC_URL`` = that URL;
2. Testcontainers ``quay.io/keycloak/keycloak:26.7.5`` when Docker runs;
3. otherwise skipped locally and failed under CI.

The login pages are driven headlessly (``browser.py``); the app runs in process with a fixture
login directory and real OIDC client, so the code exchange and ID-token checks are the real ones.
"""

from __future__ import annotations

import os
import re
import secrets
import socket
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from keycloak import KeycloakAdmin  # pyright: ignore[reportMissingTypeStubs]
from keycloak.exceptions import KeycloakError  # pyright: ignore[reportMissingTypeStubs]
from tests.platform.db.conftest import _docker_reachable  # pyright: ignore[reportPrivateUsage]

from aip.main import create_app
from aip.modules.identity.oidc import KeycloakOidcClient
from aip.modules.identity.preauth_cookie import COOKIE_NAME, open_cookie, seal
from aip.modules.identity.routes import get_login_rate_limiter, get_login_service
from aip.modules.identity.service import LoginRateLimiter, LoginService
from aip.modules.identity.settings import IdentitySettings

from .browser import Browser, Page, drive
from .conftest import TENANT_A_ID, FakeDirectory, make_settings
from .totp import totp

ROOT = Path(__file__).resolve().parents[6]
KC_DIR = ROOT / "infra" / "keycloak"
KC_IMAGE = "quay.io/keycloak/keycloak:26.7.5"
APP_ORIGIN = "https://app.example.test"
API_SECRET = "aip_api_dev_only_secret"  # the realm file's dev default
LOCAL_PASSWORD = "Carol-dev-only-Passw0rd!"


@dataclass(frozen=True)
class Keycloak:
    url: str
    admin_user: str
    admin_password: str

    def admin(self) -> KeycloakAdmin:
        return KeycloakAdmin(
            server_url=self.url,
            username=self.admin_user,
            password=self.admin_password,
            realm_name="aip",
            user_realm_name="master",
        )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def keycloak() -> Iterator[Keycloak]:
    url = os.environ.get("AIP_TEST_KEYCLOAK_URL")
    if url:
        yield Keycloak(
            url.rstrip("/"),
            os.environ.get("AIP_TEST_KEYCLOAK_ADMIN", "admin"),
            os.environ.get("AIP_TEST_KEYCLOAK_ADMIN_PASSWORD", "admin"),
        )
        return
    if not _docker_reachable():
        message = "no Keycloak: set AIP_TEST_KEYCLOAK_URL or start a Docker daemon"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    from testcontainers.community.keycloak import (  # pyright: ignore[reportMissingTypeStubs]
        KeycloakContainer,
    )

    port = _free_port()
    public = f"http://localhost:{port}"
    password = "admin_test_only"
    container: Any = KeycloakContainer(KC_IMAGE, username="admin", password=password)
    container.with_bind_ports(8080, port)
    for key, value in {
        "KC_HOSTNAME": public,
        "KEYCLOAK_PUBLIC_URL": public,
        "KEYCLOAK_INTERNAL_URL": "http://localhost:8080",
        "APP_ORIGIN": APP_ORIGIN,
        "KC_SMTP_HOST": "localhost",
    }.items():
        container.with_env(key, value)
    imports = "/opt/keycloak/data/import"
    container.with_volume_mapping(str(KC_DIR / "realm-aip.json"), f"{imports}/realm-aip.json", "ro")
    container.with_volume_mapping(
        str(KC_DIR / "realm-mock-idp.json"), f"{imports}/realm-mock-idp.json", "ro"
    )
    container.with_volume_mapping(str(KC_DIR / "themes" / "aip"), "/opt/keycloak/themes/aip", "ro")
    container.with_volume_mapping(
        str(KC_DIR / "password-blocklist.txt"),
        "/opt/keycloak/data/password-blacklists/password-blocklist.txt",
        "ro",
    )
    container.has_realm_imports = True
    with container:
        yield Keycloak(public, "admin", password)


@pytest.fixture(scope="module")
def kc_settings(keycloak: Keycloak) -> IdentitySettings:
    return make_settings(
        KEYCLOAK_URL=keycloak.url, OIDC_CLIENT_SECRET=API_SECRET, APP_ORIGIN=APP_ORIGIN
    )


@pytest.fixture
async def kc_app(kc_settings: IdentitySettings, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("AIP_ENV", "test")
    oidc = KeycloakOidcClient(
        issuer=kc_settings.issuer,
        token_endpoint=kc_settings.token_endpoint,
        jwks_uri=kc_settings.jwks_uri,
        client_id=kc_settings.oidc_client_id,
        client_secret=API_SECRET,
        redirect_uri=kc_settings.redirect_uri,
    )
    app = create_app(env="test", tracing=False)
    service = LoginService(kc_settings, FakeDirectory(), oidc)
    limiter = LoginRateLimiter.from_redis_url(None)
    app.dependency_overrides[get_login_service] = lambda: service
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    yield app
    await oidc.aclose()


@pytest.fixture
async def api(kc_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=kc_app), base_url=APP_ORIGIN) as c:
        yield c


@pytest.fixture
def browser() -> Iterator[Browser]:
    b = Browser(stop_prefix=f"{APP_ORIGIN}/api/v1/auth/oidc/callback")
    yield b
    b.close()


async def _login_start(api: httpx.AsyncClient, email: str) -> tuple[dict[str, Any], str]:
    r = await api.post("/api/v1/auth/login/start", json={"email": email})
    assert r.status_code == 200, r.text
    cookie = r.cookies.get(COOKIE_NAME)
    assert cookie
    return r.json(), cookie


async def _callback(api: httpx.AsyncClient, callback_url: str, cookie: str) -> httpx.Response:
    api.cookies.clear()
    api.cookies.set(COOKIE_NAME, cookie)
    query = {k: v[0] for k, v in parse_qs(urlsplit(callback_url).query).items()}
    return await api.get("/api/v1/auth/oidc/callback", params=query)


def _credentials(email: str, password: str):  # noqa: ANN202 - local filler
    def fill(page: Page) -> dict[str, str] | None:
        if page.form_with("password"):
            values = {"password": password}
            form = page.form_with("password")
            assert form is not None
            if "username" in form.inputs:
                values["username"] = email
            return values
        if page.form_with("username"):
            return {"username": email}
        return None

    return fill


def _create_local_user(keycloak: Keycloak, email: str) -> str:
    admin = keycloak.admin()
    user_id = admin.create_user(  # pyright: ignore[reportUnknownMemberType]
        {"username": email, "email": email, "emailVerified": True, "enabled": True,
         "firstName": "Carol", "lastName": "Client"}
    )
    admin.set_user_password(user_id, LOCAL_PASSWORD, temporary=False)  # pyright: ignore[reportUnknownMemberType]
    return str(user_id)


def _unique(local: str) -> str:
    return f"{local}-{secrets.token_hex(4)}@client.test"


def test_openid_configuration(keycloak: Keycloak) -> None:
    r = httpx.get(f"{keycloak.url}/realms/aip/.well-known/openid-configuration", timeout=10)
    assert r.status_code == 200
    assert r.json()["issuer"] == f"{keycloak.url}/realms/aip"
    assert "S256" in r.json()["code_challenge_methods_supported"]


async def test_alice_sso_goes_straight_to_the_mock_idp(
    api: httpx.AsyncClient, browser: Browser, keycloak: Keycloak
) -> None:
    body, cookie = await _login_start(api, "alice@kaefer.test")
    assert body["method"] == "sso"
    first = browser.get(body["redirectUrl"])
    assert isinstance(first, Page)
    assert "/realms/mock-idp/" in first.url, first.url  # no aip password page in between
    end = drive(browser, first, _credentials("alice@kaefer.test", "alice_dev_only_password"))
    assert isinstance(end, str), end.url if isinstance(end, Page) else end
    assert not any(
        "/realms/aip/" in p.url and p.form_with("password") for p in browser.pages
    ), "the aip realm showed a password page"
    r = await _callback(api, end, cookie)
    assert r.status_code == 200, r.text
    identity = r.json()
    assert identity["tenant_id"] == str(TENANT_A_ID)
    assert identity["idp_alias"] == "kaefer-oidc"
    assert identity["email"] == "alice@kaefer.test"
    assert "eyJ" not in r.text and "eyJ" not in r.headers.get("set-cookie", "")


async def test_bob_with_a_kaefer_cookie_is_refused(
    api: httpx.AsyncClient, browser: Browser, kc_settings: IdentitySettings
) -> None:
    body, cookie = await _login_start(api, "bob@acme.test")
    end = drive(browser, browser.get(body["redirectUrl"]), _credentials("bob@acme.test", "bob_dev_only_password"))
    assert isinstance(end, str)
    pre = open_cookie(cookie, kc_settings.preauth_key)
    kaefer = pre.model_copy(update={"tenant_id": TENANT_A_ID, "idp_alias": "kaefer-oidc"})
    r = await _callback(api, end, seal(kaefer, kc_settings.preauth_key))
    assert r.status_code == 403
    assert r.json()["code"] == "IDP_TENANT_MISMATCH"


async def test_local_user_must_set_up_otp(
    api: httpx.AsyncClient, browser: Browser, keycloak: Keycloak
) -> None:
    email = _unique("carol")
    _create_local_user(keycloak, email)
    body, cookie = await _login_start(api, email)
    assert body["method"] == "password"
    page = drive(browser, browser.get(body["redirectUrl"]), _credentials(email, LOCAL_PASSWORD))
    assert isinstance(page, Page), "reached the callback without a second factor"
    setup = page.form_with("totpSecret")
    assert setup is not None, f"expected the OTP setup page at {page.url}"
    # The themed page: our stylesheet and a terminology label.
    assert "css/aip.css" in page.html
    secret = setup.fields["totpSecret"]
    end = browser.submit(page, setup, {"totp": totp(secret.encode()), "userLabel": "test"})
    assert isinstance(end, str), end.url if isinstance(end, Page) else end
    r = await _callback(api, end, cookie)
    assert r.status_code == 200, r.text
    identity = r.json()
    assert identity["idp_alias"] is None and identity["tenant_id"] is None
    assert identity["acr"] == "aal2"
    # Keycloak's AMR mapper lists authenticators that ran; enrolment happens in the CONFIGURE_TOTP
    # required action, so the first sign-in carries "pwd" only. The next sign-in proves "otp".
    assert "pwd" in identity["amr"]
    assert identity["kc_sid"]
    assert "eyJ" not in r.text

    again = Browser(stop_prefix=browser.stop_prefix)
    try:
        body, cookie = await _login_start(api, email)
        page = drive(again, again.get(body["redirectUrl"]), _credentials(email, LOCAL_PASSWORD))
        assert isinstance(page, Page) and page.form_with("otp") is not None, "expected the OTP form"
        # The enrolment code may not be reused: use the next 30 s step (look-around 1).
        code = totp(secret.encode(), at=time.time() + 30)
        end = again.submit(page, page.form_with("otp"), {"otp": code})  # pyright: ignore[reportArgumentType]
        assert isinstance(end, str), end.url if isinstance(end, Page) else end
    finally:
        again.close()
    r = await _callback(api, end, cookie)
    assert r.status_code == 200, r.text
    identity = r.json()
    assert identity["acr"] == "aal2"
    assert {"pwd", "otp"} <= set(identity["amr"])
    assert identity["kc_sid"]


async def test_login_page_uses_the_aip_theme(api: httpx.AsyncClient, browser: Browser) -> None:
    body, _ = await _login_start(api, _unique("theme"))
    page = browser.get(body["redirectUrl"])
    assert isinstance(page, Page)
    assert "css/aip.css" in page.html
    assert re.search(r"Sign in to AIP|Work email", page.html), page.html[:2000]


async def test_brute_force_locks_the_account(
    api: httpx.AsyncClient, browser: Browser, keycloak: Keycloak
) -> None:
    email = _unique("carol-bf")
    user_id = _create_local_user(keycloak, email)
    for attempt in range(5):
        body, _ = await _login_start(api, email)
        b = Browser(stop_prefix=browser.stop_prefix)
        try:
            end = drive(b, b.get(body["redirectUrl"]), _credentials(email, f"wrong-{attempt}-password"), max_steps=3)
            assert isinstance(end, Page)
        finally:
            b.close()
        time.sleep(1.1)  # stay outside quickLoginCheckMilliSeconds
    admin = keycloak.admin()
    status: Any = admin.connection.raw_get(  # pyright: ignore[reportUnknownMemberType]
        f"admin/realms/aip/attack-detection/brute-force/users/{user_id}"
    ).json()
    assert status["disabled"] is True, status
    body, _ = await _login_start(api, email)
    end = drive(browser, browser.get(body["redirectUrl"]), _credentials(email, LOCAL_PASSWORD), max_steps=4)
    assert isinstance(end, Page), "a locked account reached the callback"


def test_password_policy_min_length(keycloak: Keycloak) -> None:
    admin = keycloak.admin()
    email = _unique("carol-pp")
    user_id = admin.create_user({"username": email, "email": email, "enabled": True})  # pyright: ignore[reportUnknownMemberType]
    with pytest.raises(KeycloakError) as exc:
        admin.set_user_password(user_id, "short", temporary=False)  # pyright: ignore[reportUnknownMemberType]
    assert "invalidPasswordMinLengthMessage" in str(exc.value)
