"""The portal sign-in routes against the in-process OIDC stub (IDENTITY-10).

The portal's Keycloak client is stubbed like the staff one (``StubProvider(client_id="aip-portal")``);
the verified identity is echoed by the placeholder handler, JIT and the session are covered by
``sessions/test_portal_sessions_db.py``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI

from aip.modules.identity.api import PlaceholderLoginHandler, get_portal_login_handler
from aip.modules.identity.oidc import KeycloakOidcClient
from aip.modules.identity.preauth_cookie import COOKIE_NAME
from aip.modules.identity.routes import get_portal_login_service
from aip.modules.identity.service import LoginService
from aip.modules.identity.settings import IdentitySettings

from .conftest import FakeDirectory, StubProvider, make_settings

PORTAL_ORIGIN = "https://portal.example.test"
PORTAL_SECRET = "test_only_portal_secret"
START = "/api/v1/auth/portal/login/start"
CALLBACK = "/api/v1/auth/portal/oidc/callback"


@pytest.fixture
def portal_settings() -> IdentitySettings:
    return make_settings(PORTAL_ORIGIN=PORTAL_ORIGIN, PORTAL_OIDC_CLIENT_SECRET=PORTAL_SECRET)


@pytest.fixture
def portal_provider(portal_settings: IdentitySettings) -> StubProvider:
    return StubProvider(
        issuer=portal_settings.issuer, client_id="aip-portal", client_secret=PORTAL_SECRET
    )


@pytest.fixture
def portal_app(
    app: FastAPI, portal_settings: IdentitySettings, portal_provider: StubProvider
) -> FastAPI:
    oidc = KeycloakOidcClient(
        issuer=portal_settings.issuer,
        token_endpoint=portal_settings.token_endpoint,
        jwks_uri=portal_settings.jwks_uri,
        client_id="aip-portal",
        client_secret=PORTAL_SECRET,
        redirect_uri=portal_settings.portal_redirect_uri,
        transport=httpx.MockTransport(portal_provider.handler),
    )
    service = LoginService(portal_settings, FakeDirectory(), oidc, audience="portal")
    app.dependency_overrides[get_portal_login_service] = lambda: service
    app.dependency_overrides[get_portal_login_handler] = PlaceholderLoginHandler
    return app


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


async def _start(
    client: httpx.AsyncClient, email: str, path: str = START, **extra: Any
) -> tuple[dict[str, Any], str]:
    r = await client.post(path, json={"email": email, **extra})
    assert r.status_code == 200, r.text
    cookie = r.cookies.get(COOKIE_NAME)
    assert cookie
    return r.json(), cookie


async def _callback(
    client: httpx.AsyncClient, cookie: str, path: str = CALLBACK, **params: str
) -> httpx.Response:
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, cookie)
    return await client.get(path, params=params)


async def test_portal_start_is_local_aal2_on_the_portal_client(
    portal_app: FastAPI, client: httpx.AsyncClient
) -> None:
    sso, _ = await _start(client, "alice@kaefer.test", returnTo="/inbox")
    unknown, _ = await _start(client, "client.a@rio.example")
    for body in (sso, unknown):
        assert set(body) == {"method", "redirectUrl"}
        assert body["method"] == "password"
        q = _query(body["redirectUrl"])
        assert q["client_id"] == "aip-portal"
        assert q["acr_values"] == "aal2"
        assert q["redirect_uri"] == f"{PORTAL_ORIGIN}/api/v1/auth/portal/oidc/callback"
        assert "kc_idp_hint" not in q
    response = await client.post(START, json={"email": "x@rio.example"})
    assert response.headers["cache-control"] == "no-store"


async def test_portal_callback_yields_a_portal_identity(
    portal_app: FastAPI, client: httpx.AsyncClient, portal_provider: StubProvider
) -> None:
    body, cookie = await _start(client, "client.a@rio.example", returnTo="/inbox")
    code = portal_provider.authorize(body["redirectUrl"])
    r = await _callback(client, cookie, code=code, state=_query(body["redirectUrl"])["state"])
    assert r.status_code == 200, r.text
    identity = r.json()
    assert identity["audience"] == "portal"
    assert identity["idp_alias"] is None
    assert identity["tenant_id"] is None
    assert identity["return_to"] == "/inbox"
    assert r.headers["cache-control"] == "no-store"
    assert "eyJ" not in r.text


async def test_portal_callback_refuses_a_brokered_or_single_factor_sign_in(
    portal_app: FastAPI, client: httpx.AsyncClient, portal_provider: StubProvider
) -> None:
    body, cookie = await _start(client, "client.a@rio.example")
    state = _query(body["redirectUrl"])["state"]
    code = portal_provider.authorize(body["redirectUrl"], identity_provider="kaefer-oidc")
    r = await _callback(client, cookie, code=code, state=state)
    assert (r.status_code, r.json()["code"]) == (403, "IDP_TENANT_MISMATCH")

    body, cookie = await _start(client, "client.a@rio.example")
    state = _query(body["redirectUrl"])["state"]
    code = portal_provider.authorize(body["redirectUrl"], acr="aal1", amr=["pwd"])
    r = await _callback(client, cookie, code=code, state=state)
    assert (r.status_code, r.json()["code"]) == (403, "MFA_NOT_SATISFIED")


async def test_a_pre_auth_cookie_only_finishes_at_its_own_callback(
    portal_app: FastAPI,
    client: httpx.AsyncClient,
    provider: StubProvider,
    portal_provider: StubProvider,
) -> None:
    staff, staff_cookie = await _start(client, "carol@unknown.test", path="/api/v1/auth/login/start")
    code = provider.authorize(staff["redirectUrl"])
    r = await _callback(client, staff_cookie, code=code, state=_query(staff["redirectUrl"])["state"])
    assert (r.status_code, r.json()["code"]) == (400, "INVALID_STATE")

    portal, portal_cookie = await _start(client, "client.a@rio.example")
    code = portal_provider.authorize(portal["redirectUrl"])
    r = await _callback(
        client,
        portal_cookie,
        path="/api/v1/auth/oidc/callback",
        code=code,
        state=_query(portal["redirectUrl"])["state"],
    )
    assert (r.status_code, r.json()["code"]) == (400, "INVALID_STATE")


async def test_portal_routes_answer_503_when_not_configured(
    app: FastAPI, client: httpx.AsyncClient, settings: IdentitySettings
) -> None:
    from aip.modules.identity.routes import get_identity_settings

    app.dependency_overrides[get_identity_settings] = lambda: settings  # no portal secret
    r = await client.post(START, json={"email": "client.a@rio.example"})
    assert (r.status_code, r.json()["code"]) == (503, "PORTAL_NOT_CONFIGURED")
    r = await client.get(CALLBACK, params={"code": "x", "state": "y"})
    assert (r.status_code, r.json()["code"]) == (503, "PORTAL_NOT_CONFIGURED")
    staff = await client.post("/api/v1/auth/login/start", json={"email": "alice@kaefer.test"})
    assert staff.status_code == 200
