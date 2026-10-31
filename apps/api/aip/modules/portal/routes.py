"""HTTP routes for portal users and grants (PORTAL-01), mounted under ``/api/v1``.

All under ``/admin/portal/users``; every route declares its permission with ``requires(...)``
(deny by default, ACCESS-01) and needs an active tenant. Invite, renew and reinstate also need a
fresh step-up (IDENTITY-04). The grant routes resolve the project their permission is checked on:
the invite and add-grant bodies name it (the invite's first grant; the service then checks every
grant's project), renew and revoke read it from the grant. When no project can be resolved the
check is tenant-wide, so a project-scoped admin gets 403 and never learns whether an id exists.

PORTAL-02: the client routes under ``/portal`` (``client_router``) are the only routes a portal
session reaches, and only a portal session reaches them (``authenticated(external=True)``; anything
else answers 404). Each request first counts against the portal rate limits (``rate_limit``).
``GET /portal/me`` marks the first sign-in and records ``portal.signed_in`` once per session;
``POST /portal/logout`` ends the session (identity's ``revoke_session``) and clears only the portal
cookies; CSRF is identity's middleware. Every client response is ``Cache-Control: no-store``.

On start, every code a grant action gives (``ACTION_PERMISSIONS``, including codes host modules
registered) must be in the permission catalogue, or the app refuses to start.
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response, status

from aip.modules.audit.api import AuditApi, SecurityEventInput
from aip.modules.identity.api import (
    Principal,
    clear_session_cookies,
    get_principal,
    revoke_session,
    step_up,
)
from aip.modules.portal import policies
from aip.modules.portal import repository as repo
from aip.modules.portal.rate_limit import PortalLimits
from aip.modules.portal.schemas import (
    GrantIn,
    GrantOut,
    InviteIn,
    PortalErrorBody,
    PortalMeOut,
    PortalUserOut,
    PortalUserPage,
    SuspendIn,
)
from aip.modules.portal.service import PortalService, client_me
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import (
    AccessPrincipal,
    PolicyService,
    Resource,
    authenticated,
    requires,
)
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant
from aip.platform.http import DomainError

__all__ = ["router"]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": PortalErrorBody, "description": "Not found"}
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": PortalErrorBody, "description": "Conflict"}
}
_INVALID: dict[int | str, dict[str, Any]] = {
    422: {"model": PortalErrorBody, "description": "Validation error"}
}

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=1024)]
Search = Annotated[str | None, Query(min_length=1, max_length=100)]


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except ValueError:
        return None


async def _body_project(request: Request) -> Resource | None:
    """The project the body names: ``projectId``, or the first grant's (invite)."""
    try:
        body = await request.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    candidate: object = body.get("projectId")  # pyright: ignore[reportUnknownMemberType]
    grants: object = body.get("grants")  # pyright: ignore[reportUnknownMemberType]
    if candidate is None and isinstance(grants, list) and grants:
        first: object = grants[0]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(first, dict):
            candidate = first.get("projectId")  # pyright: ignore[reportUnknownMemberType]
    project_id = None if candidate is None else _uuid(candidate)
    return None if project_id is None else Resource(project_id=project_id)


async def _grant_project(request: Request) -> Resource | None:
    """The project of the grant in the path (RLS-loaded, so only this tenant's grants)."""
    grant_id = _uuid(request.path_params.get("grant_id"))
    if grant_id is None:
        return None
    async with with_tenant(get_context()) as conn:
        grant = await repo.get_grant(conn, grant_id)
    return None if grant is None else Resource(project_id=grant["project_id"])


def _service(request: Request, principal: AccessPrincipal) -> PortalService:
    policy: PolicyService = request.app.state.access_policy
    return PortalService(policy, principal)


users_router = APIRouter(prefix="/admin/portal/users", tags=["portal"])

