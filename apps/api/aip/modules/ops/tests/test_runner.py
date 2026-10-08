"""OPS-02: the job registry, atomic enqueue and the runner, on real Postgres and Procrastinate.

The worker runs in-process (``run_worker(..., wait=False)``) as ``aip_jobs``; jobs are enqueued
as ``aip_app`` inside ``with_tenant``, exactly as the API does. Handlers are registered per test
under unique job types and unregistered afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.platform.db.conftest import APP, JOBS, FreshDb

from aip.modules.ops import api as ops
from aip.modules.ops import registry
from aip.modules.ops.runner import MemoryGuard, run_job
from aip.platform.context import ContextMissingError, RequestContext, use_context
from aip.platform.db.engine import (
    JOBS_DATABASE_URL_ENV,
    EngineSettings,
    create_app_engine,
    dispose_jobs_engine,
)
from aip.platform.db.session import with_tenant
from aip.platform.jobs.app import (
    QUEUES,
    JobRetryStrategy,
    defer_in_transaction,
    job_lock,
    run_worker,
)

Tx = Callable[[UUID], AbstractAsyncContextManager[AsyncConnection]]
Handler = Callable[[AsyncConnection, ops.JobView], Awaitable[str | None]]

# --- fixtures ---------------------------------------------------------------------------------


@pytest.fixture
def queue_db(migrated_db: FreshDb, monkeypatch: pytest.MonkeyPatch) -> FreshDb:
    """A migrated database; the worker's engine (``DATABASE_JOBS_URL``) points at it."""
    monkeypatch.setenv(JOBS_DATABASE_URL_ENV, migrated_db.role_url(JOBS))
    return migrated_db


@pytest.fixture(autouse=True)
async def _dispose_jobs_engine() -> AsyncIterator[None]:  # pyright: ignore[reportUnusedFunction]
    yield
    await dispose_jobs_engine()


@pytest.fixture
async def tx(queue_db: FreshDb) -> AsyncIterator[Tx]:
    """``tx(tenant)``: ``with_tenant`` as ``aip_app`` under a request context (alice)."""
    engine = create_app_engine(EngineSettings(url=queue_db.role_url(APP)))

    @contextlib.asynccontextmanager
    async def tenant_tx(tenant_id: UUID) -> AsyncIterator[AsyncConnection]:
        ctx = RequestContext(
            tenant_id=tenant_id, request_id=f"test-{uuid.uuid4().hex}", actor_id=ALICE_ID
        )
        async with use_context(ctx), with_tenant(ctx, engine=engine) as conn:
            yield conn

    try:
        yield tenant_tx
    finally:
        await engine.dispose()


@pytest.fixture
def register_job() -> Iterator[Callable[..., ops.JobSpec]]:
    """``register_job(handler, **options)`` under a fresh job type; unregistered afterwards."""
    types: list[str] = []

    def register(handler: Handler, **options: Any) -> ops.JobSpec:
        job_type = f"test.job.{uuid.uuid4().hex[:10]}"
        types.append(job_type)
        options.setdefault("timeout_s", 30)
        options.setdefault("max_attempts", 1)
        return ops.register(job_type, handler, **options)

    try:
        yield register
    finally:
        for job_type in types:
            registry.unregister(job_type)


async def drain(
    db: FreshDb, *, concurrency: int = 1, queues: tuple[str, ...] = ("default",)
) -> None:
    """Run a worker as ``aip_jobs`` until the queues are empty."""
    await asyncio.wait_for(
        run_worker(
            queues=queues,
            concurrency=concurrency,
            wait=False,
            conninfo=db.role_url(JOBS),
            install_signal_handlers=False,
            listen_notify=False,
            fetch_job_polling_interval=0.2,
        ),
        timeout=60,
    )


async def drain_all(db: FreshDb, *, concurrency: int = 1) -> None:
    """``drain`` until nothing is waiting: a ``wait=False`` worker leaves lock-blocked jobs."""
    for _ in range(20):
        await drain(db, concurrency=concurrency)
        if await sfetch(
            db, "SELECT count(*) FROM procrastinate_jobs WHERE status IN ('todo','doing')"
        ) == [(0,)]:
            return
    raise AssertionError("queue did not drain")


