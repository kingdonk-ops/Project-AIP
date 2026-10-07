"""OPS-01: job records (``jobs``, ``job_events``) and the job service.

Integration tests run on real Postgres as ``aip_app`` inside a transaction that sets
``app.tenant_id`` (the ADR 0002 contract ``with_tenant`` implements; DATABASE-02 builds the helper
itself, so these tests open the transaction directly).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator, Iterator
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from sqlalchemy import NullPool, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.platform.db.conftest import FreshDb, execute, fetch, with_db

from aip.modules.ops import api as ops
from aip.platform.context import RequestContext, use_context

# Throwaway test credentials for the login roles DATABASE-02 owns; not secrets.
ROLE_PASSWORDS = {"aip_app": "aip_app_test_only", "aip_jobs": "aip_jobs_test_only"}


# --- fixtures ---------------------------------------------------------------------------------


@pytest.fixture
def app_roles(pg_superuser_url: str) -> Iterator[None]:
    """Make sure the DATABASE-02 roles ``aip_app`` and ``aip_jobs`` exist for this test.

    Stand-in until DATABASE-02's bootstrap creates them: roles this fixture creates are dropped
    after the test database is gone, so other tests (the schema snapshot) never see them.
    """
    created: list[str] = []
    for role, password in ROLE_PASSWORDS.items():
        if not fetch(pg_superuser_url, "SELECT 1 FROM pg_roles WHERE rolname = $1", role):
            with contextlib.suppress(asyncpg.DuplicateObjectError):
                execute(
                    pg_superuser_url,
                    f"CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'",
                )
                created.append(role)
        else:
            execute(pg_superuser_url, f"ALTER ROLE {role} PASSWORD '{password}'")
    yield
    for role in created:
        with contextlib.suppress(asyncpg.PostgresError):
            execute(pg_superuser_url, f"DROP ROLE IF EXISTS {role}")


@pytest.fixture
def jobs_db(app_roles: None, migrated_db: FreshDb) -> FreshDb:
    """A database migrated to head after ``aip_app`` / ``aip_jobs`` exist (grants applied)."""
    return migrated_db


def _engine(db: FreshDb, role: str) -> AsyncEngine:
    url = with_db(db.superuser_url, db.name, role, ROLE_PASSWORDS[role])
    return create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )


@pytest.fixture
async def app_engine(jobs_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    engine = _engine(jobs_db, "aip_app")
    yield engine
    await engine.dispose()


@pytest.fixture
async def jobs_engine(jobs_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    engine = _engine(jobs_db, "aip_jobs")
    yield engine
    await engine.dispose()


@contextlib.asynccontextmanager
async def tenant_tx(engine: AsyncEngine, tenant_id: UUID) -> AsyncIterator[AsyncConnection]:
    """One transaction with ``app.tenant_id`` set locally, as ``with_tenant`` does (ADR 0002)."""
    ctx = RequestContext(
        tenant_id=tenant_id, request_id=f"test-{uuid.uuid4().hex}", actor_id=ALICE_ID
    )
    async with use_context(ctx), engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        yield conn


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


async def test_create_job_twice_with_same_key_gives_one_row(app_engine: AsyncEngine) -> None:
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        first = await ops.create_job(
            conn, job_type="report.render", payload={"n": 1}, idempotency_key="k1"
        )
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
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


async def test_same_key_in_another_tenant_is_a_separate_job(app_engine: AsyncEngine) -> None:
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        job_a = await ops.create_job(
            conn, job_type="report.render", payload={}, idempotency_key="k1"
        )
    async with tenant_tx(app_engine, TENANT_B_ID) as conn:
        job_b = await ops.create_job(
            conn, job_type="report.render", payload={}, idempotency_key="k1"
        )
        visible = (await conn.execute(text("SELECT id FROM jobs"))).scalars().all()

    assert job_b.id != job_a.id
    assert job_b.tenant_id == TENANT_B_ID
    assert visible == [job_b.id]  # RLS: tenant B never sees tenant A's job


async def test_jobs_without_key_are_never_deduplicated(app_engine: AsyncEngine) -> None:
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        one = await ops.create_job(conn, job_type="report.render", payload={})
        two = await ops.create_job(conn, job_type="report.render", payload={})
    assert one.id != two.id


async def test_queued_running_succeeded_writes_ordered_events(app_engine: AsyncEngine) -> None:
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        job = await ops.create_job(conn, job_type="report.render", payload={})
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        running = await ops.transition(conn, job.id, ops.JobStatus.RUNNING)
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
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


async def test_terminal_job_cannot_change_state(app_engine: AsyncEngine) -> None:
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        job = await ops.create_job(conn, job_type="report.render", payload={})
        await ops.transition(conn, job.id, ops.JobStatus.CANCELLED)
    with pytest.raises(ops.InvalidTransition):
        async with tenant_tx(app_engine, TENANT_A_ID) as conn:
            await ops.transition(conn, job.id, ops.JobStatus.RUNNING)
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        status = (
            await conn.execute(text("SELECT status FROM jobs WHERE id = :id"), {"id": job.id})
        ).scalar_one()
        events = (await conn.execute(text("SELECT count(*) FROM job_events"))).scalar_one()
    assert status == "cancelled"
    assert events == 2


async def test_transition_of_another_tenants_job_is_not_found(app_engine: AsyncEngine) -> None:
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        job = await ops.create_job(conn, job_type="report.render", payload={})
    with pytest.raises(ops.JobNotFound):
        async with tenant_tx(app_engine, TENANT_B_ID) as conn:
            await ops.transition(conn, job.id, ops.JobStatus.RUNNING)


async def test_app_role_cannot_update_or_delete_job_events(app_engine: AsyncEngine) -> None:
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        await ops.create_job(conn, job_type="report.render", payload={})
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_tx(app_engine, TENANT_A_ID) as conn:
            await conn.execute(text("UPDATE job_events SET detail = '{}'"))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_tx(app_engine, TENANT_A_ID) as conn:
            await conn.execute(text("DELETE FROM job_events"))


async def test_missing_tenant_context_fails_closed(app_engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError):
        async with app_engine.begin() as conn:
            await ops.create_job(conn, job_type="report.render", payload={})


async def test_jobs_role_runs_transitions_but_cannot_rewrite_jobs(
    app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    async with tenant_tx(app_engine, TENANT_A_ID) as conn:
        job = await ops.create_job(conn, job_type="report.render", payload={"a": 1})
    async with tenant_tx(jobs_engine, TENANT_A_ID) as conn:
        await ops.transition(conn, job.id, ops.JobStatus.RUNNING)
        failed = await ops.transition(conn, job.id, ops.JobStatus.FAILED, error="boom")
    assert failed.error == "boom"
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_tx(jobs_engine, TENANT_A_ID) as conn:
            await conn.execute(text("UPDATE jobs SET payload = '{}'"))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_tx(jobs_engine, TENANT_A_ID) as conn:
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