InvitePrincipal = Annotated[AccessPrincipal, Depends(requires("portal.user.invite", _body_project))]
ViewPrincipal = Annotated[AccessPrincipal, Depends(requires("portal.user.view"))]
SuspendPrincipal = Annotated[AccessPrincipal, Depends(requires("portal.user.suspend"))]
AddGrantPrincipal = Annotated[
    AccessPrincipal, Depends(requires("portal.grant.manage", _body_project))
]
GrantPrincipal = Annotated[
    AccessPrincipal, Depends(requires("portal.grant.manage", _grant_project))
]


@users_router.post(
    "",
    operation_id="portal_users_invite",
    response_model=PortalUserOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(step_up())],
)
async def invite_portal_user(
    body: InviteIn, request: Request, principal: InvitePrincipal
) -> PortalUserOut:
    return await _service(request, principal).invite(body)


@users_router.get(
    "",
    operation_id="portal_users_list",
    response_model=PortalUserPage,
    responses=_INVALID,
)
async def list_portal_users(
    request: Request,
    principal: ViewPrincipal,
    status_: Annotated[policies.PortalUserStatus | None, Query(alias="status")] = None,
    q: Search = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> PortalUserPage:
    return await _service(request, principal).list(status=status_, q=q, cursor=cursor, limit=limit)


@users_router.get(
    "/{portal_user_id}",
    operation_id="portal_users_get",
    response_model=PortalUserOut,
    responses=_NOT_FOUND,
)
async def get_portal_user(
    portal_user_id: UUID, request: Request, principal: ViewPrincipal
) -> PortalUserOut:
    return await _service(request, principal).get(portal_user_id)


@users_router.post(
    "/{portal_user_id}/suspend",
    operation_id="portal_users_suspend",
    response_model=PortalUserOut,
    responses={**_NOT_FOUND, **_CONFLICT},
)
async def suspend_portal_user(
    portal_user_id: UUID, body: SuspendIn, request: Request, principal: SuspendPrincipal
) -> PortalUserOut:
    return await _service(request, principal).suspend(portal_user_id, body.reason)


@users_router.post(
    "/{portal_user_id}/reinstate",
    operation_id="portal_users_reinstate",
    response_model=PortalUserOut,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(step_up())],
)
async def reinstate_portal_user(
    portal_user_id: UUID, request: Request, principal: SuspendPrincipal
) -> PortalUserOut:
    return await _service(request, principal).reinstate(portal_user_id)


@users_router.post(
    "/{portal_user_id}/grants",
    operation_id="portal_grants_create",
    response_model=GrantOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
)
async def add_portal_grant(
    portal_user_id: UUID, body: GrantIn, request: Request, principal: AddGrantPrincipal
) -> GrantOut:
    return await _service(request, principal).add_grant(portal_user_id, body)


@users_router.post(
    "/{portal_user_id}/grants/{grant_id}/renew",
    operation_id="portal_grants_renew",
    response_model=GrantOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(step_up())],
)
async def renew_portal_grant(
    portal_user_id: UUID, grant_id: UUID, request: Request, principal: GrantPrincipal
) -> GrantOut:
    return await _service(request, principal).renew(portal_user_id, grant_id)


