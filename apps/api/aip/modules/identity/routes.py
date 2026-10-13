"""HTTP routes for identity (IDENTITY-01, IDENTITY-02).

- ``POST /api/v1/auth/login/start``: public, rate limited (10/min per IP).
- ``GET /api/v1/auth/oidc/callback``: public; clears the pre-auth cookie on every outcome.
- ``GET /api/v1/me``: authenticated; the caller's own user, tenant and memberships.
- IDENTITY-03: ``POST /api/v1/auth/logout`` (public, idempotent: revokes the current session if
  any, clears both cookies, 204), ``POST /api/v1/auth/oidc/backchannel-logout`` (public, Keycloak
  server to server; the signed logout token authenticates it), ``GET /api/v1/me/sessions`` and
  ``DELETE /api/v1/me/sessions/{id}`` (authenticated; only the caller's own sessions, another
  user's id is 404).

The two auth routes are ``public()`` and ``/me`` is ``authenticated()`` (ACCESS-01); the auth
routes' error bodies are ``{code, detail}``. ``/me`` errors follow ADR 0015
(``{"detail": {"code", "message"}}``). No error body contains a token, email or tenant.

``/me`` checks, in order and failing closed: a principal (401), the tenant active (401/403, via
tenancy's ``require_active_tenant``), then the user live and ``active`` in that tenant (401).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from functools import lru_cache
from typing import Annotated
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.responses import Response

from aip.modules.identity import preauth_cookie
from aip.modules.identity import repository as repo
from aip.modules.identity.api import ExternalLoginHandler, get_external_login_handler
from aip.modules.identity.oidc import KeycloakOidcClient, OidcError, verify_logout_token
from aip.modules.identity.principal import Principal, get_principal
from aip.modules.identity.repository import SqlLoginDirectory
from aip.modules.identity.schemas import (
    AuthErrorResponse,
    ErrorResponse,
    LoginStartRequest,
    LoginStartResponse,
    MeMembership,
    MeResponse,
    MeTenant,
    MeUser,
    SessionList,
    SessionOut,
)
from aip.modules.identity.service import LoginRateLimiter, LoginService
from aip.modules.identity.session_store import current_session
from aip.modules.identity.sessions import (
    clear_session_cookies,
    list_user_sessions,
    owns_live_session,
    revoke_session,
)
from aip.modules.identity.settings import IdentitySettings, IdentitySettingsError
from aip.modules.tenancy.api import TenantView, require_active_tenant
from aip.platform.access import authenticated, public
from aip.platform.db.session import before_tenant, with_tenant

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["identity"], dependencies=[Depends(public())])


@lru_cache(maxsize=1)
def _settings() -> IdentitySettings:
    return IdentitySettings()  # pyright: ignore[reportCallIssue] - values come from the environment


def get_identity_settings() -> IdentitySettings:
    try:
        return _settings()
    except (ValidationError, IdentitySettingsError):
        logger.error("identity settings are missing or invalid; sign-in is unavailable")
        raise HTTPException(status_code=503, detail="sign-in is not configured") from None


def get_login_service(
    request: Request, settings: Annotated[IdentitySettings, Depends(get_identity_settings)]
) -> LoginService:
    service: LoginService | None = getattr(request.app.state, "identity_login_service", None)
    if service is None:
        oidc = KeycloakOidcClient(
            issuer=settings.issuer,
            token_endpoint=settings.token_endpoint,
            jwks_uri=settings.jwks_uri,
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret.get_secret_value(),
            redirect_uri=settings.redirect_uri,
            jwks_ttl=settings.jwks_ttl_seconds,
            timeout=settings.http_timeout_seconds,
        )
        service = LoginService(settings, SqlLoginDirectory(), oidc)
        request.app.state.identity_login_service = service
    return service


def get_login_rate_limiter(request: Request) -> LoginRateLimiter:
    limiter: LoginRateLimiter | None = getattr(request.app.state, "identity_rate_limiter", None)
    if limiter is None:
        limiter = LoginRateLimiter.from_redis_url(os.environ.get("REDIS_URL"))
        request.app.state.identity_rate_limiter = limiter
    return limiter


def _error(code: str, status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail}, status_code=status_code)


@auth_router.post(
    "/login/start",
    response_model=LoginStartResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Unprocessable Entity"},
        429: {"model": ErrorResponse},
    },
)
async def login_start(
    body: LoginStartRequest,
    request: Request,
    service: Annotated[LoginService, Depends(get_login_service)],
    limiter: Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)],
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    if not await limiter.hit(client_ip):
        return _error("RATE_LIMITED", 429, "too many sign-in attempts; try again shortly")
    try:
        start = await service.start(body.email, body.return_to)
    except ValueError:
        return _error("INVALID_EMAIL", 422, "enter a valid email address")
    response = JSONResponse(start.response.model_dump(mode="json", by_alias=True))
    preauth_cookie.set_cookie(response, start.sealed_cookie)
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_router.get(
    "/oidc/callback",
    responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def oidc_callback(
    request: Request,
    service: Annotated[LoginService, Depends(get_login_service)],
    handler: Annotated[ExternalLoginHandler, Depends(get_external_login_handler)],
) -> Response:
    cookie = request.cookies.get(preauth_cookie.COOKIE_NAME)
    try:
        identity = await service.complete(dict(request.query_params), cookie)
    except OidcError as exc:
        logger.info("oidc callback refused: %s", exc.code)
        response: Response = _error(exc.code, exc.status_code, exc.message)
    else:
        response = await handler(identity)
    preauth_cookie.clear_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_router.post("/logout", status_code=204, response_class=Response)
async def logout() -> Response:
    """Revoke the current session (the Keycloak SSO session ends through the queued job)."""
    session = current_session()
    if session is not None:
        async with with_tenant(session.tenant_id) as conn:
            await revoke_session(conn, session.session_id, "logout")
    response = Response(status_code=204)
    clear_session_cookies(response)
    response.headers["Cache-Control"] = "no-store"
    return response


_LOGOUT_BODY_MAX = 16 * 1024
_BY_KC_SID = text("SELECT tenant_id, session_id FROM identity_sessions_by_kc_sid(:sid)")


def get_logout_verifier(
    service: Annotated[LoginService, Depends(get_login_service)],
) -> Callable[[str], Awaitable[str]]:
    """How a logout token becomes a Keycloak ``sid`` (tests may override)."""

    async def verify(token: str) -> str:
        return await verify_logout_token(service.oidc, token)

    return verify


@auth_router.post(
    "/oidc/backchannel-logout",
    responses={400: {"model": ErrorResponse}},
)
async def backchannel_logout(
    request: Request,
    verify: Annotated[Callable[[str], Awaitable[str]], Depends(get_logout_verifier)],
) -> Response:
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError:
        declared = _LOGOUT_BODY_MAX + 1
    if declared > _LOGOUT_BODY_MAX:
        return _error("INVALID_LOGOUT_TOKEN", 400, "the logout request is too large")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > _LOGOUT_BODY_MAX:
            return _error("INVALID_LOGOUT_TOKEN", 400, "the logout request is too large")
    tokens = parse_qs(body.decode("utf-8", "replace")).get("logout_token", [])
    if len(tokens) != 1:
        return _error("INVALID_LOGOUT_TOKEN", 400, "send exactly one logout_token")
    try:
        kc_sid = await verify(tokens[0])
    except OidcError as exc:
        logger.info("back-channel logout refused: %s", exc.code)
        return _error(exc.code, exc.status_code, exc.message)
    async with before_tenant() as conn:
        rows = (await conn.execute(_BY_KC_SID, {"sid": kc_sid})).all()
    for tenant_id, session_id in rows:
        async with with_tenant(tenant_id) as conn:
            await revoke_session(conn, session_id, "keycloak_logout", end_keycloak=False)
    response = Response(status_code=200)
    response.headers["Cache-Control"] = "no-store"
    return response


me_router = APIRouter(tags=["identity"])

TenantConnect = Callable[[UUID], AbstractAsyncContextManager[AsyncConnection]]


def get_tenant_connect() -> TenantConnect:
    """How ``/me`` opens its tenant transaction (``with_tenant``; tests may override)."""
    return with_tenant


def _not_authenticated() -> HTTPException:
    return HTTPException(
        status_code=401, detail={"code": "NOT_AUTHENTICATED", "message": "not authenticated"}
    )


@me_router.get(
    "/me",
    dependencies=[Depends(authenticated())],
    response_model=MeResponse,
    responses={
        200: {"description": "The caller's own user, tenant and memberships."},
        401: {
            "model": AuthErrorResponse,
            "description": "No authenticated principal, or the user is unknown or not active.",
        },
        403: {
            "model": AuthErrorResponse,
            "description": "The tenant is suspended, offboarded or not ready.",
        },
    },
)
async def get_me(
    principal: Annotated[Principal, Depends(get_principal)],
    tenant: Annotated[TenantView, Depends(require_active_tenant)],
    connect: Annotated[TenantConnect, Depends(get_tenant_connect)],
    response: Response,
) -> MeResponse:
    if tenant.id != principal.tenant_id:  # defence in depth: both come from the same resolver
        raise _not_authenticated()
    async with connect(principal.tenant_id) as conn:
        user = await repo.get_user(conn, principal.user_id)
        if user is None or user.tenant_id != principal.tenant_id or user.status != "active":
            raise _not_authenticated()
        memberships = await repo.list_memberships(conn, user.id)
    response.headers["Cache-Control"] = "no-store"
    return MeResponse(
        user=MeUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            user_class=user.user_class,
            status=user.status,
        ),
        tenant=MeTenant(id=tenant.id, slug=tenant.slug, name=tenant.name),
        memberships=[
            MeMembership(
                id=m.id,
                membership_type=m.membership_type,
                organisation_id=m.organisation_id,
                valid_from=m.valid_from,
                valid_to=m.valid_to,
            )
            for m in memberships
            if m.tenant_id == principal.tenant_id
        ],
        aal=principal.aal,
        amr=principal.amr,
    )


@me_router.get(
    "/me/sessions",
    dependencies=[Depends(authenticated())],
    response_model=SessionList,
    responses={401: {"model": AuthErrorResponse}},
)
async def list_my_sessions(
    principal: Annotated[Principal, Depends(get_principal)], response: Response
) -> SessionList:
    async with with_tenant(principal.tenant_id) as conn:
        rows = await list_user_sessions(conn, principal.user_id)
    response.headers["Cache-Control"] = "no-store"
    return SessionList(
        items=[SessionOut(**row, current=row["id"] == principal.session_id) for row in rows]
    )


@me_router.delete(
    "/me/sessions/{session_id}",
    dependencies=[Depends(authenticated())],
    status_code=204,
    response_class=Response,
    responses={401: {"model": AuthErrorResponse}, 404: {"model": AuthErrorResponse}},
)
async def revoke_my_session(
    session_id: UUID, principal: Annotated[Principal, Depends(get_principal)]
) -> Response:
    async with with_tenant(principal.tenant_id) as conn:
        if not await owns_live_session(conn, session_id, principal.user_id):
            raise HTTPException(
                status_code=404, detail={"code": "NOT_FOUND", "message": "no such session"}
            )
        await revoke_session(conn, session_id, "user_revoked")
    response = Response(status_code=204)
    if session_id == principal.session_id:
        clear_session_cookies(response)
    return response


router = APIRouter()
router.include_router(auth_router)
router.include_router(me_router)
