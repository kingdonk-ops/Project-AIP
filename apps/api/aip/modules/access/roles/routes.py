"""HTTP routes for roles and role assignments (ACCESS-02), mounted under ``/api/v1/access``.

- Roles (``access.role.read`` / ``access.role.manage``): ``GET /roles``, ``POST /roles``,
  ``PATCH /roles/{id}``, ``DELETE /roles/{id}``, ``POST /roles/{id}/clone``,
  ``POST /roles/{id}/reset``.
- Assignments (``access.role_assignment.read`` / ``.manage``): ``GET /role-assignments``
  (``?userId=&projectId=&teamId=``), ``POST /role-assignments`` (ACCESS-04: also
  ``{"scope": {"type": "team", "teamId": ...}}`` without ``userId``),
  ``DELETE /role-assignments/{id}``.

Every route needs an active tenant. Errors are ``{"code": ...}`` (see ``service``).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from aip.modules.access.roles.schemas import (
    AccessErrorBody,
    AssignmentCreate,
    AssignmentList,
    AssignmentOut,
    RoleClone,
    RoleCreate,
    RoleList,
    RoleOut,
    RoleUpdate,
)
from aip.modules.access.roles.service import AssignmentService, RoleService
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, requires

__all__ = ["router"]

_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": AccessErrorBody} for code in (400, 403, 404, 409)
}
_INVALID: dict[int | str, dict[str, Any]] = {422: {"description": "Validation error"}}

ROLE_READ = Depends(requires("access.role.read"))
ROLE_MANAGE = Depends(requires("access.role.manage"))
RoleManager = Annotated[AccessPrincipal, ROLE_MANAGE]
AssignmentManager = Annotated[AccessPrincipal, Depends(requires("access.role_assignment.manage"))]
ASSIGNMENT_READ = Depends(requires("access.role_assignment.read"))

roles_router = APIRouter(prefix="/roles", tags=["access"])
assignments_router = APIRouter(prefix="/role-assignments", tags=["access"])


@roles_router.get(
    "", operation_id="access_roles_list", response_model=RoleList, dependencies=[ROLE_READ]
)
async def list_roles() -> RoleList:
    return RoleList(items=await RoleService().list())


@roles_router.post(
    "",
    operation_id="access_roles_create",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_ERRORS, **_INVALID},
)
async def create_role(body: RoleCreate, principal: RoleManager) -> RoleOut:
    return await RoleService().create(body, principal)


@roles_router.patch(
    "/{role_id}",
    operation_id="access_roles_update",
    response_model=RoleOut,
    responses={**_ERRORS, **_INVALID},
)
async def update_role(role_id: UUID, body: RoleUpdate, principal: RoleManager) -> RoleOut:
    return await RoleService().update(role_id, body, principal)


@roles_router.delete(
    "/{role_id}",
    operation_id="access_roles_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_ERRORS,
    dependencies=[ROLE_MANAGE],
)
async def delete_role(role_id: UUID) -> Response:
    await RoleService().delete(role_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roles_router.post(
    "/{role_id}/clone",
    operation_id="access_roles_clone",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_ERRORS, **_INVALID},
)
async def clone_role(role_id: UUID, body: RoleClone, principal: RoleManager) -> RoleOut:
    return await RoleService().clone(role_id, body, principal)


@roles_router.post(
    "/{role_id}/reset",
    operation_id="access_roles_reset",
    response_model=RoleOut,
    responses=_ERRORS,
)
async def reset_role(role_id: UUID, principal: RoleManager) -> RoleOut:
    return await RoleService().reset(role_id, principal)


@assignments_router.get(
    "",
    operation_id="access_role_assignments_list",
    response_model=AssignmentList,
    responses=_INVALID,
    dependencies=[ASSIGNMENT_READ],
)
async def list_assignments(
    user_id: Annotated[UUID | None, Query(alias="userId")] = None,
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
    team_id: Annotated[UUID | None, Query(alias="teamId")] = None,
) -> AssignmentList:
    items = await AssignmentService().list(user_id=user_id, project_id=project_id, team_id=team_id)
    return AssignmentList(items=items)


@assignments_router.post(
    "",
    operation_id="access_role_assignments_create",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_ERRORS, **_INVALID},
)
async def create_assignment(body: AssignmentCreate, principal: AssignmentManager) -> AssignmentOut:
    return await AssignmentService().create(body, principal)


@assignments_router.delete(
    "/{assignment_id}",
    operation_id="access_role_assignments_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_ERRORS,
)
async def delete_assignment(assignment_id: UUID, principal: AssignmentManager) -> Response:
    await AssignmentService().delete(assignment_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


router = APIRouter(dependencies=[Depends(require_active_tenant)])
router.include_router(roles_router)
router.include_router(assignments_router)
