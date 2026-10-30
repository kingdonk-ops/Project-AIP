"""Background jobs for report_engine (Procrastinate, ADR 0003, ADR 0016): the PDF render job.

``report_engine.render`` runs on the ``pdf`` queue (its own worker, ``--queues pdf``, the only one
that reaches the sandboxed Gotenberg). ``render_report(conn, job)`` runs on the connection OPS-17
provides (the ``aip_app`` engine, bound to the job's tenant; it acts as the tenant-wide ``system``
principal, as background work does) and is idempotent on the render job id:

1. Lock the render job named by ``job.payload["renderJobId"]``. Already ``succeeded``: return its
   ``file_id`` and do nothing else. Already ``failed``: return.
2. Set ``running``; load the pinned template version (by id, never the latest, a retired one too)
   and the snapshot.
3. Render the HTML through the REPORTS-01 contract with the snapshot's record, labels, locale, zone
   and unit system, plus ``report = {renderJobId, issuedAt, templateVersion, dataHash}`` (and
   ``generatedAt`` = ``issuedAt`` for the v1 project summary). A re-render uses its first job's
   id and time, so it reproduces that document. Each pinned file is read through uploads, checked
   against the snapshot's sha256 and passed as the asset ``file-<fileId>.<ext>``.
4. Print it with ``get_pdf_renderer()`` on the template's paper, store it with
   ``uploads.store_generated_file`` (idempotency key ``report-render:<id>``) and check the stored
   sha256 equals the PDF's (never record a hash of bytes that were not stored).
5. Set ``succeeded`` with the file, its sha256, size and ``rendered_at``, and emit
   ``report.render_succeeded`` in the same transaction.

Failures: a ``RenderContractError`` (``RENDER_CONTRACT_VIOLATION``), a changed source file
(``SOURCE_FILE_CHANGED``) or an oversized PDF (``PDF_TOO_LARGE``) cannot be fixed by a retry, so
the job ends ``failed`` with ``report.render_failed`` and returns. A renderer timeout or error is
re-raised so Procrastinate retries; on the last try it ends ``failed`` ``RENDER_UNAVAILABLE``
instead. Logs carry the render job id and error code, never snapshot data.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.ops import api as ops
from aip.modules.report_engine import repository as repo
from aip.modules.report_engine.events import (
    REPORT_RENDER_FAILED,
    REPORT_RENDER_SUCCEEDED,
    RenderFailed,
    RenderSucceeded,
)
from aip.modules.report_engine.render import (
    RenderableTemplate,
    RenderContractError,
    page_options,
    render_html,
)
from aip.modules.report_engine.service import TemplateService
from aip.modules.report_engine.snapshots import Snapshot
from aip.modules.uploads.api import (
    StoredFileIntegrityError,
    StoredFileNotFoundError,
    StoredFileRef,
    open_stored_file,
    store_generated_file,
)
from aip.platform.capabilities import (
    PdfRenderer,
    RenderError,
    RenderTimeoutError,
    RenderTooLargeError,
    get_pdf_renderer,
)
from aip.platform.events import Aggregate, emit

__all__ = [
    "RENDER_JOB_TYPE",
    "RENDER_MAX_ATTEMPTS",
    "RenderDeps",
    "RenderIntegrityError",
    "RenderRunner",
    "asset_name",
    "default_deps",
    "render_report",
]

logger = logging.getLogger(__name__)

RENDER_JOB_TYPE: Final = "report_engine.render"
RENDER_MAX_ATTEMPTS: Final = 3
RENDER_TIMEOUT_S: Final = 120
_AS_SYSTEM = text("SELECT set_config('app.principal_kind', 'system', true)")
_EXTENSIONS: Final[Mapping[str, str]] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
}

Row = dict[str, Any]


class RenderIntegrityError(RuntimeError):
    """The stored file's sha256 is not the sha256 of the PDF just rendered."""


class _SourceFileChangedError(Exception):
    pass


def asset_name(file_id: str, content_type: str) -> str:
    """The asset file name a pinned stored file gets: ``file-<fileId>.<ext>``."""
    return f"file-{file_id}.{_EXTENSIONS.get(content_type, 'bin')}"


