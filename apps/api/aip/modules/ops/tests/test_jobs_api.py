"""OPS-03: the jobs API on real Postgres through the real app; the access rule; the tenant guard.

Jobs are created as ``aip_app`` with ``create_job`` under each user's request context (so
``requested_by`` is set as the API would set it). u1 and u2 are plain users of tenant A; ADMIN holds
``ops.jobs.admin``; BOB is tenant B.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable, Iterable, Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

from aip.main import create_app
from aip.modules.ops import api as ops
from aip.modules.ops import registry
from aip.modules.ops.jobs_access import JOBS_ADMIN, can_act_on
from aip.platform.access import AccessPrincipal, Grant
from aip.platform.context import RequestContext, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.jobs.context import TenantMismatchError
from aip.platform.jobs.tenant_guard import TenantJobPayload, defer_for_tenant, tenant_task

U1 = ALICE_ID
U2 = UUID("00000000-0000-4000-8000-0000000000a2")
ADMIN = UUID("00000000-0000-4000-8000-0000000000a3")

SEED_TENANTS = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
)


def as_user(user: UUID, tenant: UUID = TENANT_A_ID) -> dict[str, str]:
    principal = {
        "kind": "user",
        "tenantId": str(tenant),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": 1,
        "amr": ["fed"],
    }
    return {"x-test-principal": json.dumps(principal)}


class Grants:
    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        return [Grant(JOBS_ADMIN)] if principal.actor_id == ADMIN else []


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await _execute(tenant_db.db.superuser_url, SEED_TENANTS)
    return tenant_db


@pytest.fixture
async def client(db: TenantDb, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", db.db.app_url)
    await dispose_engine()
    app: FastAPI = create_app(env="test", tracing=False)
    app.state.access_policy.register(Grants())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    await dispose_engine()


@pytest.fixture
def job_type() -> Iterator[str]:
    async def handler(conn: AsyncConnection, job: ops.JobView) -> str | None:
        return None

    name = f"test.export.{uuid.uuid4().hex[:10]}"
    ops.register(name, handler, timeout_s=30, max_attempts=1)
    yield name
    registry.unregister(name)


Make = Callable[..., Any]


@pytest.fixture
def make_job(db: TenantDb, job_type: str) -> Make:
    async def make(
        user: UUID, *, tenant: UUID = TENANT_A_ID, end: str | None = None
    ) -> ops.JobView:
        ctx = RequestContext(tenant_id=tenant, request_id=str(uuid.uuid4()), actor_id=user)
        with use_context(ctx):
            async with db.with_tenant(tenant) as conn:
                job = await ops.create_job(conn, job_type=job_type, payload={"format": "csv"})
                if end is not None:
                    await ops.transition(conn, job.id, ops.JobStatus.RUNNING)
                    job = await ops.transition(
                        conn, job.id, ops.JobStatus(end), error="boom" if end == "failed" else None
                    )
        return job

    return make


async def status_of(db: TenantDb, job_id: UUID) -> str:
    async with db.with_tenant(TENANT_A_ID) as conn:
        return (
            await conn.execute(text("SELECT status FROM jobs WHERE id = :i"), {"i": job_id})
        ).scalar_one()


# --- unit -------------------------------------------------------------------------------------


def test_only_the_requester_or_a_jobs_admin_can_act_on_a_job() -> None:
    assert can_act_on(actor_id=U1, requested_by=U2, is_admin=False) is False
    assert can_act_on(actor_id=U1, requested_by=U1, is_admin=False) is True
    assert can_act_on(actor_id=U1, requested_by=U2, is_admin=True) is True
    assert can_act_on(actor_id=None, requested_by=None, is_admin=False) is False
    assert can_act_on(actor_id=U1, requested_by=None, is_admin=False) is False


@pytest.mark.parametrize("tenant", [None, "", "not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_a_tenant_job_payload_needs_a_real_tenant(tenant: object) -> None:
    with pytest.raises(ValueError, match="tenant"):
        TenantJobPayload.model_validate({"tenant_id": tenant, "job_id": "x"})


def test_a_tenant_job_payload_keeps_the_jobs_own_arguments() -> None:
    payload = TenantJobPayload.model_validate({"tenant_id": str(TENANT_A_ID), "job_id": "j1"})
    assert payload.model_dump(exclude_none=True) == {"tenant_id": str(TENANT_A_ID), "job_id": "j1"}


async def test_tenant_task_refuses_a_payload_without_a_tenant_before_the_handler() -> None:
    calls: list[str] = []

    @tenant_task
    async def handler(**kwargs: Any) -> None:
        calls.append("ran")

    with pytest.raises(ValueError, match="tenant"):
        await handler(tenant_id="nope", job_id="x")
    await handler(tenant_id=str(TENANT_A_ID), job_id="x")
    assert calls == ["ran"]


async def test_defer_for_tenant_refuses_another_tenants_job(db: TenantDb) -> None:
    payload = TenantJobPayload.model_validate({"tenant_id": str(TENANT_B_ID), "job_id": "x"})
    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(TenantMismatchError):
            await defer_for_tenant(conn, task_name="t", queue="default", payload=payload)
    async with db.no_tenant() as conn:
        with pytest.raises(TenantMismatchError):
            await defer_for_tenant(conn, task_name="t", queue="default", payload=payload)


# --- integration: list ------------------------------------------------------------------------


async def test_my_jobs_lists_only_the_callers_jobs(
    client: httpx.AsyncClient, make_job: Make
) -> None:
    mine = await make_job(U1, end="failed")
    await make_job(U2)
    await make_job(BOB_ID, tenant=TENANT_B_ID)
    res = await client.get("/api/v1/jobs/mine", headers=as_user(U1))
    assert res.status_code == 200
    [item] = res.json()["items"]
    assert item["id"] == str(mine.id)
    assert (item["status"], item["error"]) == ("failed", "boom")
    assert item["correlationId"] == str(mine.correlation_id)
    assert "payload" not in item
    assert res.json()["nextCursor"] is None


async def test_my_jobs_pages_newest_first_and_filters_by_status(
    client: httpx.AsyncClient, make_job: Make
) -> None:
    jobs = [await make_job(U1) for _ in range(3)]
    first = (await client.get("/api/v1/jobs/mine?limit=2", headers=as_user(U1))).json()
    assert [i["id"] for i in first["items"]] == [str(jobs[2].id), str(jobs[1].id)]
    rest = await client.get(
        f"/api/v1/jobs/mine?limit=2&after={first['nextCursor']}", headers=as_user(U1)
    )
    assert [i["id"] for i in rest.json()["items"]] == [str(jobs[0].id)]
    queued = await client.get("/api/v1/jobs/mine?status=failed", headers=as_user(U1))
    assert queued.json()["items"] == []


async def test_the_admin_queue_needs_ops_jobs_admin_and_shows_every_users_jobs(
    client: httpx.AsyncClient, make_job: Make
) -> None:
    await make_job(U1)
    failed = await make_job(U2, end="failed")
    await make_job(BOB_ID, tenant=TENANT_B_ID)
    denied = await client.get("/api/v1/admin/jobs", headers=as_user(U1))
    assert denied.status_code == 403
    all_jobs = await client.get("/api/v1/admin/jobs", headers=as_user(ADMIN))
    assert len(all_jobs.json()["items"]) == 2
    only_failed = await client.get(
        f"/api/v1/admin/jobs?status=failed&requestedBy={U2}", headers=as_user(ADMIN)
    )
    assert [i["id"] for i in only_failed.json()["items"]] == [str(failed.id)]


# --- integration: cancel ----------------------------------------------------------------------


async def test_another_user_cannot_cancel_my_job(
    client: httpx.AsyncClient, make_job: Make, db: TenantDb
) -> None:
    job = await make_job(U1)
    res = await client.post(f"/api/v1/jobs/{job.id}/cancel", headers=as_user(U2))
    assert (res.status_code, res.json()["code"]) == (403, "FORBIDDEN")
    assert await status_of(db, job.id) == "queued"


async def test_the_requester_and_an_admin_can_cancel(
    client: httpx.AsyncClient, make_job: Make, db: TenantDb
) -> None:
    mine = await make_job(U1)
    res = await client.post(f"/api/v1/jobs/{mine.id}/cancel", headers=as_user(U1))
    assert (res.status_code, res.json()["status"]) == (200, "cancelled")
    theirs = await make_job(U2)
    res = await client.post(f"/api/v1/jobs/{theirs.id}/cancel", headers=as_user(ADMIN))
    assert (res.status_code, res.json()["status"]) == (200, "cancelled")
    assert await status_of(db, theirs.id) == "cancelled"


async def test_cancelling_a_finished_job_is_a_conflict(
    client: httpx.AsyncClient, make_job: Make
) -> None:
    done = await make_job(U1, end="succeeded")
    res = await client.post(f"/api/v1/jobs/{done.id}/cancel", headers=as_user(U1))
    assert res.status_code == 409
    assert res.json() == {"code": "JOB_FINISHED", "status": "succeeded"}


async def test_another_tenants_job_is_not_found(client: httpx.AsyncClient, make_job: Make) -> None:
    other = await make_job(BOB_ID, tenant=TENANT_B_ID)
    for action in ("cancel", "retry"):
        res = await client.post(f"/api/v1/jobs/{other.id}/{action}", headers=as_user(ADMIN))
        assert res.status_code == 404, action


# --- integration: retry -----------------------------------------------------------------------


async def test_retry_queues_one_fresh_copy_of_a_failed_job(
    client: httpx.AsyncClient, make_job: Make, db: TenantDb
) -> None:
    failed = await make_job(U1, end="failed")
    first = await client.post(f"/api/v1/jobs/{failed.id}/retry", headers=as_user(U1))
    again = await client.post(f"/api/v1/jobs/{failed.id}/retry", headers=as_user(U1))
    assert first.status_code == 201
    assert first.json()["id"] == again.json()["id"] != str(failed.id)
    assert first.json()["status"] == "queued"
    async with db.with_tenant(TENANT_A_ID) as conn:
        payload = (
            await conn.execute(
                text("SELECT payload FROM jobs WHERE id = :i"), {"i": UUID(first.json()["id"])}
            )
        ).scalar_one()
    assert payload == {"format": "csv", "retryOf": str(failed.id)}


async def test_only_failed_jobs_can_be_retried(client: httpx.AsyncClient, make_job: Make) -> None:
    queued = await make_job(U1)
    res = await client.post(f"/api/v1/jobs/{queued.id}/retry", headers=as_user(U1))
    assert res.json() == {"code": "JOB_NOT_FAILED", "status": "queued"}
    failed = await make_job(U1, end="failed")
    res = await client.post(f"/api/v1/jobs/{failed.id}/retry", headers=as_user(U2))
    assert res.status_code == 403
