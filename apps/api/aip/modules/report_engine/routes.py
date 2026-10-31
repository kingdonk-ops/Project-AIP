"""HTTP routes for report templates (REPORTS-01) and render jobs (REPORTS-02).

Every route needs an active tenant and declares its access (deny by default, ACCESS-01). Each
request runs in one ``with_tenant`` transaction, so another tenant's id is a 404 (RLS hides it).
Explicit ``operation_id``s keep the generated client's hook names stable, and the ``422``
description is pinned so the OpenAPI schema does not drift across Python versions.

``/api/v1/reports/templates``: reading and previewing need ``report.template.view``; uploading,
publishing, retiring and deleting a draft need ``report.template.manage``. The preview returns the
rendered sample as ``text/html`` under a sandboxing CSP and ``nosniff``, with its assets inlined as
``data:`` URIs (a browser has no sibling files).

``/api/v1/reports/renders`` (REPORTS-02): the permission depends on the record's project, which is
only known once the record is read, so the routes take the signed-in principal and the service
checks ``PolicyService.can`` with that project as the resource. Requesting and re-rendering need
``report.create`` plus the record's own view permission (``project.view`` for a project); reading
needs ``report.view``. A deny is 403 with nothing written; a list leaves out the jobs the caller may
not view. Bodies are strict (an unknown key is 422); ``Idempotency-Key`` is at most 128 characters.

REPORTS-04: the list filters by ``status`` (repeatable) and searches ``q`` (record label or template
key) for the report register. ``GET /{id}/file`` streams a succeeded job's PDF from uploads as an
attachment (``report.view``; 409 ``REPORT_NOT_READY`` before it has succeeded); no response ever
carries a storage key or presigned URL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine.render_service import Authorizer, RenderService
from aip.modules.report_engine.schemas import (
    RenderJobPage,
    RenderJobStatus,
    RenderJobView,
    RenderRequest,
    ReportErrorBody,
    ReportTemplateDetail,
    ReportTemplatePage,
    ReportTemplateUpload,
)
from aip.modules.report_engine.service import TemplateService
from aip.modules.report_engine.template_package import TemplatePackageError, parse_package
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, PolicyService, Resource, authenticated, requires
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant
from aip.platform.http import DomainError

__all__ = ["PREVIEW_CSP", "router"]

PREVIEW_CSP: Final = (
    "default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; sandbox"
)

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ReportErrorBody}}
_CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ReportErrorBody}}
_INVALID: dict[int | str, dict[str, Any]] = {
    422: {"model": ReportErrorBody, "description": "Unprocessable Entity"}
}

RecordType = Annotated[str | None, Query(alias="recordType", pattern=r"^[a-z][a-z_]{1,40}$")]
Status = Annotated[str | None, Query(alias="status", pattern=r"^(draft|published|retired)$")]
Cursor = Annotated[str | None, Query(max_length=200)]
Limit = Annotated[int, Query(ge=1, le=200)]
RenderStatuses = Annotated[list[RenderJobStatus], Query(alias="status", max_length=4)]
Search = Annotated[str | None, Query(min_length=1, max_length=100)]

router = APIRouter(dependencies=[Depends(require_active_tenant)])
templates_router = APIRouter(prefix="/reports/templates", tags=["reports"])
_service = TemplateService()


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


@templates_router.get(
    "",
    operation_id="reports_templates_list",
    response_model=ReportTemplatePage,
    responses=_INVALID,
    dependencies=[Depends(requires("report.template.view"))],
)
async def list_templates(
    record_type: RecordType = None,
    status_: Status = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> ReportTemplatePage:
    async with _tx() as conn:
        return await _service.list(
            conn, record_type=record_type, status=status_, cursor=cursor, limit=limit
        )


@templates_router.post(
    "",
    operation_id="reports_templates_create",
    response_model=ReportTemplateDetail,
    status_code=status.HTTP_201_CREATED,
    responses={**_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("report.template.manage"))],
)
async def create_template(body: ReportTemplateUpload) -> ReportTemplateDetail:
    try:
        package = parse_package(body.model_dump(by_alias=True))
    except TemplatePackageError as exc:
        raise DomainError(422, exc.code, path=exc.path, detail=exc.detail) from None
    async with _tx() as conn:
        row = await _service.create_draft(conn, get_context().actor_id, package)
    return ReportTemplateDetail.from_row(row)


@templates_router.get(
    "/{template_id}",
    operation_id="reports_templates_get",
    response_model=ReportTemplateDetail,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("report.template.view"))],
)
async def get_template(template_id: UUID) -> ReportTemplateDetail:
    async with _tx() as conn:
        return await _service.detail(conn, template_id)


@templates_router.post(
    "/{template_id}/publish",
    operation_id="reports_templates_publish",
    response_model=ReportTemplateDetail,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("report.template.manage"))],
)
async def publish_template(template_id: UUID) -> ReportTemplateDetail:
    async with _tx() as conn:
        row = await _service.publish(conn, get_context().actor_id, template_id)
    return ReportTemplateDetail.from_row(row)


@templates_router.post(
    "/{template_id}/retire",
    operation_id="reports_templates_retire",
    response_model=ReportTemplateDetail,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("report.template.manage"))],
)
async def retire_template(template_id: UUID) -> ReportTemplateDetail:
    async with _tx() as conn:
        row = await _service.retire(conn, get_context().actor_id, template_id)
    return ReportTemplateDetail.from_row(row)


@templates_router.delete(
    "/{template_id}",
    operation_id="reports_templates_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("report.template.manage"))],
)
async def delete_template(template_id: UUID) -> Response:
    async with _tx() as conn:
        await _service.delete_draft(conn, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@templates_router.post(
    "/{template_id}/preview",
    operation_id="reports_templates_preview",
    response_class=Response,
    responses={
        200: {"content": {"text/html": {"schema": {"type": "string"}}}},
        **_NOT_FOUND,
        **_INVALID,
    },
    dependencies=[Depends(requires("report.template.view"))],
)
async def preview_template(template_id: UUID) -> Response:
    ctx = get_context()
    async with _tx() as conn:
        document = await _service.preview(conn, ctx.tenant_id, template_id)
    return Response(
        content=document,
        media_type="text/html; charset=utf-8",
        headers={"Content-Security-Policy": PREVIEW_CSP, "X-Content-Type-Options": "nosniff"},
    )


# --- REPORTS-02: render jobs ------------------------------------------------------------------

renders_router = APIRouter(prefix="/reports/renders", tags=["reports"])
_renders = RenderService()

_FORBIDDEN: dict[int | str, dict[str, Any]] = {403: {"model": ReportErrorBody}}
Principal = Annotated[AccessPrincipal, Depends(authenticated())]
IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)
]
RecordId = Annotated[UUID | None, Query(alias="recordId")]


def _authorizer(request: Request, principal: AccessPrincipal) -> Authorizer:
    """``authorize(code, project_id)`` through the app's policy service (deny without one)."""
    policy: PolicyService | None = getattr(request.app.state, "access_policy", None)

    async def authorize(code: str, project_id: UUID | None) -> bool:
        if policy is None:
            return False
        resource = Resource(project_id=project_id, tenant_id=principal.tenant_id)
        return (await policy.can(principal, code, resource)).allowed

    return authorize


