"""login/start and the OIDC callback against the in-process provider stub (IDENTITY-01)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse, Response

from aip.modules.identity.api import (
    PlaceholderLoginHandler,
    VerifiedExternalIdentity,
    get_external_login_handler,
)
from aip.modules.identity.preauth_cookie import COOKIE_NAME

from .conftest import TENANT_A_ID, StubProvider


async def _start(client: httpx.AsyncClient, email: str, **extra: Any) -> tuple[dict[str, Any], str]:
    r = await client.post("/api/v1/auth/login/start", json={"email": email, **extra})
    assert r.status_code == 200, r.text
    cookie = r.cookies.get(COOKIE_NAME)
    assert cookie
    return r.json(), cookie


async def _callback(client: httpx.AsyncClient, cookie: str | None, **params: str) -> httpx.Response:
    client.cookies.clear()
    if cookie is not None:
        client.cookies.set(COOKIE_NAME, cookie)
    return await client.get("/api/v1/auth/oidc/callback", params=params)


def _state(url: str) -> str:
    from urllib.parse import parse_qs, urlsplit

    return parse_qs(urlsplit(url).query)["state"][0]


async def test_start_known_and_unknown_domains_have_the_same_shape(
    client: httpx.AsyncClient,
) -> None:
    unknown, _ = await _start(client, "x@unknown.test")
    sso, _ = await _start(client, "alice@kaefer.test", returnTo="/projects")
    assert unknown["method"] == "password"
    assert "kc_idp_hint" not in unknown["redirectUrl"]
    assert sso["method"] == "sso"
    assert "kc_idp_hint=kaefer-oidc" in sso["redirectUrl"]
    assert set(unknown) == set(sso) == {"method", "redirectUrl"}
    assert str(TENANT_A_ID) not in sso["redirectUrl"]


async def test_start_sets_a_host_cookie(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login/start", json={"email": "alice@kaefer.test"})
    header = r.headers["set-cookie"]
    assert header.startswith(f"{COOKIE_NAME}=")
    for attr in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=600"):
        assert attr in header
    assert r.headers["cache-control"] == "no-store"


async def test_start_rejects_malformed_email(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login/start", json={"email": "no-at-sign"})
    assert r.status_code == 422
    assert r.json()["code"] == "INVALID_EMAIL"


async def test_sso_callback_yields_identity(
    client: httpx.AsyncClient, provider: StubProvider
) -> None:
    body, cookie = await _start(client, "alice@kaefer.test", returnTo="/projects?x=1")
    code = provider.authorize(body["redirectUrl"])
    r = await _callback(client, cookie, code=code, state=_state(body["redirectUrl"]))
    assert r.status_code == 200, r.text
    identity = r.json()
    assert identity["tenant_id"] == str(TENANT_A_ID)
    assert identity["idp_alias"] == "kaefer-oidc"
    assert identity["email"] == "alice@kaefer.test"
    assert identity["kc_sid"] == "kc-session-1"
    assert identity["return_to"] == "/projects?x=1"
    # No Keycloak token reaches the browser, and the pre-auth cookie is cleared.
    assert "eyJ" not in r.text
    assert "eyJ" not in r.headers.get("set-cookie", "")
    assert f'{COOKIE_NAME}=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]


async def test_local_callback_requires_aal2(
    client: httpx.AsyncClient, provider: StubProvider
) -> None:
    body, cookie = await _start(client, "carol@client.test")
    ok = provider.authorize(body["redirectUrl"])
    r = await _callback(client, cookie, code=ok, state=_state(body["redirectUrl"]))
    assert r.status_code == 200, r.text
    assert r.json()["idp_alias"] is None and r.json()["tenant_id"] is None
    assert r.json()["acr"] == "aal2" and {"pwd", "otp"} <= set(r.json()["amr"])

    body, cookie = await _start(client, "carol@client.test")
    weak = provider.authorize(body["redirectUrl"], acr="aal1", amr=["pwd"])
    r = await _callback(client, cookie, code=weak, state=_state(body["redirectUrl"]))
    assert r.status_code == 403
    assert r.json()["code"] == "MFA_NOT_SATISFIED"


async def test_idp_mismatch(client: httpx.AsyncClient, provider: StubProvider) -> None:
    body, cookie = await _start(client, "alice@kaefer.test")
    code = provider.authorize(
        body["redirectUrl"], identity_provider="acme-oidc", email="bob@acme.test"
    )
    r = await _callback(client, cookie, code=code, state=_state(body["redirectUrl"]))
    assert r.status_code == 403
    assert r.json()["code"] == "IDP_TENANT_MISMATCH"
    assert "Max-Age=0" in r.headers["set-cookie"]


async def test_local_account_on_sso_domain(
    client: httpx.AsyncClient, provider: StubProvider
) -> None:
    body, cookie = await _start(client, "alice@kaefer.test")
    code = provider.authorize(body["redirectUrl"], identity_provider=None, acr="aal2")
    r = await _callback(client, cookie, code=code, state=_state(body["redirectUrl"]))
    assert r.status_code == 403
    assert r.json()["code"] == "SSO_REQUIRED"


async def test_state_mismatch(client: httpx.AsyncClient, provider: StubProvider) -> None:
    body, cookie = await _start(client, "alice@kaefer.test")
    code = provider.authorize(body["redirectUrl"])
    r = await _callback(client, cookie, code=code, state="not-the-state")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_STATE"
    assert "Max-Age=0" in r.headers["set-cookie"]
    assert provider.token_requests == 0


async def test_tampered_cookie(client: httpx.AsyncClient, provider: StubProvider) -> None:
    body, cookie = await _start(client, "alice@kaefer.test")
    code = provider.authorize(body["redirectUrl"])
    i = len(cookie) // 2
    tampered = cookie[:i] + ("A" if cookie[i] != "A" else "B") + cookie[i + 1 :]
    r = await _callback(client, tampered, code=code, state=_state(body["redirectUrl"]))
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_STATE"


async def test_missing_cookie(client: httpx.AsyncClient) -> None:
    r = await _callback(client, None, code="x", state="y")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_STATE"


@pytest.mark.parametrize(
    ("claims", "code"),
    [
        ({"nonce": "other"}, "INVALID_ID_TOKEN"),
        ({"aud": "someone-else", "azp": "someone-else"}, "INVALID_ID_TOKEN"),
        ({"iss": "https://evil.test/realms/aip"}, "INVALID_ID_TOKEN"),
        ({"exp": 1000}, "INVALID_ID_TOKEN"),
    ],
)
async def test_bad_id_tokens(
    client: httpx.AsyncClient, provider: StubProvider, claims: dict[str, Any], code: str
) -> None:
    body, cookie = await _start(client, "carol@client.test")
    grant = provider.authorize(body["redirectUrl"], **claims)
    r = await _callback(client, cookie, code=grant, state=_state(body["redirectUrl"]))
    assert r.status_code == 400
    assert r.json()["code"] == code


async def test_wrong_pkce_verifier_fails_exchange(
    client: httpx.AsyncClient, provider: StubProvider
) -> None:
    body1, _cookie1 = await _start(client, "carol@client.test")
    body2, cookie2 = await _start(client, "carol@client.test")
    code = provider.authorize(body1["redirectUrl"])  # challenge of attempt 1
    # Cookie (and verifier) of attempt 2 with the state of attempt 2: the exchange must fail.
    r = await _callback(client, cookie2, code=code, state=_state(body2["redirectUrl"]))
    assert r.status_code == 400
    assert r.json()["code"] == "TOKEN_EXCHANGE_FAILED"


async def test_wrong_iss_parameter(client: httpx.AsyncClient, provider: StubProvider) -> None:
    body, cookie = await _start(client, "carol@client.test")
    code = provider.authorize(body["redirectUrl"])
    r = await _callback(
        client, cookie, code=code, state=_state(body["redirectUrl"]), iss="https://evil.test"
    )
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_ISSUER"


async def test_provider_error_parameter(client: httpx.AsyncClient) -> None:
    body, cookie = await _start(client, "carol@client.test")
    r = await _callback(client, cookie, error="access_denied", state=_state(body["redirectUrl"]))
    assert r.status_code == 400
    assert r.json()["code"] == "LOGIN_FAILED"


async def test_rate_limit(client: httpx.AsyncClient) -> None:
    for _ in range(10):
        r = await client.post("/api/v1/auth/login/start", json={"email": "x@unknown.test"})
        assert r.status_code == 200
    r = await client.post("/api/v1/auth/login/start", json={"email": "x@unknown.test"})
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"


async def test_handler_is_replaceable(
    app: FastAPI, client: httpx.AsyncClient, provider: StubProvider
) -> None:
    seen: list[VerifiedExternalIdentity] = []

    class Handler:
        async def __call__(self, identity: VerifiedExternalIdentity) -> Response:
            seen.append(identity)
            return JSONResponse({"ok": True})

    app.dependency_overrides[get_external_login_handler] = Handler
    body, cookie = await _start(client, "alice@kaefer.test")
    code = provider.authorize(body["redirectUrl"])
    r = await _callback(client, cookie, code=code, state=_state(body["redirectUrl"]))
    assert r.json() == {"ok": True}
    assert seen[0].tenant_id == TENANT_A_ID


async def test_placeholder_handler_outside_test_is_501() -> None:
    from datetime import UTC, datetime

    identity = VerifiedExternalIdentity(
        tenant_id=None,
        idp_alias=None,
        subject="s",
        email="a@b.test",
        email_verified=True,
        acr="aal2",
        amr=["pwd", "otp"],
        auth_time=datetime.now(UTC),
        kc_sid=None,
    )
    r = await PlaceholderLoginHandler(env="development")(identity)
    assert r.status_code == 501
    assert b"PROVISIONING_NOT_IMPLEMENTED" in r.body


def test_routes_are_marked_public(app: FastAPI) -> None:
    paths = app.openapi()["paths"]
    assert paths["/api/v1/auth/login/start"]["post"]["x-aip-access"] == "public"
    assert paths["/api/v1/auth/oidc/callback"]["get"]["x-aip-access"] == "public"


def test_no_staff_credential_libraries() -> None:
    from pathlib import Path

    module = Path(__file__).resolve().parents[1]
    for path in module.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for banned in (
            "import argon2",
            "import pyotp",
            "import webauthn",
            "from argon2",
            "from pyotp",
            "from webauthn",
        ):
            assert banned not in text or path.name == Path(__file__).name, f"{path}: {banned}"
