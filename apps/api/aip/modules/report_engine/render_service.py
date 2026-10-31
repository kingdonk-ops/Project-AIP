"""Requesting report renders (REPORTS-02).

``RenderService`` runs in the caller's ``with_tenant`` transaction. ``request_render``:

(a) a known ``idempotency_key`` returns the existing job (the ``UNIQUE`` index settles a race: on
    a unique violation the row is read again and returned);
(b) the published template of ``(template_key, variant)``, else 404 ``TEMPLATE_NOT_FOUND``; its
    ``record_type`` must be the requested one, else 422 ``TEMPLATE_RECORD_TYPE_MISMATCH``;
(c) the record type's provider, else 422 ``UNKNOWN_RECORD_TYPE``; ``RecordNotFound`` from it is 404
    ``RECORD_NOT_FOUND``. With an ``authorize`` callback (the HTTP route) the caller must then hold
    ``report.create`` and the provider's view permission on the record's project, else 403 with
    nothing written; without one (``ReportsApi``, a system call) there is no policy check;
(d) the snapshot (``snapshots.build_snapshot``), the ``queued`` render job pinned to the template
    version and the snapshot, and ``ops.enqueue("report_engine.render", {"renderJobId"},
    idempotency_key="report-render:<id>")`` whose job id is kept as ``ops_job_id``.

All of it is one transaction: a rollback leaves no snapshot, no render job, no ``jobs`` row and no
queue row (ADR 0003). ``rerender`` queues a new job with the same pinned template version and
snapshot (never the latest version, even if the pinned one is now retired).

REPORTS-04: the job keeps the provider's record ``label`` (``record_label``, at most 300
characters) for the register, which ``list`` searches (``q``) and filters by ``statuses``.
``download`` reads a succeeded job's PDF through ``aip.modules.uploads.api.open_stored_file`` on
the caller's connection (never a storage URL), checks the bytes against the job's ``pdf_sha256``
and emits ``report.downloaded`` in the same transaction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.ops import api as ops
from aip.modules.report_engine import repository as repo
from aip.modules.report_engine.events import REPORT_DOWNLOADED, ReportDownloaded
from aip.modules.report_engine.jobs import RENDER_JOB_TYPE
from aip.modules.report_engine.providers import (
    ProviderEntry,
    RecordNotFound,
    call_provider,
    get_provider,
)
from aip.modules.report_engine.providers import project as project_provider
from aip.modules.report_engine.schemas import RenderJobPage, RenderJobView, TemplateRow
from aip.modules.report_engine.service import TemplateService, decode_cursor, encode_cursor
from aip.modules.report_engine.snapshots import build_snapshot
from aip.modules.uploads.api import (
    StoredFileIntegrityError,
    StoredFileNotFoundError,
    open_stored_file,
)
from aip.platform.access import Forbidden
from aip.platform.context import get_context, new_request_id
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = ["REPORT_CREATE", "REPORT_VIEW", "Authorizer", "RenderService", "ReportFile"]

REPORT_VIEW: Final = "report.view"
REPORT_CREATE: Final = "report.create"
_UNIQUE_VIOLATION: Final = "23505"
MAX_LABEL: Final = 300

# ``authorize(permission, project_id)``: whether the caller holds ``permission`` on that project.
Authorizer = Callable[[str, UUID | None], Awaitable[bool]]

project_provider.install()


def _job_not_found(render_job_id: UUID) -> DomainError:
    return DomainError(404, "RENDER_JOB_NOT_FOUND", detail=f"render job {render_job_id}")


def _label(label: str | None) -> str | None:
    """The provider's label trimmed and cut to ``MAX_LABEL`` characters (``None`` when blank)."""
    trimmed = (label or "").strip()[:MAX_LABEL].strip()
    return trimmed or None


