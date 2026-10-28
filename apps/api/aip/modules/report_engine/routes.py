"""HTTP routes for report templates (REPORTS-01), mounted under ``/api/v1/reports/templates``.

Every route declares its permission with ``requires(...)`` (deny by default, ACCESS-01) and needs
an active tenant. Reading and previewing need ``report.template.view``; uploading, publishing,
retiring and deleting a draft need ``report.template.manage``. Each request runs in one
``with_tenant`` transaction, so another tenant's id is 404 ``TEMPLATE_NOT_FOUND`` (RLS hides it).
Explicit ``operation_id``s keep the generated client's hook names stable, and the ``422``
description is pinned so the OpenAPI schema does not drift across Python versions.

The preview returns the rendered sample as ``text/html`` under a sandboxing CSP and ``nosniff``,
with its assets inlined as ``data:`` URIs (a browser has no sibling files).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine.schemas import (
    ReportErrorBody,
    ReportTemplateDetail,
    ReportTemplatePage,
    ReportTemplateUpload,
)
from aip.modules.report_engine.service import TemplateService
from aip.modules.report_engine.template_package import TemplatePackageError, parse_package
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import requires
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

router = APIRouter(
    prefix="/reports/templates",
    tags=["reports"],
    dependencies=[Depends(require_active_tenant)],
)
_service = TemplateService()


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


@router.get(
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


@router.post(
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


@router.get(
    "/{template_id}",
    operation_id="reports_templates_get",
    response_model=ReportTemplateDetail,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("report.template.view"))],
)
async def get_template(template_id: UUID) -> ReportTemplateDetail:
    async with _tx() as conn:
        return await _service.detail(conn, template_id)


@router.post(
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


@router.post(
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


@router.delete(
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


@router.post(
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
