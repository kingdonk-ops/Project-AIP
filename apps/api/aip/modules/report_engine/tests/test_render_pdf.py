"""REPORTS-02 integration tests: the ``pdf`` worker renders, stores and records the PDF.

Real Postgres, a real object store (RustFS) and a real Gotenberg (the STACK-02 fixtures; in CI the
compose stack's sandboxed one). The queue is drained in-process with
``aip.platform.jobs.app.run_worker(queues=['pdf'], wait=False)`` as ``aip_jobs``; handlers run on
the ``aip_app`` engine exactly as in the worker (OPS-17).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from pypdf import PdfReader
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.report_engine.loader import run
from aip.modules.report_engine.template_package import load_package
from aip.modules.uploads.api import open_stored_file
from aip.platform.db.migrator import repo_root
from aip.platform.db.scope import run_as_system
from aip.platform.jobs.app import run_worker

from .conftest import ALICE, RenderEnv, add_project, su_fetch

RENDERS = "/api/v1/reports/renders"
TEMPLATES = "/api/v1/reports/templates"
ROOT = repo_root() / "config" / "report-templates"
EXAMPLE = ROOT / "project-summary" / "internal" / "v1"

pytestmark = pytest.mark.usefixtures("scope_users")


async def _load() -> None:
    out, err = io.StringIO(), io.StringIO()
    assert await run(ROOT, (TENANT_A_ID, TENANT_B_ID), out=out, err=err) == 0, err.getvalue()


async def _pending(db: TenantDb) -> int:
    rows = await su_fetch(
        db, "SELECT count(*) FROM report_render_jobs WHERE status IN ('queued', 'running')"
    )
    return int(str(rows[0][0]))


async def drain(db: TenantDb, env: RenderEnv) -> None:
    """Run a ``pdf`` worker until no render job is waiting (retries are scheduled ahead)."""
    for _ in range(40):
        await asyncio.wait_for(
            run_worker(
                queues=["pdf"],
                wait=False,
                conninfo=env.jobs_url,
                install_signal_handlers=False,
                listen_notify=False,
                fetch_job_polling_interval=0.2,
            ),
            timeout=180,
        )
        if await _pending(db) == 0:
            return
        await asyncio.sleep(1)
    raise AssertionError("render jobs did not finish")


async def _request(client: httpx.AsyncClient, project: UUID) -> dict[str, Any]:
    body = {
        "templateKey": "project-summary",
        "variant": "internal",
        "recordType": "project",
        "recordId": str(project),
    }
    response = await client.post(RENDERS, json=body, headers=ALICE)
    assert response.status_code == 202, response.text
    return response.json()


async def _get(client: httpx.AsyncClient, job_id: str) -> dict[str, Any]:
    response = await client.get(f"{RENDERS}/{job_id}", headers=ALICE)
    assert response.status_code == 200, response.text
    return response.json()


async def _pdf(db: TenantDb, file_id: str) -> bytes:
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        return await open_stored_file(conn, UUID(file_id))


def _text(pdf: bytes) -> str:
    return PdfReader(io.BytesIO(pdf)).pages[0].extract_text()


def _size(pdf: bytes) -> tuple[float, float]:
    box = PdfReader(io.BytesIO(pdf)).pages[0].mediabox
    return float(box.width), float(box.height)


async def _publish_v2(client: httpx.AsyncClient, **definition: Any) -> None:
    """Upload and publish ``project-summary/internal`` v2 (a copy of v1, changed as asked)."""
    package = load_package(EXAMPLE)
    marker = definition.pop("marker", None)
    body = package.body if marker is None else package.body + f"\n<p>{marker}</p>\n"
    upload = {
        "definition": {**json.loads(json.dumps(package.definition)), "version": 2, **definition},
        "body": body,
        "css": package.css,
        "sampleData": dict(package.sample_data),
        "assets": {n: base64.b64encode(a.data).decode() for n, a in package.assets.items()},
    }
    created = await client.post(TEMPLATES, json=upload, headers=ALICE)
    assert created.status_code == 201, created.text
    published = await client.post(f"{TEMPLATES}/{created.json()['id']}/publish", headers=ALICE)
    assert published.status_code == 200, published.text


async def test_the_worker_renders_stores_and_records_the_pdf(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, render_env: RenderEnv
) -> None:
    await _load()
    project = await add_project(db)
    job = await _request(client, project)
    await drain(db, render_env)

    done = await _get(client, job["id"])
    assert done["status"] == "succeeded", done
    assert len(done["pdfSha256"]) == 64 and len(done["htmlSha256"]) == 64
    assert done["renderedAt"].endswith("Z") and done["errorCode"] is None
    pdf = await _pdf(db, done["fileId"])
    assert pdf.startswith(b"%PDF")
    assert hashlib.sha256(pdf).hexdigest() == done["pdfSha256"]
    assert done["pdfSizeBytes"] == len(pdf)
    assert "KF-01" in _text(pdf)
    assert _size(pdf) == pytest.approx((595, 842), abs=1)

    events = await su_fetch(
        db, "SELECT payload FROM domain_events WHERE event_name = 'report.render_succeeded'"
    )
    assert len(events) == 1
    stored = await su_fetch(
        db, "SELECT source, purpose, project_id, scan_status FROM stored_files"
    )
    assert stored == [("generated", "report", project, "clean")]


async def test_a_landscape_template_gives_landscape_pages(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, render_env: RenderEnv
) -> None:
    await _load()
    project = await add_project(db)
    await _publish_v2(client, orientation="landscape")
    job = await _request(client, project)
    assert job["templateVersion"] == 2
    await drain(db, render_env)
    done = await _get(client, job["id"])
    assert done["status"] == "succeeded", done
    assert _size(await _pdf(db, done["fileId"])) == pytest.approx((842, 595), abs=1)


async def test_the_pinned_version_renders_and_a_rerender_reproduces_it(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, render_env: RenderEnv
) -> None:
    await _load()
    project = await add_project(db)
    job = await _request(client, project)
    assert job["templateVersion"] == 1
    await _publish_v2(client, marker="MARKER-V2")  # published before the worker runs
    await drain(db, render_env)

    done = await _get(client, job["id"])
    assert (done["status"], done["templateVersion"]) == ("succeeded", 1)
    text = _text(await _pdf(db, done["fileId"]))
    assert "KF-01" in text and "MARKER-V2" not in text

    again = await client.post(f"{RENDERS}/{job['id']}/rerender", headers=ALICE)
    assert again.status_code == 202, again.text
    second = again.json()
    assert second["id"] != job["id"]
    assert (second["templateVersion"], second["templateId"]) == (1, job["templateId"])
    assert (second["snapshotId"], second["rerenderOf"]) == (job["snapshotId"], job["id"])
    await drain(db, render_env)
    redone = await _get(client, second["id"])
    assert redone["status"] == "succeeded", redone
    assert redone["htmlSha256"] == done["htmlSha256"]
    assert "MARKER-V2" not in _text(await _pdf(db, redone["fileId"]))


async def test_an_unreachable_renderer_fails_after_three_tries(
    app: FastAPI,
    client: httpx.AsyncClient,
    db: TenantDb,
    render_env: RenderEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _load()
    project = await add_project(db)
    monkeypatch.setenv("GOTENBERG_URL", "http://127.0.0.1:9")  # nothing listens on the discard port
    job = await _request(client, project)
    await drain(db, render_env)

    done = await _get(client, job["id"])
    assert (done["status"], done["errorCode"], done["fileId"]) == (
        "failed",
        "RENDER_UNAVAILABLE",
        None,
    )
    attempts = await su_fetch(db, "SELECT attempts FROM jobs WHERE id = $1", UUID(job["opsJobId"]))
    assert attempts == [(3,)]
    failed = await su_fetch(
        db, "SELECT payload FROM domain_events WHERE event_name = 'report.render_failed'"
    )
    assert len(failed) == 1
    assert await su_fetch(db, "SELECT count(*) FROM stored_files") == [(0,)]
