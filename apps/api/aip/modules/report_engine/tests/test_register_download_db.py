"""REPORTS-04 integration tests: the report register's list filters and the authorised download.

Real Postgres and a real object store (RustFS, the STACK-02 fixture); no Gotenberg. A render is
requested through the API and then completed the way the REPORTS-02 handler does it: a small PDF
is stored with ``store_generated_file`` and the job is marked ``succeeded`` with its file and
sha256. The download must stream exactly those bytes through the API and never a storage URL.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb
from tests.platform.capabilities.conftest import S3Backend

from aip.modules.report_engine.loader import run
from aip.modules.uploads.api import store_generated_file
from aip.platform.db.migrator import repo_root
from aip.platform.db.scope import run_as_system

from .conftest import ALICE, BOB, DAVE, add_project, su_execute, su_fetch

RENDERS = "/api/v1/reports/renders"
ROOT = repo_root() / "config" / "report-templates"
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

pytestmark = pytest.mark.usefixtures("scope_users")


@pytest.fixture
def store(db: TenantDb, rustfs: S3Backend, monkeypatch: pytest.MonkeyPatch) -> str:
    bucket = rustfs.create_bucket()
    for name, value in rustfs.env(bucket).items():
        monkeypatch.setenv(name, value)
    return bucket


async def _load() -> None:
    out, err = io.StringIO(), io.StringIO()
    assert await run(ROOT, (TENANT_A_ID, TENANT_B_ID), out=out, err=err) == 0, err.getvalue()


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


async def _succeed(db: TenantDb, job: dict[str, Any], data: bytes = PDF) -> str:
    """Store ``data`` as the job's PDF and mark it ``succeeded`` (what the render handler does)."""
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        ref = await store_generated_file(
            conn,
            data=data,
            filename=f"project-summary-internal-{job['recordId']}.pdf",
            content_type="application/pdf",
            purpose="report",
            idempotency_key=f"report-render:{job['id']}",
            project_id=UUID(job["projectId"]),
        )
    await su_execute(
        db,
        f"UPDATE report_render_jobs SET status = 'succeeded', file_id = '{ref.id}', "
        f"pdf_sha256 = '{ref.sha256}', pdf_size_bytes = {ref.size_bytes}, rendered_at = now() "
        f"WHERE id = '{job['id']}'",
    )
    return ref.sha256


def _ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def test_the_list_carries_the_record_label_and_searches_and_filters(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, store: str
) -> None:
    await _load()
    karratha = await add_project(db)
    other = await add_project(db, code="PL-07", name="Pilbara 100% upgrade")
    done = await _request(client, karratha)
    waiting = await _request(client, other)
    await _succeed(db, done)

    items = (await client.get(RENDERS, headers=ALICE)).json()["items"]
    assert [item["id"] for item in items] == [waiting["id"], done["id"]]  # newest first
    first = next(item for item in items if item["id"] == done["id"])
    assert first["recordLabel"] == "KF-01 Karratha compressor station"
    assert first["templateNameKey"] == "report.template.project_summary"
    assert first["status"] == "succeeded" and first["fileId"]

    assert _ids(await client.get(RENDERS, params={"q": "karratha"}, headers=ALICE)) == [done["id"]]
    assert _ids(await client.get(RENDERS, params={"q": "pl-07"}, headers=ALICE)) == [waiting["id"]]
    both = await client.get(RENDERS, params={"q": "project-SUMMARY"}, headers=ALICE)
    assert len(_ids(both)) == 2  # the template key matches too
    assert _ids(await client.get(RENDERS, params={"q": "zzz"}, headers=ALICE)) == []
    assert _ids(await client.get(RENDERS, params={"q": "100%"}, headers=ALICE)) == [waiting["id"]]
    assert _ids(await client.get(RENDERS, params={"q": "1_0"}, headers=ALICE)) == []  # literal _

    succeeded = await client.get(RENDERS, params={"status": "succeeded"}, headers=ALICE)
    assert _ids(succeeded) == [done["id"]]
    queued = await client.get(RENDERS, params={"status": "queued"}, headers=ALICE)
    assert _ids(queued) == [waiting["id"]]
    either = await client.get(
        RENDERS, params=[("status", "queued"), ("status", "succeeded")], headers=ALICE
    )
    assert len(_ids(either)) == 2
    assert (await client.get(RENDERS, params={"status": "bogus"}, headers=ALICE)).status_code == 422
    assert (await client.get(RENDERS, params={"q": ""}, headers=ALICE)).status_code == 422

    fetched = (await client.get(f"{RENDERS}/{done['id']}", headers=ALICE)).json()
    assert fetched["recordLabel"] == first["recordLabel"]
    assert fetched["templateNameKey"] == "report.template.project_summary"

    again = await client.post(f"{RENDERS}/{done['id']}/rerender", headers=ALICE)
    assert again.json()["recordLabel"] == "KF-01 Karratha compressor station"