@renders_router.post(
    "",
    operation_id="reports_renders_create",
    response_model=RenderJobView,
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_FORBIDDEN, **_NOT_FOUND, **_INVALID},
)
async def request_render(
    body: RenderRequest,
    request: Request,
    principal: Principal,
    idempotency_key: IdempotencyKey = None,
) -> RenderJobView:
    async with _tx() as conn:
        return await _renders.request_render(
            conn,
            template_key=body.template_key,
            record_type=body.record_type,
            record_id=body.record_id,
            variant=body.variant,
            requested_by=principal.actor_id,
            idempotency_key=idempotency_key,
            authorize=_authorizer(request, principal),
        )


@renders_router.get(
    "",
    operation_id="reports_renders_list",
    response_model=RenderJobPage,
    responses=_INVALID,
)
async def list_renders(
    request: Request,
    principal: Principal,
    record_type: RecordType = None,
    record_id: RecordId = None,
    status_: RenderStatuses = [],  # noqa: B006 - FastAPI copies it
    q: Search = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> RenderJobPage:
    async with _tx() as conn:
        return await _renders.list(
            conn,
            record_type=record_type,
            record_id=record_id,
            statuses=tuple(status_),
            q=q,
            cursor=cursor,
            limit=limit,
            authorize=_authorizer(request, principal),
        )


@renders_router.get(
    "/{render_job_id}",
    operation_id="reports_renders_get",
    response_model=RenderJobView,
    responses={**_FORBIDDEN, **_NOT_FOUND},
)
async def get_render(render_job_id: UUID, request: Request, principal: Principal) -> RenderJobView:
    async with _tx() as conn:
        return await _renders.get(conn, render_job_id, authorize=_authorizer(request, principal))


@renders_router.get(
    "/{render_job_id}/file",
    operation_id="reports_renders_file",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The report's PDF"},
        **_FORBIDDEN,
        **_NOT_FOUND,
        409: {"model": ReportErrorBody, "description": "REPORT_NOT_READY"},
    },
)
async def download_render(render_job_id: UUID, request: Request, principal: Principal) -> Response:
    async with _tx() as conn:
        report = await _renders.download(
            conn, render_job_id, authorize=_authorizer(request, principal)
        )
    return Response(
        content=report.data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@renders_router.post(
    "/{render_job_id}/rerender",
    operation_id="reports_renders_rerender",
    response_model=RenderJobView,
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_FORBIDDEN, **_NOT_FOUND},
)
async def rerender(render_job_id: UUID, request: Request, principal: Principal) -> RenderJobView:
    async with _tx() as conn:
        return await _renders.rerender(
            conn, principal.actor_id, render_job_id, authorize=_authorizer(request, principal)
        )


router.include_router(templates_router)
router.include_router(renders_router)