@users_router.delete(
    "/{portal_user_id}/grants/{grant_id}",
    operation_id="portal_grants_revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_NOT_FOUND,
)
async def revoke_portal_grant(
    portal_user_id: UUID, grant_id: UUID, request: Request, principal: GrantPrincipal
) -> Response:
    await _service(request, principal).revoke(portal_user_id, grant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def check_action_codes(catalogue: Iterable[str]) -> None:
    """``RuntimeError`` when a grant action gives a code the catalogue does not declare."""
    missing = policies.unknown_action_codes(catalogue)
    if missing:
        raise RuntimeError(f"portal grant actions give unknown permission codes: {missing}")


@asynccontextmanager
async def _check_actions_on_start(app: FastAPI) -> AsyncIterator[None]:
    """Refuse to start when a registered action code is missing from the catalogue."""
    check_action_codes(app.state.access_catalogue)
    yield


# --- the client routes (PORTAL-02) ----------------------------------------------------------

NO_STORE: Final = "no-store"
# Longer than the longest portal session (8 h absolute by default): one signed_in per session.
_SIGNED_IN_TTL: Final = 24 * 3600


def portal_limits(request: Request) -> PortalLimits:
    """The app's portal limiters (built once, from the environment)."""
    limits: PortalLimits | None = getattr(request.app.state, "portal_limits", None)
    if limits is None:
        limits = PortalLimits.from_env()
        request.app.state.portal_limits = limits
    return limits


def _client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return None if host is None else str(ipaddress.ip_address(host))
    except ValueError:
        return None


async def _security_event(event_type: str, **fields: Any) -> None:
    async with with_tenant(get_context()) as conn:
        await AuditApi().record_security_event(
            conn, SecurityEventInput(event_type=event_type, **fields)
        )


async def rate_limit(request: Request, response: Response) -> None:
    """Count the request against its session's and its IP's budget; 429 over either."""
    response.headers["Cache-Control"] = NO_STORE
    principal = await get_principal(request)
    limits = portal_limits(request)
    ip = _client_ip(request)
    session = str(principal.session_id or principal.user_id)
    for kind, limiter, key in (
        ("session", limits.session, session),
        ("ip", limits.ip, ip or "unknown"),
    ):
        hit = await limiter.hit(key)
        if hit.allowed:
            continue
        if hit.first_refusal:
            await _security_event(
                "portal.rate_limited",
                target_ref=f"session:{session}",
                source_ip=ip,
                detail={"limit": kind, "perMinute": limiter.limit},
            )
        refused = DomainError(429, "RATE_LIMITED")
        refused.headers = {"Retry-After": str(hit.retry_after), "Cache-Control": NO_STORE}
        raise refused


ClientPrincipal = Annotated[Principal, Depends(get_principal)]

# The session first (an ended one answers 401 SESSION_EXPIRED and clears the portal cookies), then
# the rate limits, then the tenant check the admin routes also make.
client_router = APIRouter(
    prefix="/portal",
    tags=["portal"],
    dependencies=[
        Depends(authenticated(external=True)),
        Depends(rate_limit),
        Depends(require_active_tenant),
    ],
    responses={404: {"model": PortalErrorBody}, 429: {"model": PortalErrorBody}},
)


@client_router.get("/me", operation_id="portal_me", response_model=PortalMeOut)
async def portal_me(request: Request, principal: ClientPrincipal) -> PortalMeOut:
    """The signed-in client, its access status and the projects it may act on now."""
    limits = portal_limits(request)
    once_key = f"signed_in:{principal.session_id or principal.user_id}"
    first = await limits.store.once(once_key, _SIGNED_IN_TTL)
    try:
        async with with_tenant(get_context()) as conn:
            me = await client_me(conn, principal.tenant_id, principal.user_id)
            if me is None:
                raise DomainError(404, "NOT_FOUND")
            if first:
                await AuditApi().record_security_event(
                    conn,
                    SecurityEventInput(
                        event_type="portal.signed_in",
                        target_ref=f"session:{principal.session_id}",
                        auth_strength=f"aal{principal.aal}",
                        source_ip=_client_ip(request),
                    ),
                )
    except BaseException:
        if first:
            await limits.store.forget(once_key)  # nothing was recorded: the next call tries again
        raise
    return me


@client_router.post(
    "/logout",
    operation_id="portal_logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def portal_logout(principal: ClientPrincipal) -> Response:
    """End this portal session and clear the portal cookies (never the staff ones)."""
    if principal.session_id is not None:
        async with with_tenant(get_context()) as conn:
            await revoke_session(conn, principal.session_id, "logout")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(response, audience="portal")
    response.headers["Cache-Control"] = NO_STORE
    return response


router = APIRouter(lifespan=_check_actions_on_start)
router.include_router(users_router, dependencies=[Depends(require_active_tenant)])
router.include_router(client_router)
