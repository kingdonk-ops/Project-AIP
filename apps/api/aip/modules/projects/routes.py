"""HTTP routes for projects and sites (PROJECTS-01), mounted under ``/api/v1``.

Every route declares its permission with ``requires(...)`` (deny by default, ACCESS-01) and needs
an active tenant. Explicit ``operation_id``s keep the generated client's hook names stable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from aip.modules.projects.schemas import (
    ErrorBody,
    ProjectCreate,
    ProjectOut,
    ProjectPage,
    ProjectSort,
    ProjectStatus,
    ProjectUpdate,
    SiteCreate,
    SiteOut,
    SitePage,
    SiteUpdate,
)
from aip.modules.projects.service import ProjectService, SiteService
from aip.modules.projects.settings import get_settings
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, PolicyService, Resource, requires

__all__ = ["router"]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorBody}}
_CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorBody}}
_INVALID: dict[int | str, dict[str, Any]] = {422: {"description": "Validation error"}}

Limit = Annotated[int, Query(ge=1, le=200)]
Cursor = Annotated[str | None, Query(max_length=1024)]
Search = Annotated[str | None, Query(min_length=1, max_length=100)]


def _project_resource(request: Request) -> Resource | None:
    """The project in the path, so a project-scoped grant can allow the call."""
    try:
        return Resource(project_id=UUID(request.path_params["project_id"]))
    except (KeyError, ValueError):
        return None  # FastAPI rejects the malformed id with 422


projects_router = APIRouter(prefix="/projects", tags=["projects"])
sites_router = APIRouter(prefix="/sites", tags=["sites"])


@projects_router.get(
    "",
    operation_id="projects_list",
    response_model=ProjectPage,
    responses=_INVALID,
    dependencies=[Depends(requires("project.view"))],
)
async def list_projects(
    limit: Limit = 50,
    cursor: Cursor = None,
    sort: ProjectSort = "code",
    status_: Annotated[list[ProjectStatus], Query(alias="status")] = [],  # noqa: B006 - FastAPI copies it
    site_id: Annotated[UUID | None, Query(alias="siteId")] = None,
    q: Search = None,
) -> ProjectPage:
    return await ProjectService().list(
        limit=limit, cursor=cursor, sort=sort, statuses=status_, site_id=site_id, q=q
    )


# Declared before "/{project_id}", which would otherwise claim the path (and 422 on the id).
@projects_router.get(
    "/export.csv",
    operation_id="projects_export",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/csv": {}}, "description": "The filtered projects as CSV"},
        422: {"model": ErrorBody, "description": "Validation error, or EXPORT_TOO_LARGE"},
    },
    dependencies=[Depends(requires("project.view"))],
)
async def export_projects(
    sort: ProjectSort = "code",
    status_: Annotated[list[ProjectStatus], Query(alias="status")] = [],  # noqa: B006 - FastAPI copies it
    site_id: Annotated[UUID | None, Query(alias="siteId")] = None,
    q: Search = None,
) -> StreamingResponse:
    """The same filters and sort as the list, as one CSV file (PROJECTS-06, DESIGN-03)."""
    chunks = await ProjectService().export_csv(sort=sort, statuses=status_, site_id=site_id, q=q)
    return StreamingResponse(
        chunks,
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": 'attachment; filename="projects.csv"'},
    )


@projects_router.get(
    "/{project_id}",
    operation_id="projects_get",
    response_model=ProjectOut,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("project.view", _project_resource))],
)
async def get_project(project_id: UUID) -> ProjectOut:
    return await ProjectService().get(project_id)


@projects_router.post(
    "",
    operation_id="projects_create",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("project.create"))],
)
async def create_project(body: ProjectCreate) -> ProjectOut:
    return await ProjectService().create(body)


@projects_router.patch(
    "/{project_id}",
    operation_id="projects_update",
    response_model=ProjectOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    request: Request,
    principal: Annotated[AccessPrincipal, Depends(requires("project.update", _project_resource))],
) -> ProjectOut:
    if body.status == "archived":
        policy: PolicyService = request.app.state.access_policy
        resource = Resource(project_id=project_id, tenant_id=principal.tenant_id)
        await policy.assert_can(principal, "project.archive", resource)
    return await ProjectService().update(project_id, body)


@sites_router.get(
    "",
    operation_id="sites_list",
    response_model=SitePage,
    responses=_INVALID,
    dependencies=[Depends(requires("site.view"))],
)
async def list_sites(limit: Limit = 50, cursor: Cursor = None, q: Search = None) -> SitePage:
    return await SiteService().list(limit=limit, cursor=cursor, q=q)


@sites_router.get(
    "/{site_id}",
    operation_id="sites_get",
    response_model=SiteOut,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("site.view"))],
)
async def get_site(site_id: UUID) -> SiteOut:
    return await SiteService().get(site_id)


@sites_router.post(
    "",
    operation_id="sites_create",
    response_model=SiteOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("site.manage"))],
)
async def create_site(body: SiteCreate) -> SiteOut:
    return await SiteService().create(body)


@sites_router.patch(
    "/{site_id}",
    operation_id="sites_update",
    response_model=SiteOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("site.manage"))],
)
async def update_site(site_id: UUID, body: SiteUpdate) -> SiteOut:
    return await SiteService().update(site_id, body)


@sites_router.delete(
    "/{site_id}",
    operation_id="sites_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("site.manage"))],
)
async def delete_site(site_id: UUID) -> Response:
    await SiteService().delete(site_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@asynccontextmanager
async def _validate_settings(app: FastAPI) -> AsyncIterator[None]:
    """Load the settings when the server starts, so a missing cursor key fails the deploy."""
    get_settings()
    yield


router = APIRouter(dependencies=[Depends(require_active_tenant)], lifespan=_validate_settings)
router.include_router(projects_router)
router.include_router(sites_router)
