"""OIDC authorization-code + PKCE client for Keycloak (IDENTITY-01, ADR 0005).

Pure helpers (``domain_of``, ``build_authorize_url``, ``check_idp_binding``, ``safe_return_to``)
plus ``KeycloakOidcClient``, which exchanges the code with ``authlib`` and verifies the ID token
with ``joserfc`` against Keycloak's JWKS (cached in-process with a TTL).

Keycloak tokens never leave this module except as verified claims: they are not stored, not
logged and never sent to the browser.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc6749.parameters import prepare_grant_uri
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

__all__ = [
    "ID_TOKEN_ALGORITHMS",
    "JwksCache",
    "KeycloakOidcClient",
    "OidcError",
    "build_authorize_url",
    "check_idp_binding",
    "domain_of",
    "new_code_verifier",
    "new_nonce",
    "new_state",
    "safe_return_to",
]

ID_TOKEN_ALGORITHMS = ["RS256", "PS256", "ES256"]
SCOPE = "openid email profile"
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class OidcError(Exception):
    """A sign-in failure with a stable error code for the API response.

    The message is safe to return: it never contains a token, an email or a tenant.
    """

    def __init__(self, code: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message


def domain_of(email: str) -> str:
    """The lower-cased domain of ``email``; ``ValueError`` if it is not ``local@domain.tld``."""
    local, sep, domain = email.strip().rpartition("@")
    domain = domain.lower()
    if not sep or not local or "@" in local or not _DOMAIN_RE.match(domain):
        raise ValueError("not an email address")
    return domain


def new_state() -> str:
    """32 random bytes, base64url (43 characters)."""
    return secrets.token_urlsafe(32)


def new_nonce() -> str:
    return secrets.token_urlsafe(32)


def new_code_verifier() -> str:
    """RFC 7636 verifier: 64 random bytes, base64url (86 characters, within 43..128)."""
    return secrets.token_urlsafe(64)


def build_authorize_url(
    *,
    authorize_endpoint: str,
    client_id: str,
    redirect_uri: str,
    email: str,
    idp_alias: str | None,
    state: str,
    nonce: str,
    code_verifier: str,
    scope: str = SCOPE,
) -> str:
    """Keycloak's authorize URL: code flow, S256 PKCE, ``login_hint`` and, for SSO, ``kc_idp_hint``."""
    extra: dict[str, str] = {
        "nonce": nonce,
        "code_challenge": create_s256_code_challenge(code_verifier),
        "code_challenge_method": "S256",
        "login_hint": email,
    }
    if idp_alias is not None:
        extra["kc_idp_hint"] = idp_alias
    return prepare_grant_uri(
        authorize_endpoint,
        client_id,
        "code",
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        **extra,
    )


def check_idp_binding(claim_alias: str | None, cookie_alias: str | None) -> None:
    """The IdP Keycloak used must be the one the email domain resolved to before sign-in.

    - a present ``identity_provider`` claim must equal the pre-auth alias (403 IDP_TENANT_MISMATCH);
    - an absent claim is a Keycloak-local account, refused when the domain is an SSO domain
      (403 SSO_REQUIRED).
    """
    if claim_alias is not None:
        if claim_alias != cookie_alias:
            raise OidcError("IDP_TENANT_MISMATCH", 403, "signed in through a different identity provider")
        return
    if cookie_alias is not None:
        raise OidcError("SSO_REQUIRED", 403, "this email domain must sign in with company SSO")


def safe_return_to(value: str | None) -> str:
    """A same-origin path to return to after sign-in, else ``/``."""
    if not value or not value.startswith("/") or _CONTROL_RE.search(value):
        return "/"
    decoded = unquote(value)
    if decoded.startswith(("//", "/\\")) or "\\" in decoded[:2] or _CONTROL_RE.search(decoded):
        return "/"
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return "/"
    return value


class JwksCache:
    """Keycloak's JWKS, cached in-process for ``ttl`` seconds; refreshed early on an unknown key."""

    def __init__(self, jwks_uri: str, http: httpx.AsyncClient, ttl: float = 300.0) -> None:
        self._uri = jwks_uri
        self._http = http
        self._ttl = ttl
        self._keys: KeySet | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, *, refresh: bool = False) -> KeySet:
        async with self._lock:
            stale = time.monotonic() - self._fetched_at > self._ttl
            if self._keys is None or stale or refresh:
                response = await self._http.get(self._uri)
                response.raise_for_status()
                self._keys = KeySet.import_key_set(response.json())
                self._fetched_at = time.monotonic()
            return self._keys


class KeycloakOidcClient:
    """Code exchange and ID-token verification against one Keycloak realm and client."""

    def __init__(
        self,
        *,
        issuer: str,
        token_endpoint: str,
        jwks_uri: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        jwks_ttl: float = 300.0,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.issuer = issuer
        self.client_id = client_id
        self._token_endpoint = token_endpoint
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._timeout = timeout
        self._transport = transport
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)
        self.jwks = JwksCache(jwks_uri, self._http, ttl=jwks_ttl)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def exchange_code(self, *, code: str, code_verifier: str) -> str:
        """Redeem ``code`` with the PKCE verifier; return the raw ID token (and drop the rest)."""
        async with AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self._client_secret,
            token_endpoint_auth_method="client_secret_basic",
            redirect_uri=self._redirect_uri,
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            try:
                token: Mapping[str, Any] = await client.fetch_token(  # pyright: ignore[reportUnknownMemberType]
                    self._token_endpoint,
                    grant_type="authorization_code",
                    code=code,
                    code_verifier=code_verifier,
                )
            except Exception as exc:  # authlib raises OAuthError, httpx raises HTTPError
                raise OidcError("TOKEN_EXCHANGE_FAILED", 400, "the authorization code was rejected") from exc
        id_token = token.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OidcError("TOKEN_EXCHANGE_FAILED", 400, "no ID token was returned")
        return id_token

    async def verify_id_token(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        """Signature (JWKS), ``iss``, ``aud``/``azp``, ``exp``, ``iat`` and ``nonce``; returns the claims."""
        try:
            decoded = jwt.decode(id_token, await self.jwks.get(), algorithms=ID_TOKEN_ALGORITHMS)
        except (JoseError, ValueError):
            try:  # a rotated signing key: refetch the JWKS once
                decoded = jwt.decode(
                    id_token, await self.jwks.get(refresh=True), algorithms=ID_TOKEN_ALGORITHMS
                )
            except (JoseError, ValueError) as exc:
                raise OidcError("INVALID_ID_TOKEN", 400, "the ID token signature is invalid") from exc
        claims: dict[str, Any] = dict(decoded.claims)
        registry = jwt.JWTClaimsRegistry(
            leeway=30,
            iss={"essential": True, "value": self.issuer},
            aud={"essential": True, "value": self.client_id},
            sub={"essential": True},
            exp={"essential": True},
            iat={"essential": True},
            nonce={"essential": True, "value": nonce},
        )
        try:
            registry.validate(claims)
        except JoseError as exc:
            raise OidcError("INVALID_ID_TOKEN", 400, "the ID token claims are invalid") from exc
        aud = claims.get("aud")
        azp = claims.get("azp")
        if (isinstance(aud, list) and len(aud) > 1) or azp is not None:  # pyright: ignore[reportUnknownArgumentType]
            if azp != self.client_id:
                raise OidcError("INVALID_ID_TOKEN", 400, "the ID token was issued to another client")
        return claims
