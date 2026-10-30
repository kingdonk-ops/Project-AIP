"""REPORTS-02 unit tests: the render job handler with fakes (no database, no Gotenberg).

``RenderRunner`` takes its collaborators as ``RenderDeps``; here the render job store, the
template, the snapshot, the PDF renderer, the uploads calls and ``emit`` are all in memory.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.ops.api import JobStatus, JobView
from aip.modules.report_engine.jobs import (
    RENDER_MAX_ATTEMPTS,
    RenderDeps,
    RenderIntegrityError,
    RenderRunner,
    asset_name,
)
from aip.modules.report_engine.render import RenderableTemplate
from aip.modules.report_engine.snapshots import Snapshot, snapshot_body
from aip.modules.report_engine.template_package import TemplatePackage, load_package
from aip.modules.uploads.api import StoredFileRef
from aip.platform.capabilities import PageOptions, PdfRenderer, RenderTimeoutError
from aip.platform.db.migrator import repo_root
from aip.platform.events import Aggregate

EXAMPLE = repo_root() / "config" / "report-templates" / "project-summary" / "internal" / "v1"
TENANT = UUID("00000000-0000-4000-8000-00000000000a")
RECORD = UUID("00000000-0000-4000-8000-0000000000a1")
PDF = b"%PDF-1.7\n% fake\n%%EOF\n"
CONN = cast(AsyncConnection, object())
NOW = datetime(2026, 10, 31, 1, 0, tzinfo=UTC)


@dataclass
class PolicyBreaker:
    """A template whose output breaks the HTML policy (a data value as a link target)."""

    body: str = '<a href="{{ link }}">open</a>'
    css: str = ""
    definition: Mapping[str, Any] = field(
        default_factory=lambda: {
            "paper": "A4",
            "orientation": "portrait",
            "marginsMm": {"top": 10, "right": 10, "bottom": 10, "left": 10},
            "termKeys": [],
        }
    )

    def asset_files(self) -> dict[str, tuple[str, bytes]]:
        return {}


class FakeRenderer:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, bytes], PageOptions | None]] = []

    async def render_html(
        self,
        html: str,
        *,
        assets: Mapping[str, bytes] | None = None,
        page: PageOptions | None = None,
    ) -> bytes:
        self.calls.append((html, dict(assets or {}), page))
        if self.error is not None:
            raise self.error
        return PDF


class World:
    """The in-memory state the fakes share."""

    def __init__(
        self,
        template: RenderableTemplate,
        record: Mapping[str, Any],
        *,
        files: list[dict[str, Any]] | None = None,
        stored: Mapping[UUID, bytes] | None = None,
        renderer: FakeRenderer | None = None,
        wrong_store_hash: bool = False,
    ) -> None:
        self.template = template
        self.render_job_id = uuid4()
        self.template_id = uuid4()
        self.snapshot_id = uuid4()
        keys = list(template.definition.get("termKeys", []))
        body = snapshot_body(
            record_type="project",
            record_id=RECORD,
            record_version=1,
            record=record,
            labels={k: k for k in keys},
            locale="en-AU",
            time_zone="Australia/Perth",
            unit_system="metric",
            files=files or [],
        )
        self.snapshot = Snapshot(
            id=self.snapshot_id,
            record_type="project",
            record_id=RECORD,
            record_version=1,
            project_id=RECORD,
            data=body,
            data_hash="a" * 64,
            size_bytes=1,
            created_at=NOW,
        )
        self.jobs: dict[UUID, dict[str, Any]] = {
            self.render_job_id: {
                "id": self.render_job_id,
                "tenant_id": TENANT,
                "template_id": self.template_id,
                "template_key": "project-summary",
                "template_version": 1,
                "variant": "internal",
                "record_type": "project",
                "record_id": RECORD,
                "project_id": RECORD,
                "snapshot_id": self.snapshot_id,
                "data_hash": "a" * 64,
                "status": "queued",
                "requested_by": None,
                "rerender_of": None,
                "html_sha256": None,
                "file_id": None,
                "pdf_sha256": None,
                "pdf_size_bytes": None,
                "error_code": None,
                "rendered_at": None,
                "created_at": NOW,
            }
        }
        self.stored = dict(stored or {})
        self.renderer = renderer or FakeRenderer()
        self.wrong_store_hash = wrong_store_hash
        self.store_calls: list[dict[str, Any]] = []
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.system = False

    @property
    def job(self) -> dict[str, Any]:
        return self.jobs[self.render_job_id]

    def deps(self) -> RenderDeps:
        async def act_as_system(conn: AsyncConnection) -> None:
            self.system = True

        async def lock_job(conn: AsyncConnection, id: UUID) -> dict[str, Any] | None:
            row = self.jobs.get(id)
            return None if row is None else dict(row)

        async def update_job(
            conn: AsyncConnection, id: UUID, patch: dict[str, Any]
        ) -> dict[str, Any]:
            self.jobs[id].update(patch)
            return dict(self.jobs[id])

        async def get_template(conn: AsyncConnection, id: UUID) -> RenderableTemplate | None:
            return self.template if id == self.template_id else None

        async def get_snapshot(conn: AsyncConnection, id: UUID) -> Snapshot | None:
            return self.snapshot if id == self.snapshot_id else None

        async def open_file(conn: AsyncConnection, id: UUID) -> bytes:
            return self.stored[id]

        async def store_file(conn: AsyncConnection, **kwargs: Any) -> StoredFileRef:
            self.store_calls.append(kwargs)
            data: bytes = kwargs["data"]
            digest = hashlib.sha256(data + (b"x" if self.wrong_store_hash else b"")).hexdigest()
            return StoredFileRef(
                id=uuid4(),
                project_id=kwargs.get("project_id"),
                filename=kwargs["filename"],
                content_type=kwargs["content_type"],
                size_bytes=len(data),
                sha256=digest,
                source="generated",
                purpose=kwargs["purpose"],
                created_at=NOW,
            )

        def renderer() -> PdfRenderer:
            return self.renderer

        async def emit(
            conn: AsyncConnection,
            name: str,
            version: int,
            aggregate: Aggregate,
            payload: Mapping[str, Any],
        ) -> object:
            self.events.append((name, dict(payload)))
            return None

        return RenderDeps(
            act_as_system=act_as_system,
            lock_job=lock_job,
            get_job=lock_job,
            update_job=update_job,
            get_template=get_template,
            get_snapshot=get_snapshot,
            open_file=open_file,
            store_file=store_file,
            renderer=renderer,
            emit=emit,
            now=lambda: NOW,
        )

    def ops_job(self, attempts: int) -> JobView:
        return JobView(
            id=uuid4(),
            tenant_id=TENANT,
            job_type="report_engine.render",
            status=JobStatus.RUNNING,
            idempotency_key=f"report-render:{self.render_job_id}",
            correlation_id=uuid4(),
            attempts=attempts,
            payload={"renderJobId": str(self.render_job_id)},
            result_ref=None,
            error=None,
            requested_by=None,
            procrastinate_job_id=1,
            created_at=NOW,
            updated_at=NOW,
        )

    async def run(self, attempts: int = 1) -> str | None:
        return await RenderRunner(self.deps()).run(CONN, self.ops_job(attempts))


def _package() -> TemplatePackage:
    return load_package(EXAMPLE)


PROJECT = {
    "project": {
        "id": str(RECORD),
        "code": "KF-01",
        "name": "Karratha compressor",
        "status": "active",
        "timezone": "Australia/Perth",
        "region": None,
        "createdAt": "2026-10-18T02:30:00Z",
    }
}


async def test_a_render_stores_the_pdf_and_emits_succeeded() -> None:
    world = World(_package(), PROJECT)
    file_id = await world.run()

    assert world.system
    job = world.job
    assert job["status"] == "succeeded" and file_id == str(job["file_id"])
    assert job["pdf_sha256"] == hashlib.sha256(PDF).hexdigest()
    assert job["pdf_size_bytes"] == len(PDF) and job["rendered_at"] == NOW
    assert job["html_sha256"] == hashlib.sha256(world.renderer.calls[0][0].encode()).hexdigest()
    (call,) = world.store_calls
    assert call["idempotency_key"] == f"report-render:{world.render_job_id}"
    assert call["filename"] == f"project-summary-internal-{RECORD}.pdf"
    assert (call["content_type"], call["purpose"]) == ("application/pdf", "report")
    html, assets, page = world.renderer.calls[0]
    assert "KF-01" in html and set(assets) == {"logo.png"}
    assert page == PageOptions(210, 297, False, 15, 12, 18, 12)
    assert [name for name, _ in world.events] == ["report.render_succeeded"]
    assert world.events[0][1]["pdfSha256"] == job["pdf_sha256"]


async def test_a_renderer_timeout_retries_until_the_last_try() -> None:
    world = World(_package(), PROJECT, renderer=FakeRenderer(RenderTimeoutError("slow")))
    with pytest.raises(RenderTimeoutError):
        await world.run(attempts=1)

    world = World(_package(), PROJECT, renderer=FakeRenderer(RenderTimeoutError("slow")))
    assert await world.run(attempts=RENDER_MAX_ATTEMPTS) is None
    assert (world.job["status"], world.job["error_code"]) == ("failed", "RENDER_UNAVAILABLE")
    assert [name for name, _ in world.events] == ["report.render_failed"]
    assert world.events[0][1]["errorCode"] == "RENDER_UNAVAILABLE"
    assert world.store_calls == []


async def test_a_template_that_breaks_the_html_policy_fails_without_rendering() -> None:
    world = World(PolicyBreaker(), {"link": "javascript:alert(1)"})
    assert await world.run(attempts=1) is None
    assert (world.job["status"], world.job["error_code"]) == (
        "failed",
        "RENDER_CONTRACT_VIOLATION",
    )
    assert world.renderer.calls == []
    assert [name for name, _ in world.events] == ["report.render_failed"]


async def test_an_already_succeeded_job_is_not_rendered_again() -> None:
    world = World(_package(), PROJECT)
    stored = uuid4()
    world.job.update(status="succeeded", file_id=stored, pdf_sha256="b" * 64)
    assert await world.run() == str(stored)
    assert world.renderer.calls == [] and world.store_calls == [] and world.events == []


async def test_an_already_failed_job_is_left_alone() -> None:
    world = World(_package(), PROJECT)
    world.job.update(status="failed", error_code="PDF_TOO_LARGE")
    assert await world.run() is None
    assert world.renderer.calls == [] and world.job["error_code"] == "PDF_TOO_LARGE"


async def test_a_stored_hash_that_differs_from_the_pdf_raises() -> None:
    world = World(_package(), PROJECT, wrong_store_hash=True)
    with pytest.raises(RenderIntegrityError):
        await world.run()
    assert world.job["status"] != "succeeded"
    assert world.events == []


async def test_pinned_files_become_assets_and_a_changed_file_fails() -> None:
    photo_id = uuid4()
    photo = b"\x89PNG\r\n\x1a\nphoto"
    entry = {
        "fileId": str(photo_id),
        "role": "photo",
        "sha256": hashlib.sha256(photo).hexdigest(),
        "sizeBytes": len(photo),
        "contentType": "image/png",
    }
    world = World(_package(), PROJECT, files=[entry], stored={photo_id: photo})
    await world.run()
    name = asset_name(str(photo_id), "image/png")
    assert name == f"file-{photo_id}.png"
    assert world.renderer.calls[0][1][name] == photo

    changed = World(_package(), PROJECT, files=[entry], stored={photo_id: photo + b"!"})
    assert await changed.run() is None
    assert (changed.job["status"], changed.job["error_code"]) == ("failed", "SOURCE_FILE_CHANGED")
    assert changed.renderer.calls == []


async def test_a_landscape_template_asks_for_landscape_paper() -> None:
    package = _package()
    landscape = PolicyBreaker(
        body="<p>{{ project.code }}</p>",
        definition={**package.definition, "orientation": "landscape", "termKeys": []},
    )
    world = World(landscape, PROJECT)
    await world.run()
    page = world.renderer.calls[0][2]
    assert page is not None and page.landscape and page.paper_width_mm == 210