@dataclass(frozen=True, slots=True)
class ReportFile:
    """A succeeded render's PDF, read through uploads and checked against the job's sha256."""

    job: RenderJobView
    data: bytes

    @property
    def filename(self) -> str:
        return f"{self.job.template_key}-{self.job.variant}-{self.job.record_id}.pdf"


async def _require(
    authorize: Authorizer | None, codes: tuple[str, ...], project: UUID | None
) -> None:
    """Raise ``Forbidden`` unless ``authorize`` allows every code (no check for a system call)."""
    if authorize is None:
        return
    for code in codes:
        if not await authorize(code, project):
            raise Forbidden(code)


class RenderService:
    """Stateless; every method runs on the caller's tenant-bound connection."""

    def __init__(self) -> None:
        self._templates = TemplateService()

    async def request_render(
        self,
        conn: AsyncConnection,
        *,
        template_key: str,
        record_type: str,
        record_id: UUID,
        variant: str,
        requested_by: UUID | None,
        idempotency_key: str | None = None,
        trigger_event_id: UUID | None = None,
        context: Mapping[str, Any] | None = None,
        authorize: Authorizer | None = None,
    ) -> RenderJobView:
        if idempotency_key is not None:
            existing = await repo.find_job_by_idempotency_key(conn, idempotency_key)
            if existing is not None:
                await _require(authorize, (REPORT_VIEW,), existing["project_id"])
                return RenderJobView.model_validate(existing)

        template = await self._templates.get_published(conn, template_key, variant)
        if template is None:
            raise DomainError(404, "TEMPLATE_NOT_FOUND", detail=f"{template_key}/{variant}")
        if template.record_type != record_type:
            raise DomainError(422, "TEMPLATE_RECORD_TYPE_MISMATCH")
        entry = get_provider(record_type)
        if entry is None:
            raise DomainError(422, "UNKNOWN_RECORD_TYPE")
        try:
            source = await call_provider(entry, conn, record_id, context=context)
        except RecordNotFound:
            raise DomainError(404, "RECORD_NOT_FOUND") from None
        await _require(authorize, (REPORT_CREATE, entry.view_permission), source.project_id)

        snapshot = await build_snapshot(
            conn, template, source, record_id=record_id, created_by=requested_by
        )
        values = {
            "template_id": template.id,
            "template_key": template.key,
            "template_version": template.version,
            "variant": template.variant,
            "record_type": record_type,
            "record_id": record_id,
            "record_label": _label(source.label),
            "project_id": source.project_id,
            "snapshot_id": snapshot.id,
            "data_hash": snapshot.data_hash,
            "idempotency_key": idempotency_key,
            "trigger_event_id": trigger_event_id,
            "requested_by": requested_by,
        }
        if idempotency_key is None:
            return await self._queue(conn, values)
        try:
            async with conn.begin_nested():
                return await self._queue(conn, values)
        except IntegrityError as exc:  # a concurrent request with the same key won the race
            if getattr(exc.orig, "sqlstate", None) != _UNIQUE_VIOLATION:
                raise
            existing = await repo.find_job_by_idempotency_key(conn, idempotency_key)
            if existing is None:
                raise
            return RenderJobView.model_validate(existing)

    async def rerender(
        self,
        conn: AsyncConnection,
        actor: UUID | None,
        render_job_id: UUID,
        *,
        authorize: Authorizer | None = None,
    ) -> RenderJobView:
        """A new job with the same pinned template version and snapshot as ``render_job_id``."""
        first = await repo.get_job(conn, render_job_id)
        if first is None:
            raise _job_not_found(render_job_id)
        entry: ProviderEntry | None = get_provider(first["record_type"])
        codes = (REPORT_CREATE,) if entry is None else (REPORT_CREATE, entry.view_permission)
        await _require(authorize, codes, first["project_id"])
        template: TemplateRow | None = await self._templates.get(conn, first["template_id"])
        if template is None:
            raise DomainError(404, "TEMPLATE_NOT_FOUND")
        values = {
            key: first[key]
            for key in (
                "template_id",
                "template_key",
                "template_version",
                "variant",
                "record_type",
                "record_id",
                "record_label",
                "project_id",
                "snapshot_id",
                "data_hash",
            )
        }
        values["requested_by"] = actor
        values["rerender_of"] = first["rerender_of"] or first["id"]
        return await self._queue(conn, values)

    async def get(
        self,
        conn: AsyncConnection,
        render_job_id: UUID,
        *,
        authorize: Authorizer | None = None,
    ) -> RenderJobView:
        row = await repo.get_job(conn, render_job_id)
        if row is None:
            raise _job_not_found(render_job_id)
        await _require(authorize, (REPORT_VIEW,), row["project_id"])
        return RenderJobView.model_validate(row)

    async def find(self, conn: AsyncConnection, render_job_id: UUID) -> RenderJobView | None:
        row = await repo.get_job(conn, render_job_id)
        return None if row is None else RenderJobView.model_validate(row)

    async def list(
        self,
        conn: AsyncConnection,
        *,
        record_type: str | None = None,
        record_id: UUID | None = None,
        statuses: tuple[str, ...] = (),
        q: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        authorize: Authorizer | None = None,
    ) -> RenderJobPage:
        """Newest first; jobs on a project the caller may not view are left out."""
        before = None if cursor is None else decode_cursor(cursor)
        rows = await repo.list_jobs(
            conn,
            record_type=record_type,
            record_id=record_id,
            statuses=statuses,
            q=q,
            before=before,
            limit=limit + 1,
        )
        more = len(rows) > limit
        rows = rows[:limit]
        visible = [
            row
            for row in rows
            if authorize is None or await authorize(REPORT_VIEW, row["project_id"])
        ]
        return RenderJobPage(
            items=[RenderJobView.model_validate(row) for row in visible],
            next_cursor=encode_cursor(rows[-1]["id"]) if more else None,
        )

    async def download(
        self,
        conn: AsyncConnection,
        render_job_id: UUID,
        *,
        authorize: Authorizer | None = None,
    ) -> ReportFile:
        """A succeeded job's PDF (``report.view`` on its project); emits ``report.downloaded``."""
        job = await self.get(conn, render_job_id, authorize=authorize)
        if job.status != "succeeded" or job.file_id is None or job.pdf_sha256 is None:
            raise DomainError(409, "REPORT_NOT_READY", detail=f"render job is {job.status}")
        try:
            data = await open_stored_file(conn, job.file_id)
        except StoredFileNotFoundError:
            raise DomainError(404, "REPORT_FILE_NOT_FOUND") from None
        if hashlib.sha256(data).hexdigest() != job.pdf_sha256:
            raise StoredFileIntegrityError(f"render job {job.id}: the stored PDF is not the report")
        payload = ReportDownloaded(
            render_job_id=job.id,
            file_id=job.file_id,
            record_type=job.record_type,
            record_id=job.record_id,
            pdf_sha256=job.pdf_sha256,
        ).model_dump(mode="json")
        await emit(conn, REPORT_DOWNLOADED, 1, Aggregate("report_render_job", job.id), payload)
        return ReportFile(job=job, data=data)

    async def _queue(self, conn: AsyncConnection, values: dict[str, Any]) -> RenderJobView:
        render_job_id = UUID(new_request_id())
        await repo.insert_job(
            conn,
            {
                "id": render_job_id,
                "tenant_id": get_context().tenant_id,
                "status": "queued",
                **values,
            },
        )
        job = await ops.enqueue(
            conn,
            RENDER_JOB_TYPE,
            {"renderJobId": str(render_job_id)},
            idempotency_key=f"report-render:{render_job_id}",
        )
        await repo.update_job(conn, render_job_id, {"ops_job_id": job.id})
        row = await repo.get_job(conn, render_job_id)  # with the template's name (REPORTS-04)
        return RenderJobView.model_validate(row)