async def test_a_succeeded_report_downloads_its_exact_bytes_through_the_api(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, store: str
) -> None:
    await _load()
    project = await add_project(db)
    job = await _request(client, project)
    sha256 = await _succeed(db, job)

    response = await client.get(f"{RENDERS}/{job['id']}/file", headers=ALICE)
    assert response.status_code == 200, response.text
    assert response.content == PDF and hashlib.sha256(response.content).hexdigest() == sha256
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="project-summary-internal-{project}.pdf"'
    )
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert int(response.headers["content-length"]) == len(PDF)

    (key,) = (await su_fetch(db, "SELECT storage_key FROM stored_files"))[0]
    listed = await client.get(RENDERS, headers=ALICE)
    for text in (listed.text, json.dumps(dict(response.headers))):
        assert str(key) not in text and store not in text  # no storage key or bucket leaks

    events = await su_fetch(
        db, "SELECT payload FROM domain_events WHERE event_name = 'report.downloaded'"
    )
    assert len(events) == 1
    payload = events[0][0]
    payload = json.loads(payload) if isinstance(payload, str) else payload
    assert payload == {
        "renderJobId": job["id"],
        "fileId": (await client.get(f"{RENDERS}/{job['id']}", headers=ALICE)).json()["fileId"],
        "recordType": "project",
        "recordId": str(project),
        "pdfSha256": sha256,
    }


async def test_only_a_succeeded_report_in_the_callers_scope_downloads(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, store: str
) -> None:
    await _load()
    project = await add_project(db)
    queued = await _request(client, project)
    not_ready = await client.get(f"{RENDERS}/{queued['id']}/file", headers=ALICE)
    assert (not_ready.status_code, not_ready.json()["code"]) == (409, "REPORT_NOT_READY")

    await _succeed(db, queued)
    dave = await client.get(f"{RENDERS}/{queued['id']}/file", headers=DAVE)  # no report.view
    assert dave.status_code == 403
    bob = await client.get(f"{RENDERS}/{queued['id']}/file", headers=BOB)  # tenant B
    assert (bob.status_code, bob.json()["code"]) == (404, "RENDER_JOB_NOT_FOUND")
    events = await su_fetch(
        db, "SELECT count(*) FROM domain_events WHERE event_name = 'report.downloaded'"
    )
    assert int(str(events[0][0])) == 0


async def test_bytes_that_are_not_the_recorded_report_are_never_served(
    app: FastAPI, db: TenantDb, store: str
) -> None:
    await _load()
    project = await add_project(db)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        job = await _request(client, project)
        await _succeed(db, job)
        await su_execute(
            db,
            f"UPDATE report_render_jobs SET pdf_sha256 = '{'0' * 64}' WHERE id = '{job['id']}'",
        )
        response = await client.get(f"{RENDERS}/{job['id']}/file", headers=ALICE)
    assert response.status_code == 500
    assert b"%PDF" not in response.content
