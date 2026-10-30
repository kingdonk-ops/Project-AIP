"""REPORTS-02 integration tests: requesting renders on real Postgres (no worker, no Gotenberg).

The app connects as ``aip_app`` (RLS on); users come from the AUTH_TEST_STUB principal header and
permissions from the ``grants`` table (``scope_users``). The config ``project-summary`` template is
installed by the REPORTS-01 loader. Each request must commit its snapshot, render job, ``jobs`` row
and queue row together, or none of them.
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.report_engine import render_service as render_service_module
from aip.modules.report_engine.api import ReportsApi
from aip.modules.report_engine.loader import run
from aip.modules.report_engine.template_package import load_package
from aip.platform.context import RequestContext, use_context
from aip.platform.db.migrator import repo_root

from .conftest import ALICE, BOB, CAROL, DAVE, GrantTable, add_project, su_execute, su_fetch

RENDERS = "/api/v1/reports/renders"
TEMPLATES = "/api/v1/reports/templates"
ROOT = repo_root() / "config" / "report-templates"
EXAMPLE = ROOT / "project-summary" / "internal" / "v1"

pytestmark = pytest.mark.usefixtures("scope_users")


async def _load() -> None:
    out, err = io.StringIO(), io.StringIO()
    assert await run(ROOT, (TENANT_A_ID, TENANT_B_ID), out=out, err=err) == 0, err.getvalue()


def _body(project_id: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "templateKey": "project-summary",
        "variant": "internal",
        "recordType": "project",
        "recordId": str(project_id),
        **overrides,
    }


def _json(value: object) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def _count(db: TenantDb, table: str, where: str = "true") -> int:
    rows = await su_fetch(db, f"SELECT count(*) FROM {table} WHERE {where}")  # noqa: S608
    return int(str(rows[0][0]))


async def _counts(db: TenantDb) -> tuple[int, int, int, int]:
    return (
        await _count(db, "report_data_snapshots"),
        await _count(db, "report_render_jobs"),
        await _count(db, "jobs", "job_type = 'report_engine.render'"),
        await _count(db, "procrastinate_jobs", "task_name = 'report_engine.render'"),
    )


async def _install(
    client: httpx.AsyncClient, *, key: str, record_type: str, version: int = 1
) -> None:
    package = load_package(EXAMPLE)
    upload = {
        "definition": {
            **json.loads(json.dumps(package.definition)),
            "key": key,
            "recordType": record_type,
            "version": version,
        },
        "body": package.body,
        "css": package.css,
        "sampleData": dict(package.sample_data),
        "assets": {n: base64.b64encode(a.data).decode() for n, a in package.assets.items()},
    }
    created = await client.post(TEMPLATES, json=upload, headers=ALICE)
    assert created.status_code == 201, created.text
    published = await client.post(f"{TEMPLATES}/{created.json()['id']}/publish", headers=ALICE)
    assert published.status_code == 200, published.text


async def test_a_request_commits_snapshot_job_and_queue_row_together(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    project = await add_project(db)
    response = await client.post(RENDERS, json=_body(project), headers=ALICE)
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "queued"
    assert (job["templateKey"], job["templateVersion"], job["variant"]) == (
        "project-summary",
        1,
        "internal",
    )
    assert len(job["dataHash"]) == 64 and job["opsJobId"] and job["templateId"]
    assert job["projectId"] == str(project) and job["fileId"] is None
    assert await _counts(db) == (1, 1, 1, 1)
    (ops_job,) = await su_fetch(db, "SELECT id, payload FROM jobs")
    assert str(ops_job[0]) == job["opsJobId"]
    assert _json(ops_job[1]) == {"renderJobId": job["id"]}

    (snapshot,) = await su_fetch(
        db, "SELECT data, data_hash, record_version, project_id FROM report_data_snapshots"
    )
    data = _json(snapshot[0])
    assert data["record"]["project"]["code"] == "KF-01"
    assert (data["timeZone"], data["locale"], data["recordType"]) == (
        "Australia/Perth",
        "en-AU",
        "project",
    )
    assert data["labels"]["report.label.project_code"]
    assert snapshot[1] == job["dataHash"] and snapshot[3] == project

    fetched = await client.get(f"{RENDERS}/{job['id']}", headers=ALICE)
    assert fetched.status_code == 200 and fetched.json()["id"] == job["id"]
    listed = await client.get(RENDERS, params={"recordId": str(project)}, headers=ALICE)
    assert [item["id"] for item in listed.json()["items"]] == [job["id"]]


async def test_an_idempotency_key_returns_the_first_job(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    project = await add_project(db)
    headers = {**ALICE, "Idempotency-Key": "abc"}
    first = await client.post(RENDERS, json=_body(project), headers=headers)
    second = await client.post(RENDERS, json=_body(project), headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert await _counts(db) == (1, 1, 1, 1)

    too_long = await client.post(
        RENDERS, json=_body(project), headers={**ALICE, "Idempotency-Key": "k" * 129}
    )
    assert too_long.status_code == 422


async def test_unchanged_data_reuses_the_snapshot_and_a_change_makes_a_new_one(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    project = await add_project(db)
    one = (await client.post(RENDERS, json=_body(project), headers=ALICE)).json()
    two = (await client.post(RENDERS, json=_body(project), headers=ALICE)).json()
    assert one["id"] != two["id"] and one["dataHash"] == two["dataHash"]
    assert one["snapshotId"] == two["snapshotId"]
    assert (await _count(db, "report_render_jobs"), await _count(db, "report_data_snapshots")) == (
        2,
        1,
    )

    await su_execute(db, f"UPDATE projects SET name = 'Renamed station' WHERE id = '{project}'")
    three = (await client.post(RENDERS, json=_body(project), headers=ALICE)).json()
    assert three["dataHash"] != one["dataHash"]
    assert await _count(db, "report_data_snapshots") == 2


async def test_snapshots_cannot_be_changed_or_deleted_by_the_app(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    project = await add_project(db)
    assert (await client.post(RENDERS, json=_body(project), headers=ALICE)).status_code == 202
    for statement in (
        "UPDATE report_data_snapshots SET data = '{}'",
        "DELETE FROM report_data_snapshots",
        "TRUNCATE report_data_snapshots",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with db.with_tenant(TENANT_A_ID) as conn:
                await conn.execute(text(statement))
    assert await _count(db, "report_data_snapshots") == 1


async def test_a_failure_inside_the_request_writes_nothing(
    app: FastAPI, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load()
    project = await add_project(db)
    real_enqueue = render_service_module.ops.enqueue

    class EnqueueThenFailError(Exception):
        pass

    async def enqueue_then_fail(*args: Any, **kwargs: Any) -> Any:
        await real_enqueue(*args, **kwargs)
        raise EnqueueThenFailError

    monkeypatch.setattr(render_service_module.ops, "enqueue", enqueue_then_fail)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(RENDERS, json=_body(project), headers=ALICE)
    assert response.status_code == 500
    assert await _counts(db) == (0, 0, 0, 0)


async def test_template_and_record_type_errors(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    project = await add_project(db)
    await _install(client, key="widget-card", record_type="widget")
    await _install(client, key="inspection-sheet", record_type="inspection")

    nope = await client.post(RENDERS, json=_body(project, templateKey="nope"), headers=ALICE)
    assert (nope.status_code, nope.json()["code"]) == (404, "TEMPLATE_NOT_FOUND")
    widget = await client.post(
        RENDERS, json=_body(project, templateKey="widget-card", recordType="widget"), headers=ALICE
    )
    assert (widget.status_code, widget.json()["code"]) == (422, "UNKNOWN_RECORD_TYPE")
    mismatch = await client.post(
        RENDERS, json=_body(project, templateKey="inspection-sheet"), headers=ALICE
    )
    assert (mismatch.status_code, mismatch.json()["code"]) == (
        422,
        "TEMPLATE_RECORD_TYPE_MISMATCH",
    )
    missing = await client.post(RENDERS, json=_body(uuid4()), headers=ALICE)
    assert (missing.status_code, missing.json()["code"]) == (404, "RECORD_NOT_FOUND")
    strict = await client.post(RENDERS, json={**_body(project), "extra": 1}, headers=ALICE)
    assert strict.status_code == 422
    assert await _counts(db) == (0, 0, 0, 0)


async def test_permissions_are_checked_on_the_records_project(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, scope_users: GrantTable
) -> None:
    await _load()
    project = await add_project(db)
    carol = await client.post(RENDERS, json=_body(project), headers=CAROL)  # no project.view
    assert (carol.status_code, carol.json()) == (
        403,
        {"code": "FORBIDDEN", "permission": "project.view"},
    )
    dave = await client.post(RENDERS, json=_body(project), headers=DAVE)  # nothing
    assert dave.status_code == 403
    assert await _counts(db) == (0, 0, 0, 0)

    job = (await client.post(RENDERS, json=_body(project), headers=ALICE)).json()
    assert (await client.get(f"{RENDERS}/{job['id']}", headers=DAVE)).status_code == 403
    assert (await client.get(RENDERS, headers=DAVE)).json()["items"] == []
    rerender = await client.post(f"{RENDERS}/{job['id']}/rerender", headers=DAVE)
    assert rerender.status_code == 403
    assert await _count(db, "report_render_jobs") == 1


async def test_another_tenant_sees_nothing(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    project = await add_project(db)
    job = (await client.post(RENDERS, json=_body(project), headers=ALICE)).json()

    seen = await client.get(f"{RENDERS}/{job['id']}", headers=BOB)
    assert (seen.status_code, seen.json()["code"]) == (404, "RENDER_JOB_NOT_FOUND")
    again = await client.post(f"{RENDERS}/{job['id']}/rerender", headers=BOB)
    assert (again.status_code, again.json()["code"]) == (404, "RENDER_JOB_NOT_FOUND")
    stolen = await client.post(RENDERS, json=_body(project), headers=BOB)
    assert (stolen.status_code, stolen.json()["code"]) == (404, "RECORD_NOT_FOUND")
    assert (await client.get(RENDERS, headers=BOB)).json()["items"] == []
    assert await _count(db, "report_render_jobs") == 1


async def test_the_published_interface_queues_a_render_without_a_policy_check(
    app: FastAPI, db: TenantDb
) -> None:
    await _load()
    project = await add_project(db)
    reports = ReportsApi()
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id="test-system-render")
    with use_context(ctx):
        async with db.with_tenant(ctx) as conn:
            await conn.execute(text("SELECT set_config('app.principal_kind', 'system', true)"))
            job = await reports.request_render(
                conn,
                template_key="project-summary",
                record_type="project",
                record_id=project,
                variant="internal",
                idempotency_key="approval:1",
            )
            assert job.status == "queued" and job.requested_by is None
            assert await reports.get_render_job(conn, job.id) == job
            assert await reports.get_render_job(conn, uuid4()) is None
    assert await _counts(db) == (1, 1, 1, 1)
