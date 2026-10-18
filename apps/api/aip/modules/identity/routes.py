"""HTTP routes for identity (IDENTITY-01 to IDENTITY-04).

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

IDENTITY-04: ``GET /api/v1/auth/step-up/start`` (authenticated; redirects to Keycloak for a
fresh second factor, the callback then rotates the session), the invite routes under
``/api/v1/identity/invites`` and ``POST /api/v1/identity/users/{id}/reset-mfa`` (all mutations need
``identity.user.manage`` plus a step-up), and ``GET/PUT /api/v1/identity/signoff-policy``
(Part D; lowering a minimum needs a step-up and emits ``identity.signoff_policy.changed``).

``/me`` checks, in order and failing closed: a principal (401), the tenant active (401/403, via
tenancy's ``require_active_tenant``), then the user live and ``active`` in that tenant (401).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from functools import lru_cache
from typing import Annotated, Any, Literal
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.responses import Response

from aip.modules.identity import preauth_cookie
from aip.modules.identity import repository as repo
from aip.modules.identity.api import ExternalLoginHandler, get_external_login_handler
from aip.modules.identity.assurance import DEFAULT_MAX_AGE_MIN as DEFAULT_SIGNOFF_MAX_AGE_MIN
from aip.modules.identity.assurance import DEFAULT_MIN_AAL, SIGNOFF_ACTIONS
from aip.modules.identity.events import (
    SIGNOFF_POLICY_CHANGED,
    SignoffPolicyChangedEvent,
    SignoffPolicyValues,
)
from aip.modules.identity.invites import (
    InviteError,
    create_invite,
    resend_invite,
    reset_mfa,
    revoke_invite,
)
from aip.modules.identity.oidc import KeycloakOidcClient, OidcError, verify_logout_token
from aip.modules.identity.principal import Principal, get_principal
from aip.modules.identity.repository import InviteRow, SqlLoginDirectory
from aip.modules.identity.schemas import (
    AuthErrorResponse,
    ErrorResponse,
    InviteCreate,
    InviteCreated,
    InviteList,
    InviteOut,
    LoginStartRequest,
    LoginStartResponse,
    MeMembership,
    MeResponse,
    MeTenant,
    MeUser,
    SessionList,
    SessionOut,
    SignoffPolicyList,
    SignoffPolicyOut,
    SignoffPolicyUpdate,
    StepUpErrorResponse,
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
from aip.modules.identity.step_up import complete_step_up, require_step_up, step_up
from aip.modules.identity.step_up import now as step_up_clock
from aip.modules.tenancy.api import TenantView, require_active_tenant
from aip.platform.access import authenticated, public, requires
from aip.platform.db.session import before_tenant, with_tenant
from aip.platform.events import Aggregate, emit

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
        if identity.step_up is not None:
            response = await complete_step_up(identity)
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


# --- step-up (IDENTITY-04 step 6) -------------------------------------------------------------

step_up_router = APIRouter(prefix="/auth", tags=["identity"])


@step_up_router.get(
    "/step-up/start",
    dependencies=[Depends(authenticated())],
    status_code=303,
    response_class=Response,
    responses={
        303: {"description": "To Keycloak, which re-authenticates with a second factor."},
        401: {"model": AuthErrorResponse},
    },
)
async def step_up_start(
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[LoginService, Depends(get_login_service)],
    return_to: Annotated[str | None, Query(alias="returnTo", max_length=2048)] = None,
) -> Response:
    if principal.session_id is None:
        raise _not_authenticated()  # step-up elevates a browser session; nothing else has one
    async with with_tenant(principal.tenant_id) as conn:
        user = await repo.get_user(conn, principal.user_id)
    if user is None or user.status != "active":
        raise _not_authenticated()
    url, sealed = service.start_step_up(
        email=user.email,
        tenant_id=principal.tenant_id,
        idp_alias=user.idp_alias if user.sso_managed else None,
        session_id=principal.session_id,
        started_at=int(step_up_clock().timestamp()),
        return_to=return_to,
    )
    response = RedirectResponse(url, status_code=303)
    preauth_cookie.set_cookie(response, sealed)
    response.headers["Cache-Control"] = "no-store"
    return response


# --- invites and MFA reset (IDENTITY-04 steps 3, 4 and 7) ------------------------------------

admin_router = APIRouter(prefix="/identity", tags=["identity"])

_MANAGE = Depends(requires("identity.user.manage"))
_STEP_UP = Depends(step_up())
_ADMIN_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": StepUpErrorResponse, "description": "Not signed in, or a step-up is needed."},
    403: {"model": AuthErrorResponse},
    404: {"model": AuthErrorResponse},
    409: {"model": AuthErrorResponse},
}


def _refused(exc: InviteError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
    )


def _invite_out(row: InviteRow) -> InviteOut:
    return InviteOut(
        id=row.id,
        user_id=row.user_id,
        email=row.email,
        user_class=row.user_class,
        method=row.method,
        status=row.status,
        last_error=row.last_error,
        expires_at=row.expires_at,
        sent_at=row.sent_at,
        accepted_at=row.accepted_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


@admin_router.post(
    "/invites",
    dependencies=[_MANAGE, _STEP_UP],
    status_code=201,
    response_model=InviteCreated,
    responses={**_ADMIN_ERRORS, 422: {"model": AuthErrorResponse}},
)
async def create_invite_route(
    body: InviteCreate, principal: Annotated[Principal, Depends(get_principal)]
) -> InviteCreated:
    async with with_tenant(principal.tenant_id) as conn:
        try:
            created = await create_invite(
                conn,
                tenant_id=principal.tenant_id,
                email=body.email,
                user_class=body.user_class,
                first_name=body.first_name,
                last_name=body.last_name,
                organisation_id=body.organisation_id,
                invited_by=principal.user_id,
            )
        except InviteError as exc:
            raise _refused(exc) from None
    return InviteCreated(
        invite_id=created.invite_id, user_id=created.user_id, method=created.method
    )


@admin_router.get(
    "/invites",
    dependencies=[Depends(requires("identity.user.read"))],
    response_model=InviteList,
    responses={401: {"model": AuthErrorResponse}, 403: {"model": AuthErrorResponse}},
)
async def list_invites_route(
    principal: Annotated[Principal, Depends(get_principal)],
    status: Annotated[
        Literal["pending", "sent", "accepted", "revoked", "failed"] | None, Query()
    ] = None,
) -> InviteList:
    async with with_tenant(principal.tenant_id) as conn:
        rows = await repo.list_invites(conn, status=status)
    return InviteList(items=[_invite_out(r) for r in rows])


@admin_router.post(
    "/invites/{invite_id}/resend",
    dependencies=[_MANAGE, _STEP_UP],
    response_model=InviteOut,
    responses=_ADMIN_ERRORS,
)
async def resend_invite_route(
    invite_id: UUID, principal: Annotated[Principal, Depends(get_principal)]
) -> InviteOut:
    async with with_tenant(principal.tenant_id) as conn:
        try:
            row = await resend_invite(conn, invite_id)
        except InviteError as exc:
            raise _refused(exc) from None
    return _invite_out(row)


@admin_router.delete(
    "/invites/{invite_id}",
    dependencies=[_MANAGE, _STEP_UP],
    response_model=InviteOut,
    responses=_ADMIN_ERRORS,
)
async def revoke_invite_route(
    invite_id: UUID, principal: Annotated[Principal, Depends(get_principal)]
) -> InviteOut:
    async with with_tenant(principal.tenant_id) as conn:
        try:
            row = await revoke_invite(conn, invite_id)
        except InviteError as exc:
            raise _refused(exc) from None
    return _invite_out(row)


@admin_router.post(
    "/users/{user_id}/reset-mfa",
    dependencies=[_MANAGE, _STEP_UP],
    status_code=204,
    response_class=Response,
    responses=_ADMIN_ERRORS,
)
async def reset_mfa_route(
    user_id: UUID, principal: Annotated[Principal, Depends(get_principal)]
) -> Response:
    async with with_tenant(principal.tenant_id) as conn:
        try:
            await reset_mfa(conn, user_id)
        except InviteError as exc:
            raise _refused(exc) from None
    return Response(status_code=204)


# --- sign-off policy (IDENTITY-04 Part D) ----------------------------------------------------


def _policy_items(rows: list[repo.SignoffPolicyRow]) -> list[SignoffPolicyOut]:
    stored = {r.action_code: r for r in rows}
    items = [
        SignoffPolicyOut(
            action_code=r.action_code,
            min_aal=2 if r.min_aal >= 2 else 1,
            step_up_max_age_min=r.step_up_max_age_min,
            is_default=False,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    items += [
        SignoffPolicyOut(
            action_code=code,
            min_aal=DEFAULT_MIN_AAL,
            step_up_max_age_min=DEFAULT_SIGNOFF_MAX_AGE_MIN,
            is_default=True,
        )
        for code in SIGNOFF_ACTIONS
        if code not in stored
    ]
    return sorted(items, key=lambda item: item.action_code)


@admin_router.get(
    "/signoff-policy",
    dependencies=[Depends(requires("identity.signoff_policy.read"))],
    response_model=SignoffPolicyList,
    responses={401: {"model": AuthErrorResponse}, 403: {"model": AuthErrorResponse}},
)
async def get_signoff_policy_route(
    principal: Annotated[Principal, Depends(get_principal)],
) -> SignoffPolicyList:
    async with with_tenant(principal.tenant_id) as conn:
        rows = await repo.list_signoff_policies(conn)
    return SignoffPolicyList(items=_policy_items(rows))


@admin_router.put(
    "/signoff-policy",
    dependencies=[Depends(requires("identity.signoff_policy.manage"))],
    response_model=SignoffPolicyList,
    responses={
        401: {"model": StepUpErrorResponse, "description": "Lowering a minimum needs a step-up."},
        403: {"model": AuthErrorResponse},
    },
)
async def put_signoff_policy_route(
    body: SignoffPolicyUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> SignoffPolicyList:
    async with with_tenant(principal.tenant_id) as conn:
        before = await repo.get_signoff_policy(conn, body.action_code)
        before_min = before.min_aal if before is not None else DEFAULT_MIN_AAL
        before_age = (
            before.step_up_max_age_min if before is not None else DEFAULT_SIGNOFF_MAX_AGE_MIN
        )
        # ADR 0010: lowering a minimum or widening the window weakens sign-off (privileged).
        if body.min_aal < before_min or body.step_up_max_age_min > before_age:
            await require_step_up(request, principal, conn=conn)
        await repo.upsert_signoff_policy(
            conn,
            action_code=body.action_code,
            min_aal=body.min_aal,
            step_up_max_age_min=body.step_up_max_age_min,
            updated_by=principal.user_id,
        )
        payload = SignoffPolicyChangedEvent(
            action_code=body.action_code,
            before=None
            if before is None
            else SignoffPolicyValues(
                min_aal=before.min_aal, step_up_max_age_min=before.step_up_max_age_min
            ),
            after=SignoffPolicyValues(
                min_aal=body.min_aal, step_up_max_age_min=body.step_up_max_age_min
            ),
        )
        await emit(
            conn,
            SIGNOFF_POLICY_CHANGED,
            1,
            Aggregate("signoff_policy", principal.tenant_id),
            payload.model_dump(by_alias=True),
        )
        rows = await repo.list_signoff_policies(conn)
    return SignoffPolicyList(items=_policy_items(rows))


router = APIRouter()
router.include_router(auth_router)
router.include_router(step_up_router)
router.include_router(me_router)
router.include_router(admin_router)
