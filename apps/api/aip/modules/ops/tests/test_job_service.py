"""OPS-01: job records (``jobs``, ``job_events``) and the job service.

Integration tests run on real Postgres (DATABASE-02 fixtures: the cluster bootstrap creates
``aip_app``/``aip_jobs``) as ``aip_app`` or ``aip_jobs`` inside ``with_tenant``.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.platform.db.conftest import APP, JOBS, FreshDb

from aip.modules.ops import api as ops
from aip.platform.context import RequestContext, use_context
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.session import with_tenant

# --- fixtures ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleDb:
    """Connections to the test database as one runtime role.

    ``tx(tenant)`` is ``with_tenant`` under a request context for that tenant acting as alice;
    ``no_tenant()`` is a bare transaction with no tenant set (to prove RLS fails closed).
    """

    tx: Callable[[UUID], AbstractAsyncContextManager[AsyncConnection]]
    no_tenant: Callable[[], AbstractAsyncContextManager[AsyncConnection]]


@contextlib.asynccontextmanager
async def _role_db(db: FreshDb, role: str) -> AsyncIterator[RoleDb]:
    engine = create_app_engine(EngineSettings(url=db.role_url(role)))

    @contextlib.asynccontextmanager
    async def tx(tenant_id: UUID) -> AsyncIterator[AsyncConnection]:
        ctx = RequestContext(
            tenant_id=tenant_id, request_id=f"test-{uuid.uuid4().hex}", actor_id=ALICE_ID
        )
        async with use_context(ctx), with_tenant(ctx, engine=engine) as conn:
            yield conn

    try:
        yield RoleDb(tx=tx, no_tenant=engine.begin)
    finally:
        await engine.dispose()


@pytest.fixture
def jobs_db(migrated_db: FreshDb) -> FreshDb:
    """A bootstrapped database (the runtime roles exist) migrated to head."""
    return migrated_db


@pytest.fixture
async def app(jobs_db: FreshDb) -> AsyncIterator[RoleDb]:
    async with _role_db(jobs_db, APP) as role_db:
        yield role_db


@pytest.fixture
async def jobs(jobs_db: FreshDb) -> AsyncIterator[RoleDb]:
    async with _role_db(jobs_db, JOBS) as role_db:
        yield role_db


# --- unit -------------------------------------------------------------------------------------


def test_succeeded_to_running_raises_invalid_transition() -> None:
    with pytest.raises(ops.InvalidTransition):
        ops.validate_transition(ops.JobStatus.SUCCEEDED, ops.JobStatus.RUNNING)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        ("queued", "running"),
        ("queued", "cancelled"),
        ("running", "succeeded"),
        ("running", "failed"),
        ("running", "cancelled"),
    ],
)
def test_allowed_transitions(current: str, new: str) -> None:
    ops.validate_transition(ops.JobStatus(current), ops.JobStatus(new))


@pytest.mark.parametrize(
    ("current", "new"),
    [
        ("queued", "queued"),
        ("queued", "succeeded"),
        ("queued", "failed"),
        ("running", "running"),
        ("running", "queued"),
        ("succeeded", "failed"),
        ("failed", "running"),
        ("failed", "queued"),
        ("cancelled", "running"),
        ("cancelled", "cancelled"),
    ],
)
def test_forbidden_transitions(current: str, new: str) -> None:
    with pytest.raises(ops.InvalidTransition):
        ops.validate_transition(ops.JobStatus(current), ops.JobStatus(new))


def test_missing_correlation_id_becomes_uuid7() -> None:
    generated = ops.resolve_correlation_id(None)
    assert generated.version == 7


def test_supplied_correlation_id_is_kept() -> None:
    given = uuid.uuid4()
    assert ops.resolve_correlation_id(given) == given


def test_correlation_id_comes_from_request_context_when_it_is_a_uuid() -> None:
    request_id = uuid.UUID(int=uuid.uuid4().int)
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id=str(request_id))
    with use_context(ctx):
        assert ops.resolve_correlation_id(None) == request_id


def test_non_uuid_request_id_is_not_used_as_correlation_id() -> None:
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id="job-not-a-uuid")
    with use_context(ctx):
        assert ops.resolve_correlation_id(None).version == 7


# --- integration ------------------------------------------------------------------------------


async def test_create_job_twice_with_same_key_gives_one_row(app: RoleDb) -> None:
    async with app.tx(TENANT_A_ID) as conn:
        first = await ops.create_job(
            conn, job_type="report.render", payload={"n": 1}, idempotency_key="k1"
        )
    async with app.tx(TENANT_A_ID) as conn:
        second = await ops.create_job(
            conn, job_type="report.render", payload={"n": 2}, idempotency_key="k1"
        )
        count = (await conn.execute(text("SELECT count(*) FROM jobs"))).scalar_one()
        events = (await conn.execute(text("SELECT count(*) FROM job_events"))).scalar_one()

    assert second.id == first.id
    assert second.payload == {"n": 1}
    assert count == 1
    assert events == 1  # only the first create writes the initial `queued` event
    assert first.status is ops.JobStatus.QUEUED
    assert first.tenant_id == TENANT_A_ID
    assert first.requested_by == ALICE_ID
    assert first.correlation_id.version == 7


async def test_same_key_in_another_tenant_is_a_separate_job(app: RoleDb) -> None:
    async with app.tx(TENANT_A_ID) as conn:
        job_a = await ops.create_job(
            conn, job_type="report.render", payload={}, idempotency_key="k1"
        )
    async with app.tx(TENANT_B_ID) as conn:
        job_b = await ops.create_job(
            conn, job_type="report.render", payload={}, idempotency_key="k1"
        )
        visible = (await conn.execute(text("SELECT id FROM jobs"))).scalars().all()

    assert job_b.id != job_a.id
    assert job_b.tenant_id == TENANT_B_ID
    assert visible == [job_b.id]  # RLS: tenant B never sees tenant A's job


async def test_jobs_without_key_are_never_deduplicated(app: RoleDb) -> None:
    async with app.tx(TENANT_A_ID) as conn:
        one = await ops.create_job(conn, job_type="report.render", payload={})
        two = await ops.create_job(conn, job_type="report.render", payload={})
    assert one.id != two.id


async def test_queued_running_succeeded_writes_ordered_events(app: RoleDb) -> None:
    async with app.tx(TENANT_A_ID) as conn:
        job = await ops.create_job(conn, job_type="report.render", payload={})
    async with app.tx(TENANT_A_ID) as conn:
        running = await ops.transition(conn, job.id, ops.JobStatus.RUNNING)
    async with app.tx(TENANT_A_ID) as conn:
        done = await ops.transition(
            conn, job.id, ops.JobStatus.SUCCEEDED, detail={"pages": 3}, result_ref="s3://k"
        )
        rows = (
            await conn.execute(
                text(
                    "SELECT seq, from_status, to_status, detail FROM job_events "
                    "WHERE job_id = :id ORDER BY seq"
                ),
                {"id": job.id},
            )
        ).all()

    assert running.status is ops.JobStatus.RUNNING
    assert running.attempts == 1
    assert done.status is ops.JobStatus.SUCCEEDED
    assert done.result_ref == "s3://k"
    assert [r.seq for r in rows] == [1, 2, 3]
    assert [r.to_status for r in rows] == ["queued", "running", "succeeded"]
    assert [r.from_status for r in rows] == [None, "queued", "running"]
    assert rows[2].detail == {"pages": 3}


async def test_terminal_job_cannot_change_state(app: RoleDb) -> None:
    async with app.tx(TENANT_A_ID) as conn:
        job = await ops.create_job(conn, job_type="report.render", payload={})
        await ops.transition(conn, job.id, ops.JobStatus.CANCELLED)
    with pytest.raises(ops.InvalidTransition):
        async with app.tx(TENANT_A_ID) as conn:
            await ops.transition(conn, job.id, ops.JobStatus.RUNNING)
    async with app.tx(TENANT_A_ID) as conn:
        status = (
            await conn.execute(text("SELECT status FROM jobs WHERE id = :id"), {"id": job.id})
        ).scalar_one()
        events = (await conn.execute(text("SELECT count(*) FROM job_events"))).scalar_one()
    assert status == "cancelled"
    assert events == 2


async def test_transition_of_another_tenants_job_is_not_found(app: RoleDb) -> None:
    async with app.tx(TENANT_A_ID) as conn:
        job = await ops.create_job(conn, job_type="report.render", payload={})
    with pytest.raises(ops.JobNotFound):
        async with app.tx(TENANT_B_ID) as conn:
            await ops.transition(conn, job.id, ops.JobStatus.RUNNING)


async def test_app_role_cannot_update_or_delete_job_events(app: RoleDb) -> None:
    async with app.tx(TENANT_A_ID) as conn:
        await ops.create_job(conn, job_type="report.render", payload={})
    with pytest.raises(DBAPIError, match="permission denied"):
        async with app.tx(TENANT_A_ID) as conn:
            await conn.execute(text("UPDATE job_events SET detail = '{}'"))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with app.tx(TENANT_A_ID) as conn:
            await conn.execute(text("DELETE FROM job_events"))


async def test_missing_tenant_context_fails_closed(app: RoleDb) -> None:
    with pytest.raises(DBAPIError):
        async with app.no_tenant() as conn:
            await ops.create_job(conn, job_type="report.render", payload={})


async def test_jobs_role_runs_transitions_but_cannot_rewrite_jobs(
    app: RoleDb, jobs: RoleDb
) -> None:
    async with app.tx(TENANT_A_ID) as conn:
        job = await ops.create_job(conn, job_type="report.render", payload={"a": 1})
    async with jobs.tx(TENANT_A_ID) as conn:
        await ops.transition(conn, job.id, ops.JobStatus.RUNNING)
        failed = await ops.transition(conn, job.id, ops.JobStatus.FAILED, error="boom")
    assert failed.error == "boom"
    with pytest.raises(DBAPIError, match="permission denied"):
        async with jobs.tx(TENANT_A_ID) as conn:
            await conn.execute(text("UPDATE jobs SET payload = '{}'"))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with jobs.tx(TENANT_A_ID) as conn:
            await conn.execute(text("INSERT INTO jobs (id) VALUES (gen_random_uuid())"))


def test_both_tables_force_row_level_security(jobs_db: FreshDb) -> None:
    rows = jobs_db.fetch(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
        "WHERE relname IN ('jobs', 'job_events') ORDER BY relname"
    )
    assert rows == [("job_events", True, True), ("jobs", True, True)]


def test_declared_tables_match_the_migrated_schema(jobs_db: FreshDb) -> None:
    result = jobs_db.aip_db("check-schema")
    assert result.returncode == 0, result.stdout + result.stderr