def _utc_z(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class RenderDeps:
    """What the handler talks to; the unit tests replace each with a fake."""

    act_as_system: Callable[[AsyncConnection], Awaitable[None]]
    lock_job: Callable[[AsyncConnection, UUID], Awaitable[Row | None]]
    get_job: Callable[[AsyncConnection, UUID], Awaitable[Row | None]]
    update_job: Callable[[AsyncConnection, UUID, dict[str, Any]], Awaitable[Row]]
    get_template: Callable[[AsyncConnection, UUID], Awaitable[RenderableTemplate | None]]
    get_snapshot: Callable[[AsyncConnection, UUID], Awaitable[Snapshot | None]]
    open_file: Callable[[AsyncConnection, UUID], Awaitable[bytes]]
    store_file: Callable[..., Awaitable[StoredFileRef]]
    renderer: Callable[[], PdfRenderer]
    emit: Callable[[AsyncConnection, str, int, Aggregate, Mapping[str, Any]], Awaitable[object]]
    now: Callable[[], object]


async def _act_as_system(conn: AsyncConnection) -> None:
    await conn.execute(_AS_SYSTEM)


async def _get_snapshot(conn: AsyncConnection, snapshot_id: UUID) -> Snapshot | None:
    row = await repo.get_snapshot(conn, snapshot_id)
    return None if row is None else Snapshot.from_row(row)


async def _emit(
    conn: AsyncConnection, name: str, version: int, aggregate: Aggregate, payload: Mapping[str, Any]
) -> object:
    return await emit(conn, name, version, aggregate, payload)


def default_deps() -> RenderDeps:
    templates = TemplateService()
    return RenderDeps(
        act_as_system=_act_as_system,
        lock_job=repo.lock_job,
        get_job=repo.get_job,
        update_job=repo.update_job,
        get_template=templates.get,
        get_snapshot=_get_snapshot,
        open_file=open_stored_file,
        store_file=store_generated_file,
        renderer=get_pdf_renderer,
        emit=_emit,
        now=func.now,
    )


class RenderRunner:
    """One try of one render job (see the module docstring)."""

    def __init__(self, deps: RenderDeps) -> None:
        self.deps = deps

    async def run(self, conn: AsyncConnection, job: ops.JobView) -> str | None:
        d = self.deps
        await d.act_as_system(conn)
        render_job_id = UUID(str(job.payload["renderJobId"]))
        row = await d.lock_job(conn, render_job_id)
        if row is None:
            logger.warning("render job %s not found; nothing to do", render_job_id)
            return None
        if row["status"] == "succeeded":
            return str(row["file_id"])
        if row["status"] == "failed":
            return None

        row = await d.update_job(conn, render_job_id, {"status": "running", "error_code": None})
        template = await d.get_template(conn, row["template_id"])
        snapshot = await d.get_snapshot(conn, row["snapshot_id"])
        if template is None or snapshot is None:
            return await self._fail(conn, row, "RENDER_CONTRACT_VIOLATION")

        try:
            assets = await self._pinned_assets(conn, snapshot)
            document = render_html(
                template,
                {**snapshot.record, **await self._report_fields(conn, row)},
                labels=snapshot.labels,
                locale=snapshot.locale,
                time_zone=snapshot.time_zone,
                unit_system=snapshot.unit_system,
                extra_assets=assets,
            )
        except RenderContractError as exc:
            logger.info("render job %s: template contract error %s", render_job_id, exc.code)
            return await self._fail(conn, row, "RENDER_CONTRACT_VIOLATION")
        except _SourceFileChangedError:
            return await self._fail(conn, row, "SOURCE_FILE_CHANGED")
        html_sha256 = hashlib.sha256(document.html.encode("utf-8")).hexdigest()
        row = await d.update_job(conn, render_job_id, {"html_sha256": html_sha256})

        try:
            pdf = await d.renderer().render_html(
                document.html, assets=document.assets, page=page_options(document.page)
            )
        except RenderTooLargeError:
            return await self._fail(conn, row, "PDF_TOO_LARGE")
        except (RenderTimeoutError, RenderError) as exc:
            if job.attempts >= RENDER_MAX_ATTEMPTS:
                return await self._fail(conn, row, "RENDER_UNAVAILABLE")
            logger.warning(
                "render job %s try %d: renderer unavailable (%s); retrying",
                render_job_id,
                job.attempts,
                type(exc).__name__,
            )
            raise

        pdf_sha256 = hashlib.sha256(pdf).hexdigest()
        ref = await d.store_file(
            conn,
            data=pdf,
            filename=f"{row['template_key']}-{row['variant']}-{row['record_id']}.pdf",
            content_type="application/pdf",
            purpose="report",
            idempotency_key=f"report-render:{render_job_id}",
            project_id=row["project_id"],
            created_by=row["requested_by"],
        )
        if ref.sha256 != pdf_sha256:
            raise RenderIntegrityError(f"render job {render_job_id}: stored sha256 differs")

        row = await d.update_job(
            conn,
            render_job_id,
            {
                "status": "succeeded",
                "file_id": ref.id,
                "pdf_sha256": pdf_sha256,
                "pdf_size_bytes": len(pdf),
                "rendered_at": d.now(),
            },
        )
        payload = RenderSucceeded(
            render_job_id=row["id"],
            template_key=row["template_key"],
            template_version=row["template_version"],
            variant=row["variant"],
            record_type=row["record_type"],
            record_id=row["record_id"],
            data_hash=row["data_hash"],
            file_id=ref.id,
            pdf_sha256=pdf_sha256,
        ).model_dump(mode="json")
        await d.emit(
            conn, REPORT_RENDER_SUCCEEDED, 1, Aggregate("report_render_job", row["id"]), payload
        )
        return str(ref.id)

    async def _report_fields(self, conn: AsyncConnection, row: Row) -> dict[str, Any]:
        """``report`` (and ``generatedAt``) for the template; a re-render uses its first job."""
        first = row
        if row["rerender_of"] is not None:
            found = await self.deps.get_job(conn, row["rerender_of"])
            first = found if found is not None else row
        issued_at = _utc_z(first["created_at"])
        return {
            "report": {
                "renderJobId": str(first["id"]),
                "issuedAt": issued_at,
                "templateVersion": row["template_version"],
                "dataHash": row["data_hash"],
            },
            "generatedAt": issued_at,
        }

    async def _pinned_assets(
        self, conn: AsyncConnection, snapshot: Snapshot
    ) -> dict[str, tuple[str, bytes]]:
        assets: dict[str, tuple[str, bytes]] = {}
        for entry in snapshot.files:
            file_id, content_type = str(entry["fileId"]), str(entry["contentType"])
            try:
                data = await self.deps.open_file(conn, UUID(file_id))
            except (StoredFileNotFoundError, StoredFileIntegrityError):
                raise _SourceFileChangedError from None
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise _SourceFileChangedError
            assets[asset_name(file_id, content_type)] = (content_type, data)
        return assets

    async def _fail(self, conn: AsyncConnection, row: Row, code: str) -> None:
        logger.info("render job %s failed: %s", row["id"], code)
        row = await self.deps.update_job(conn, row["id"], {"status": "failed", "error_code": code})
        payload = RenderFailed(
            render_job_id=row["id"],
            template_key=row["template_key"],
            variant=row["variant"],
            record_type=row["record_type"],
            record_id=row["record_id"],
            error_code=code,
        ).model_dump(mode="json")
        await self.deps.emit(
            conn, REPORT_RENDER_FAILED, 1, Aggregate("report_render_job", row["id"]), payload
        )
        return None


async def render_report(conn: AsyncConnection, job: ops.JobView) -> str | None:
    """The ``report_engine.render`` handler."""
    return await RenderRunner(default_deps()).run(conn, job)


if RENDER_JOB_TYPE not in ops.registered_types():
    ops.register(
        RENDER_JOB_TYPE,
        render_report,
        queue="pdf",
        timeout_s=RENDER_TIMEOUT_S,
        max_attempts=RENDER_MAX_ATTEMPTS,
        max_per_tenant=2,
    )
