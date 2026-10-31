"""Published interface of the report_engine module (REPORTS-01, REPORTS-02).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the read joins their transaction and RLS applies.

``ReportTemplatesApi.get_published`` gives the highest published version of a template key and
variant; ``get`` any version by id (a retired one too, so a pinned report can be re-rendered).
``render_html`` is the render contract: a template plus a plain data dict, resolved labels, a
locale, an IANA time zone and a unit system give a ``RenderedDocument`` (inert HTML, its asset
files and the ``PageSpec`` for Gotenberg) or a ``RenderContractError``. In R1 only report_engine's
own render job (REPORTS-02) calls it; no other module builds PDF HTML.

``ReportsApi.request_render`` (REPORTS-02) queues a PDF render of one record in the caller's
transaction: it freezes the record's data into a snapshot, pins the published template version and
enqueues the ``report_engine.render`` job, all or nothing. It is a system call with no policy
check, for report_engine's own subscribers and for callers that have already authorised the user.
``get_render_job`` reads a render job (``None`` when absent or another tenant's).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine.render import (
    Margins,
    PageSpec,
    RenderContractError,
    RenderedDocument,
    render_html,
)
from aip.modules.report_engine.render_service import RenderService
from aip.modules.report_engine.schemas import RenderJobView, TemplateRow
from aip.modules.report_engine.service import TemplateService

__all__ = [
    "Margins",
    "PageSpec",
    "RenderContractError",
    "RenderJobView",
    "RenderedDocument",
    "ReportTemplatesApi",
    "ReportsApi",
    "TemplateRow",
    "render_html",
]

_service = TemplateService()
_renders = RenderService()


class ReportTemplatesApi:
    """The template reads report_engine offers to other modules."""

    async def get_published(
        self, conn: AsyncConnection, key: str, variant: str
    ) -> TemplateRow | None:
        """The highest published version of ``(key, variant)`` in this tenant, or ``None``."""
        return await _service.get_published(conn, key, variant)

    async def get(self, conn: AsyncConnection, template_id: UUID) -> TemplateRow | None:
        """The template ``template_id`` in any status in this tenant, or ``None``."""
        return await _service.get(conn, template_id)


class ReportsApi:
    """Report renders (REPORTS-02)."""

    async def request_render(
        self,
        conn: AsyncConnection,
        *,
        template_key: str,
        record_type: str,
        record_id: UUID,
        variant: str,
        requested_by: UUID | None = None,
        idempotency_key: str | None = None,
        trigger_event_id: UUID | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> RenderJobView:
        """Queue a render of ``record_type``/``record_id`` with the published template (no policy
        check). Raises ``DomainError`` 404 ``TEMPLATE_NOT_FOUND``/``RECORD_NOT_FOUND`` or 422
        ``TEMPLATE_RECORD_TYPE_MISMATCH``/``UNKNOWN_RECORD_TYPE``/``SNAPSHOT_TOO_LARGE``."""
        return await _renders.request_render(
            conn,
            template_key=template_key,
            record_type=record_type,
            record_id=record_id,
            variant=variant,
            requested_by=requested_by,
            idempotency_key=idempotency_key,
            trigger_event_id=trigger_event_id,
            context=context,
        )

    async def get_render_job(
        self, conn: AsyncConnection, render_job_id: UUID
    ) -> RenderJobView | None:
        """The render job ``render_job_id`` in this tenant, or ``None``."""
        return await _renders.find(conn, render_job_id)
