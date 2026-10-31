"""HTTP routes for portal users and grants (PORTAL-01), mounted under ``/api/v1``.

All under ``/admin/portal/users``; every route declares its permission with ``requires(...)``
(deny by default, ACCESS-01) and needs an active tenant. Invite, renew and reinstate also need a
fresh step-up (IDENTITY-04). The grant routes resolve the project their permission is checked on:
the invite and add-grant bodies name it (the invite's first grant; the service then checks every
grant's project), renew and revoke read it from the grant. When no project can be resolved the
check is tenant-wide, so a project-scoped admin gets 403 and never learns whether an id exists.

On start, every code a grant action gives (``ACTION_PERMISSIONS``, including codes host modules
registered) must be in the permission catalogue, or the app refuses to start.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response, status

from aip.modules.identity.api import step_up
from aip.modules.portal import policies
from aip.modules.portal import repository as repo
from aip.modules.portal.schemas import (
    GrantIn,
    GrantOut,
    InviteIn,
    PortalErrorBody,
    PortalUserOut,
    PortalUserPage,
    SuspendIn,
)
from aip.modules.portal.service import PortalService
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, PolicyService, Resource, requires
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant

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
ExpiringWithin = Annotated[
    int | None, Query(alias="expiringWithinDays", ge=1, le=policies.MAX_ACCESS_DAYS)
]
ProjectFilter = Annotated[UUID | None, Query(alias="projectId")]


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
    project_id: ProjectFilter = None,
    expiring_within_days: ExpiringWithin = None,
) -> PortalUserPage:
    """``expiringWithinDays``: users with a live grant ending within that many days (PORTAL-07);
    ``projectId``: users with an unrevoked grant on that project."""
    return await _service(request, principal).list(
        status=status_,
        q=q,
        cursor=cursor,
        limit=limit,
        project_id=project_id,
        expiring_within_days=expiring_within_days,
    )


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


router = APIRouter(dependencies=[Depends(require_active_tenant)], lifespan=_check_actions_on_start)
router.include_router(users_router)
