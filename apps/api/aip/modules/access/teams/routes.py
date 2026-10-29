"""HTTP routes for teams and team membership (ACCESS-04), mounted under ``/api/v1/access``.

- ``GET /teams`` (``?projectId=``), ``POST /teams``, ``PATCH /teams/{team_id}``,
  ``DELETE /teams/{team_id}``;
- ``GET /teams/{team_id}/members``, ``POST /teams/{team_id}/members`` (``{userIds}``),
  ``DELETE /teams/{team_id}/members/{user_id}``.

Each route is ``authenticated()``; ``access.team.manage`` is checked in ``TeamService`` against
the team's project (tenant scope for a tenant-level team), deny by default. Errors are
``{"code": ...}``.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from aip.modules.access.roles.schemas import AccessErrorBody
from aip.modules.access.teams.schemas import (
    MembersAdd,
    TeamCreate,
    TeamList,
    TeamMemberList,
    TeamOut,
    TeamUpdate,
)
from aip.modules.access.teams.service import TeamService
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, PolicyService, authenticated

__all__ = ["router"]

_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": AccessErrorBody} for code in (403, 404, 409)
}
_INVALID: dict[int | str, dict[str, Any]] = {422: {"description": "Validation error"}}

Principal = Annotated[AccessPrincipal, Depends(authenticated())]


def _service(request: Request) -> TeamService:
    policy: PolicyService | None = getattr(request.app.state, "access_policy", None)
    if policy is None:  # access not installed: nothing is allowed
        raise HTTPException(status_code=503, detail="access policy is not available")
    return TeamService(policy)


Service = Annotated[TeamService, Depends(_service)]

router = APIRouter(prefix="/teams", tags=["access"], dependencies=[Depends(require_active_tenant)])


@router.get(
    "",
    operation_id="access_teams_list",
    response_model=TeamList,
    responses={**_ERRORS, **_INVALID},
)
async def list_teams(
    principal: Principal,
    service: Service,
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
) -> TeamList:
    return TeamList(items=await service.list(principal, project_id=project_id))


@router.post(
    "",
    operation_id="access_teams_create",
    response_model=TeamOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_ERRORS, **_INVALID},
)
async def create_team(body: TeamCreate, principal: Principal, service: Service) -> TeamOut:
    return await service.create(body, principal)


@router.patch(
    "/{team_id}",
    operation_id="access_teams_update",
    response_model=TeamOut,
    responses={**_ERRORS, **_INVALID},
)
async def update_team(
    team_id: UUID, body: TeamUpdate, principal: Principal, service: Service
) -> TeamOut:
    return await service.update(team_id, body, principal)


@router.delete(
    "/{team_id}",
    operation_id="access_teams_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_ERRORS,
)
async def delete_team(team_id: UUID, principal: Principal, service: Service) -> Response:
    await service.delete(team_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{team_id}/members",
    operation_id="access_team_members_list",
    response_model=TeamMemberList,
    responses=_ERRORS,
)
async def list_members(team_id: UUID, principal: Principal, service: Service) -> TeamMemberList:
    return TeamMemberList(items=await service.list_members(team_id, principal))


@router.post(
    "/{team_id}/members",
    operation_id="access_team_members_add",
    response_model=TeamMemberList,
    responses={**_ERRORS, **_INVALID},
)
async def add_members(
    team_id: UUID, body: MembersAdd, principal: Principal, service: Service
) -> TeamMemberList:
    return TeamMemberList(items=await service.add_members(team_id, body, principal))


@router.delete(
    "/{team_id}/members/{user_id}",
    operation_id="access_team_members_remove",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_ERRORS,
)
async def remove_member(
    team_id: UUID, user_id: UUID, principal: Principal, service: Service
) -> Response:
    await service.remove_member(team_id, user_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