async def sfetch(db: FreshDb, sql: str) -> list[tuple[Any, ...]]:
    """``db.fetch`` (superuser, bypasses RLS) from async code: it runs its own event loop."""
    return await asyncio.to_thread(db.fetch, sql)


async def job_row(tx: Tx, tenant_id: UUID, job_id: UUID) -> Any:
    async with tx(tenant_id) as conn:
        return (
            await conn.execute(
                text("SELECT status, attempts, error, result_ref FROM jobs WHERE id = :id"),
                {"id": job_id},
            )
        ).one()


async def enqueue(
    tx: Tx, tenant_id: UUID, spec: ops.JobSpec, payload: dict[str, Any] | None = None, **kw: Any
) -> ops.JobView:
    async with tx(tenant_id) as conn:
        return await ops.enqueue(conn, spec.job_type, payload or {}, **kw)


# --- unit -------------------------------------------------------------------------------------


async def test_enqueue_of_an_unregistered_type_raises_unknown_job_type() -> None:
    with pytest.raises(ops.UnknownJobType):
        await ops.enqueue(None, "nobody.registered.this", {})  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def test_retry_wait_grows_with_the_attempt() -> None:
    strategy = JobRetryStrategy(max_attempts=5, exponential_wait=2)
    assert strategy.backoff_seconds(3) > strategy.backoff_seconds(1)
    assert [strategy.backoff_seconds(n) for n in (1, 2, 3)] == [2, 4, 8]


def test_retry_decision_waits_longer_on_later_attempts_and_stops_at_max_attempts() -> None:
    from procrastinate.jobs import Job

    strategy = JobRetryStrategy(max_attempts=3, exponential_wait=2)

    def decision(earlier_tries: int) -> Any:
        job = Job(id=1, queue="default", lock=None, queueing_lock=None, task_name="t",
                  task_kwargs={}, attempts=earlier_tries)  # fmt: skip
        return strategy.get_retry_decision(exception=RuntimeError("x"), job=job)

    first, second, third = decision(0), decision(1), decision(2)
    assert first is not None and second is not None
    assert second.retry_at > first.retry_at
    assert third is None  # try number 3 of 3 failed: no retry


def test_one_attempt_means_no_retry() -> None:
    from procrastinate.jobs import Job

    strategy = JobRetryStrategy(max_attempts=1, exponential_wait=2)
    job = Job(id=1, queue="default", lock=None, queueing_lock=None, task_name="t",
              task_kwargs={}, attempts=0)  # fmt: skip
    assert strategy.get_retry_decision(exception=RuntimeError("x"), job=job) is None


async def _noop(conn: AsyncConnection, job: ops.JobView) -> str | None:
    return None


def test_register_validates_its_arguments(register_job: Callable[..., ops.JobSpec]) -> None:
    for bad in (
        {"queue": "per-tenant-queue"},
        {"timeout_s": 0},
        {"max_attempts": 0},
        {"max_per_tenant": 0},
        {"retry_backoff_s": -1},
    ):
        with pytest.raises(ops.InvalidJobSpec):
            register_job(_noop, **bad)
    with pytest.raises(ops.InvalidJobSpec):
        ops.register("", _noop, timeout_s=1, max_attempts=1)


def test_register_is_idempotent_for_the_same_handler_and_rejects_a_different_one() -> None:
    job_type = f"test.job.{uuid.uuid4().hex[:10]}"
    try:
        first = ops.register(job_type, _noop, timeout_s=5, max_attempts=2)
        assert ops.register(job_type, _noop, timeout_s=5, max_attempts=2) is first
        assert ops.get_spec(job_type) is first
        assert job_type in ops.registered_types()

        async def other(conn: AsyncConnection, job: ops.JobView) -> str | None:
            return None

        with pytest.raises(ops.DuplicateJobType):
            ops.register(job_type, other, timeout_s=5, max_attempts=2)
    finally:
        registry.unregister(job_type)


