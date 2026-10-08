"""Fixtures for the identity tests: settings, an in-process OIDC provider stub and the app.

The stub stands in for Keycloak's token and JWKS endpoints (``httpx.MockTransport``): it signs ID
tokens with a fresh RSA key and checks the client secret and the PKCE verifier like Keycloak does.
The real Keycloak runs in ``test_keycloak_flows.py``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from joserfc import jwt
from joserfc.jwk import RSAKey

from aip.main import create_app
from aip.modules.identity.oidc import KeycloakOidcClient
from aip.modules.identity.repository import LoginTarget, LookupKind
from aip.modules.identity.routes import get_login_rate_limiter, get_login_service
from aip.modules.identity.service import LoginRateLimiter, LoginService
from aip.modules.identity.settings import IdentitySettings

TENANT_A_ID = UUID("00000000-0000-4000-8000-00000000000a")
TENANT_B_ID = UUID("00000000-0000-4000-8000-00000000000b")
KC = "https://kc.example.test"
CLIENT_SECRET = "test_only_client_secret"
PREAUTH_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def make_settings(**overrides: Any) -> IdentitySettings:
    values: dict[str, Any] = {
        "AIP_ENV": "test",
        "KEYCLOAK_URL": KC,
        "KEYCLOAK_REALM": "aip",
        "OIDC_CLIENT_ID": "aip-api",
        "OIDC_CLIENT_SECRET": CLIENT_SECRET,
        "APP_ORIGIN": "https://app.example.test",
        "PREAUTH_COOKIE_KEY": PREAUTH_KEY,
    }
    values.update(overrides)
    return IdentitySettings.model_validate(values)


class FakeDirectory:
    rows: dict[tuple[str, str], LoginTarget] = {  # noqa: RUF012 - read-only fixture data
        ("email_domain", "kaefer.test"): LoginTarget(TENANT_A_ID, "kaefer-oidc"),
        ("email_domain", "acme.test"): LoginTarget(TENANT_B_ID, "acme-oidc"),
    }

    async def resolve(self, kind: LookupKind, key: str) -> LoginTarget | None:
        return self.rows.get((kind, key.lower()))


@dataclass
class _Grant:
    claims: dict[str, Any]
    challenge: str
    redirect_uri: str


@dataclass
class StubProvider:
    """Keycloak's token + JWKS endpoints, in process."""

    issuer: str
    key: RSAKey = field(default_factory=lambda: RSAKey.generate_key(2048, parameters={"kid": "k1"}))
    grants: dict[str, _Grant] = field(default_factory=dict[str, _Grant])
    token_requests: int = 0

    def authorize(self, redirect_url: str, **claims: Any) -> str:
        """Play the browser + Keycloak: approve the authorize request, return the code."""
        q = {k: v[0] for k, v in parse_qs(urlsplit(redirect_url).query).items()}
        assert q["code_challenge_method"] == "S256"
        now = int(time.time())
        base: dict[str, Any] = {
            "iss": self.issuer,
            "aud": "aip-api",
            "azp": "aip-api",
            "sub": "kc-user-1",
            "iat": now,
            "exp": now + 300,
            "auth_time": now,
            "nonce": q["nonce"],
            "email": q.get("login_hint", "someone@example.test"),
            "email_verified": True,
            "sid": "kc-session-1",
        }
        if "kc_idp_hint" in q:
            base["identity_provider"] = q["kc_idp_hint"]
            base["acr"] = "aal1"
            base["amr"] = ["fed"]
        else:
            base["acr"] = "aal2"
            base["amr"] = ["pwd", "otp"]
        base.update(claims)
        base = {k: v for k, v in base.items() if v is not None}
        code = secrets.token_urlsafe(16)
        self.grants[code] = _Grant(base, q["code_challenge"], q["redirect_uri"])
        return code

    def sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode({"alg": "RS256", "kid": "k1"}, claims, self.key)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/certs"):
            return httpx.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if request.url.path.endswith("/token"):
            self.token_requests += 1
            expected = base64.b64encode(f"aip-api:{CLIENT_SECRET}".encode()).decode()
            if request.headers.get("authorization") != f"Basic {expected}":
                return httpx.Response(401, json={"error": "unauthorized_client"})
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            grant = self.grants.pop(form.get("code", ""), None)
            if grant is None or form.get("grant_type") != "authorization_code":
                return httpx.Response(400, json={"error": "invalid_grant"})
            verifier = form.get("code_verifier", "")
            digest = hashlib.sha256(verifier.encode()).digest()
            if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != grant.challenge:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "pkce"})
            if form.get("redirect_uri") != grant.redirect_uri:
                return httpx.Response(400, json={"error": "invalid_grant"})
            body = {
                "access_token": "eyJ-access-token-never-leaves-the-backend",
                "refresh_token": "eyJ-refresh",
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": self.sign(grant.claims),
            }
            return httpx.Response(200, content=json.dumps(body), headers={"content-type": "application/json"})
        return httpx.Response(404)


@pytest.fixture
def settings() -> IdentitySettings:
    return make_settings()


@pytest.fixture
def provider(settings: IdentitySettings) -> StubProvider:
    return StubProvider(issuer=settings.issuer)


@pytest.fixture
def oidc_client(settings: IdentitySettings, provider: StubProvider) -> Iterator[KeycloakOidcClient]:
    yield KeycloakOidcClient(
        issuer=settings.issuer,
        token_endpoint=settings.token_endpoint,
        jwks_uri=settings.jwks_uri,
        client_id=settings.oidc_client_id,
        client_secret=CLIENT_SECRET,
        redirect_uri=settings.redirect_uri,
        transport=httpx.MockTransport(provider.handler),
    )


@pytest.fixture
def app(
    settings: IdentitySettings, oidc_client: KeycloakOidcClient, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    monkeypatch.setenv("AIP_ENV", "test")  # the placeholder login handler echoes the identity
    application = create_app(env="test", tracing=False)
    service = LoginService(settings, FakeDirectory(), oidc_client)
    limiter = LoginRateLimiter.from_redis_url(None)
    application.dependency_overrides[get_login_service] = lambda: service
    application.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://app.example.test") as c:
        yield c
