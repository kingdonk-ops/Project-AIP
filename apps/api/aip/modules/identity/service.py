"""Staff sign-in through Keycloak (IDENTITY-01, ADR 0005).

``LoginService.start`` resolves the email domain in the login directory and builds Keycloak's
authorize URL plus the sealed pre-auth state. ``LoginService.complete`` checks state, redeems the
code with PKCE, verifies the ID token, enforces the IdP binding and aal2 for local accounts, and
returns a ``VerifiedExternalIdentity``. Keycloak tokens are discarded inside ``complete``.

No staff password, TOTP or WebAuthn code lives here: Keycloak does all of it.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from limits import RateLimitItem, parse
from limits.aio.storage import MemoryStorage, RedisStorage, Storage
from limits.aio.strategies import MovingWindowRateLimiter

from aip.modules.identity.oidc import (
    KeycloakOidcClient,
    OidcError,
    build_authorize_url,
    check_idp_binding,
    domain_of,
    new_code_verifier,
    new_nonce,
    new_state,
    safe_return_to,
)
from aip.modules.identity.preauth_cookie import (
    InvalidPreAuthError,
    PreAuthState,
    new_expiry,
    open_cookie,
    seal,
)
from aip.modules.identity.repository import LoginDirectory
from aip.modules.identity.schemas import LoginStartResponse, VerifiedExternalIdentity
from aip.modules.identity.settings import IdentitySettings

LOGIN_START_LIMIT = "10/minute"
REQUIRED_LOCAL_ACR = "aal2"


@dataclass(frozen=True)
class LoginStart:
    response: LoginStartResponse
    sealed_cookie: str


class LoginService:
    def __init__(
        self, settings: IdentitySettings, directory: LoginDirectory, oidc: KeycloakOidcClient
    ) -> None:
        self._settings = settings
        self._directory = directory
        self._oidc = oidc

    async def start(self, email: str, return_to: str | None) -> LoginStart:
        """``ValueError`` for a malformed email; otherwise the same shape for every domain."""
        domain = domain_of(email)
        target = await self._directory.resolve("email_domain", domain)
        tenant_id = target.tenant_id if target else None
        idp_alias = target.idp_alias if target else None
        state = PreAuthState(
            state=new_state(),
            nonce=new_nonce(),
            code_verifier=new_code_verifier(),
            tenant_id=tenant_id,
            idp_alias=idp_alias,
            return_to=safe_return_to(return_to),
            exp=new_expiry(),
        )
        url = build_authorize_url(
            authorize_endpoint=self._settings.authorize_endpoint,
            client_id=self._settings.oidc_client_id,
            redirect_uri=self._settings.redirect_uri,
            email=email.strip(),
            idp_alias=idp_alias,
            state=state.state,
            nonce=state.nonce,
            code_verifier=state.code_verifier,
        )
        response = LoginStartResponse(
            method="sso" if idp_alias is not None else "password", redirect_url=url
        )
        return LoginStart(response=response, sealed_cookie=seal(state, self._settings.preauth_key))

    async def complete(
        self, params: Mapping[str, str], cookie: str | None
    ) -> VerifiedExternalIdentity:
        try:
            pre = open_cookie(cookie, self._settings.preauth_key)
        except InvalidPreAuthError as exc:
            raise OidcError("INVALID_STATE", 400, "sign-in state is missing or invalid") from exc
        state = params.get("state", "")
        if not hmac.compare_digest(state.encode(), pre.state.encode()):
            raise OidcError("INVALID_STATE", 400, "sign-in state is missing or invalid")
        iss = params.get("iss")
        if iss is not None and iss != self._settings.issuer:  # RFC 9207 mix-up defence
            raise OidcError("INVALID_ISSUER", 400, "unexpected authorization server")
        if "error" in params:
            raise OidcError("LOGIN_FAILED", 400, "sign-in was not completed")
        code = params.get("code")
        if not code:
            raise OidcError("LOGIN_FAILED", 400, "no authorization code")

        id_token = await self._oidc.exchange_code(code=code, code_verifier=pre.code_verifier)
        claims = await self._oidc.verify_id_token(id_token, nonce=pre.nonce)
        del id_token  # never stored, logged or sent to the browser

        claim_alias = _opt_str(claims.get("identity_provider"))
        check_idp_binding(claim_alias, pre.idp_alias)
        acr = _opt_str(claims.get("acr"))
        if claim_alias is None and acr != REQUIRED_LOCAL_ACR:
            raise OidcError("MFA_NOT_SATISFIED", 403, "a second factor is required")
        return _identity(claims, pre, claim_alias, acr)


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _identity(
    claims: Mapping[str, Any], pre: PreAuthState, alias: str | None, acr: str | None
) -> VerifiedExternalIdentity:
    email = claims.get("email")
    auth_time = claims.get("auth_time")
    if not isinstance(email, str) or not email:
        raise OidcError("INVALID_ID_TOKEN", 400, "the ID token has no email")
    if not isinstance(auth_time, int | float):
        raise OidcError("INVALID_ID_TOKEN", 400, "the ID token has no auth_time")
    raw_amr: object = claims.get("amr")
    amr = [str(v) for v in raw_amr] if isinstance(raw_amr, list) else []  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return VerifiedExternalIdentity(
        tenant_id=pre.tenant_id,
        idp_alias=alias,
        subject=str(claims["sub"]),
        email=email,
        email_verified=claims.get("email_verified") is True,
        acr=acr,
        amr=amr,
        auth_time=datetime.fromtimestamp(auth_time, tz=UTC),
        kc_sid=_opt_str(claims.get("sid")),
        return_to=pre.return_to,
    )


class LoginRateLimiter:
    """10 ``login/start`` calls per minute per client IP, moving window (``limits``)."""

    def __init__(self, storage: Storage, limit: str = LOGIN_START_LIMIT) -> None:
        self._limiter = MovingWindowRateLimiter(storage)
        item: RateLimitItem = parse(limit)
        self._item = item

    @classmethod
    def from_redis_url(cls, url: str | None) -> LoginRateLimiter:
        """Redis (Valkey) storage when ``url`` is set, else in-process memory (dev and tests)."""
        if not url:
            return cls(MemoryStorage())
        scheme, sep, rest = url.partition("://")
        if not sep or scheme not in ("redis", "rediss"):
            raise ValueError("REDIS_URL must be redis:// or rediss://")
        return cls(RedisStorage(f"async+{scheme}://{rest}", implementation="redispy"))

    async def hit(self, client_key: str) -> bool:
        return await self._limiter.hit(self._item, "identity-login-start", client_key)