def test_queues_are_per_job_class() -> None:
    assert QUEUES == ("default", "pdf", "scan", "import", "outbox")


def test_job_lock_names_tenant_type_and_slot() -> None:
    assert job_lock(TENANT_A_ID, "export", 1) == f"tenant:{TENANT_A_ID}:job:export:1"


def test_memory_guard_warns_then_asks_the_worker_to_exit(caplog: pytest.LogCaptureFixture) -> None:
    exits: list[bool] = []
    usage = {"mb": 700.0}
    guard = MemoryGuard(
        1000, read_rss_mb=lambda: usage["mb"], on_exceeded=lambda: exits.append(True)
    )
    assert guard.check() is False and not caplog.records
    usage["mb"] = 850.0
    with caplog.at_level("WARNING"):
        assert guard.check() is False
    assert "above 80%" in caplog.text and not exits
    usage["mb"] = 960.0
    assert guard.check() is True and exits == [True]
    assert MemoryGuard(None, read_rss_mb=lambda: 10**9).check() is False  # no limit: off


def test_memory_guard_reads_its_limit_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_MEMORY_LIMIT_MB", "512")
    assert MemoryGuard.from_env().limit_mb == 512
    monkeypatch.setenv("WORKER_MEMORY_LIMIT_MB", "lots")
    assert MemoryGuard.from_env().limit_mb is None


async def test_a_payload_without_a_tenant_is_refused_before_anything_runs() -> None:
    spec = ops.JobSpec("x", _noop, "default", 1, 1, 1, 0)
    with pytest.raises(ContextMissingError):
        await run_job(spec, job_id=str(uuid.uuid4()), tenant_id="")


# --- integration ------------------------------------------------------------------------------


async def test_a_handler_over_its_timeout_fails_with_timeout(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    async def slow(conn: AsyncConnection, job: ops.JobView) -> str | None:
        await asyncio.sleep(5)
        return "never"

    spec = register_job(slow, timeout_s=1, max_attempts=1)
    job = await enqueue(tx, TENANT_A_ID, spec)
    started = time.monotonic()
    await drain(queue_db)

    row = await job_row(tx, TENANT_A_ID, job.id)
    assert row.status == "failed"
    assert "timeout" in row.error
    assert row.result_ref is None
    assert time.monotonic() - started < 5


async def test_the_same_succeeded_job_delivered_twice_runs_the_handler_once(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    calls: list[UUID] = []

    async def handler(conn: AsyncConnection, job: ops.JobView) -> str | None:
        calls.append(job.id)
        return "s3://result"

    spec = register_job(handler)
    job = await enqueue(tx, TENANT_A_ID, spec)
    await drain(queue_db)
    assert calls == [job.id]

    # Redeliver: two more Procrastinate jobs for the same, already succeeded, job id.
    args = {"job_id": str(job.id), "tenant_id": str(TENANT_A_ID)}
    for _ in range(2):
        async with tx(TENANT_A_ID) as conn:
            await defer_in_transaction(conn, task_name=spec.job_type, queue="default", args=args)
    await drain(queue_db)

    assert calls == [job.id]
    row = await job_row(tx, TENANT_A_ID, job.id)
    assert (row.status, row.result_ref, row.attempts) == ("succeeded", "s3://result", 1)
    queue = await sfetch(
        queue_db, "SELECT status::text, count(*) FROM procrastinate_jobs GROUP BY 1"
    )
    assert queue == [("succeeded", 3)]


async def test_a_raising_handler_is_retried_until_max_attempts_then_failed(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    calls = 0

    async def boom(conn: AsyncConnection, job: ops.JobView) -> str | None:
        nonlocal calls
        calls += 1
        await conn.execute(text("SELECT 1"))
        raise RuntimeError("kaboom")

    spec = register_job(boom, max_attempts=3, retry_backoff_s=0)
    job = await enqueue(tx, TENANT_A_ID, spec)
    await drain(queue_db)

    row = await job_row(tx, TENANT_A_ID, job.id)
    assert calls == 3
    assert (row.status, row.attempts) == ("failed", 3)
    assert row.error == "RuntimeError: kaboom"
    async with tx(TENANT_A_ID) as conn:
        events = (
            await conn.execute(
                text(
                    "SELECT from_status, to_status FROM job_events WHERE job_id = :i ORDER BY seq"
                ),
                {"i": job.id},
            )
        ).all()
    assert [tuple(e) for e in events] == [
        (None, "queued"),
        ("queued", "running"),
        ("running", "running"),  # try 1 failed, will retry
        ("running", "running"),  # try 2 begins
        ("running", "running"),  # try 2 failed, will retry
        ("running", "running"),  # try 3 begins
        ("running", "failed"),
    ]


async def test_a_handler_that_fails_once_then_succeeds_ends_succeeded(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    calls = 0

    async def flaky(conn: AsyncConnection, job: ops.JobView) -> str | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        return "ok"

    spec = register_job(flaky, max_attempts=3, retry_backoff_s=0)
    job = await enqueue(tx, TENANT_A_ID, spec)
    await drain(queue_db)

    row = await job_row(tx, TENANT_A_ID, job.id)
    assert (row.status, row.attempts, row.result_ref) == ("succeeded", 2, "ok")


async def test_a_failed_try_rolls_back_the_handlers_writes(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    async def writes_then_fails(conn: AsyncConnection, job: ops.JobView) -> str | None:
        await conn.execute(
            text("UPDATE jobs SET result_ref = 'half-done' WHERE id = :id"), {"id": job.id}
        )
        raise RuntimeError("after the write")

    spec = register_job(writes_then_fails, max_attempts=1)
    job = await enqueue(tx, TENANT_A_ID, spec)
    await drain(queue_db)
    row = await job_row(tx, TENANT_A_ID, job.id)
    assert (row.status, row.result_ref) == ("failed", None)


async def test_a_rolled_back_enqueue_leaves_no_job_and_no_queue_row(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    spec = register_job(_noop)

    class BoomError(Exception):
        pass

    with pytest.raises(BoomError):
        async with tx(TENANT_A_ID) as conn:
            await ops.enqueue(conn, spec.job_type, {"n": 1})
            raise BoomError

    assert await sfetch(queue_db, "SELECT count(*) FROM jobs") == [(0,)]
    assert await sfetch(queue_db, "SELECT count(*) FROM procrastinate_jobs") == [(0,)]
    assert await sfetch(queue_db, "SELECT count(*) FROM procrastinate_events") == [(0,)]

    job = await enqueue(tx, TENANT_A_ID, spec, {"n": 2})  # the committed path still works
    assert await sfetch(queue_db, "SELECT count(*) FROM jobs") == [(1,)]
    assert await sfetch(queue_db, "SELECT count(*) FROM procrastinate_jobs") == [(1,)]
    assert job.procrastinate_job_id is not None


async def test_enqueue_with_the_same_idempotency_key_defers_once(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    calls = 0

    async def handler(conn: AsyncConnection, job: ops.JobView) -> str | None:
        nonlocal calls
        calls += 1
        return None

    spec = register_job(handler)
    first = await enqueue(tx, TENANT_A_ID, spec, {"a": 1}, idempotency_key="k")
    second = await enqueue(tx, TENANT_A_ID, spec, {"a": 2}, idempotency_key="k")
    assert second.id == first.id and second.procrastinate_job_id == first.procrastinate_job_id
    assert await sfetch(queue_db, "SELECT count(*) FROM procrastinate_jobs") == [(1,)]
    await drain(queue_db)
    assert calls == 1


async def test_a_handler_sees_only_its_own_tenants_rows(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    async def who_do_i_see(conn: AsyncConnection, job: ops.JobView) -> str | None:
        tenants = (await conn.execute(text("SELECT DISTINCT tenant_id FROM jobs"))).scalars().all()
        return ",".join(sorted(str(t) for t in tenants))

    spec = register_job(who_do_i_see)
    job_a = await enqueue(tx, TENANT_A_ID, spec)
    job_b = await enqueue(tx, TENANT_B_ID, spec)
    await drain(queue_db)

    assert (await job_row(tx, TENANT_A_ID, job_a.id)).result_ref == str(TENANT_A_ID)
    assert (await job_row(tx, TENANT_B_ID, job_b.id)).result_ref == str(TENANT_B_ID)


async def test_a_cancelled_job_is_not_run(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    calls = 0

    async def handler(conn: AsyncConnection, job: ops.JobView) -> str | None:
        nonlocal calls
        calls += 1
        return None

    spec = register_job(handler)
    job = await enqueue(tx, TENANT_A_ID, spec)
    async with tx(TENANT_A_ID) as conn:
        await ops.transition(conn, job.id, ops.JobStatus.CANCELLED)
    await drain(queue_db)
    assert calls == 0
    assert (await job_row(tx, TENANT_A_ID, job.id)).status == "cancelled"


async def test_one_tenant_cannot_starve_another(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    """5 jobs for A, 1 for B, cap 2 per tenant, 3 worker slots: B starts before A's third ends."""
    running = 0
    peak_a = 0
    log: list[tuple[str, str, float]] = []

    async def handler(conn: AsyncConnection, job: ops.JobView) -> str | None:
        nonlocal running, peak_a
        who = "A" if job.tenant_id == TENANT_A_ID else "B"
        log.append((who, "start", time.monotonic()))
        running += who == "A"
        peak_a = max(peak_a, running)
        await asyncio.sleep(0.6)
        running -= who == "A"
        log.append((who, "end", time.monotonic()))
        return None

    spec = register_job(handler, max_per_tenant=2)
    for _ in range(5):
        await enqueue(tx, TENANT_A_ID, spec)
    await enqueue(tx, TENANT_B_ID, spec)
    await drain_all(queue_db, concurrency=3)

    starts_a = sorted(t for who, kind, t in log if who == "A" and kind == "start")
    ends_a = sorted(t for who, kind, t in log if who == "A" and kind == "end")
    start_b = next(t for who, kind, t in log if who == "B" and kind == "start")
    assert len(starts_a) == 5 and len(ends_a) == 5
    assert peak_a == 2  # the cap held even though a third worker slot was free
    assert start_b < ends_a[2]  # B did not wait for A's third job to finish
    async with tx(TENANT_A_ID) as conn:
        done = (
            await conn.execute(text("SELECT count(*) FROM jobs WHERE status='succeeded'"))
        ).scalar_one()
    assert done == 5


async def test_the_app_role_can_defer_but_cannot_read_the_queue(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    spec = register_job(_noop)
    await enqueue(tx, TENANT_A_ID, spec)  # INSERT through the defer function works
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tx(TENANT_A_ID) as conn:
            await conn.execute(text("SELECT args FROM procrastinate_jobs"))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tx(TENANT_A_ID) as conn:
            await conn.execute(text("UPDATE procrastinate_jobs SET status = 'failed'"))


async def test_the_queue_row_holds_ids_only_and_the_tenant_lock(
    queue_db: FreshDb, tx: Tx, register_job: Callable[..., ops.JobSpec]
) -> None:
    spec = register_job(_noop, max_per_tenant=2)
    job = await enqueue(tx, TENANT_A_ID, spec, {"secret": "do-not-copy"})
    ((args, lock, queue),) = await sfetch(
        queue_db, "SELECT args, lock, queue_name FROM procrastinate_jobs"
    )
    args = json.loads(args)
    assert args["job_id"] == str(job.id) and args["tenant_id"] == str(TENANT_A_ID)
    assert args["actor_id"] == str(ALICE_ID)
    assert "secret" not in str(args) and "do-not-copy" not in str(args)
    assert lock == job_lock(TENANT_A_ID, spec.job_type, 0)
    assert queue == "default"
