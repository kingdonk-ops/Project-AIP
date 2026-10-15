"""ARCH-07: the outbox dispatcher, subscribers, retries, dead letters and the periodic job.

Integration tests run on real Postgres (migrations applied as ``aip_owner``): the dispatcher claims
as ``aip_jobs`` and runs subscribers as ``aip_app``, exactly as in the worker. Rows that must be
seen across tenants are read (or forced into a state) as the test superuser.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from procrastinate import testing
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aip.platform.context import RequestContext, use_context
from aip.platform.db.engine import (
    EngineSettings,
    create_app_engine,
    dispose_engine,
    dispose_jobs_engine,
)
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.events import jobs as outbox_jobs
from aip.platform.events.dispatcher import (
    LAST_ERROR_MAX,
    DispatchSettings,
    Outcome,
    alert_dead_letter_thresholds,
    backoff,
    dispatch_batch,
    failure_outcome,
)
from aip.platform.events.registry import (
    PLATFORM_OUTBOX_THRESHOLD_EXCEEDED,
    register_platform_events,
)
from aip.platform.events.subscribers import (
    DomainEvent,
    ManifestSubscriberMismatchError,
    SubscriberRegistry,
    owner_of,
    verify_manifest_subscribers,
)
from aip.platform.jobs.app import app as procrastinate_app
from aip.platform.modules.manifest import EventRef
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import APP, JOBS, FreshDb

from .fixtures import SCHEMAS

# --- unit -------------------------------------------------------------------------------------


def test_backoff_doubles_from_the_base() -> None:
    assert backoff(1, base_s=2) == timedelta(seconds=2)
    assert backoff(2, base_s=2) == timedelta(seconds=4)
    assert backoff(3, base_s=2) == timedelta(seconds=8)


def test_backoff_is_capped() -> None:
    assert backoff(30, base_s=2, cap_s=3600) == timedelta(hours=1)


def test_failure_at_the_last_attempt_dead_letters() -> None:
    assert failure_outcome(5, max_attempts=5) is Outcome.DEAD_LETTER
    assert failure_outcome(4, max_attempts=5) is Outcome.RETRY


def test_settings_read_the_outbox_environment() -> None:
    settings = DispatchSettings.from_env(
        {"OUTBOX_BATCH_SIZE": "25", "OUTBOX_BACKOFF_BASE_S": "0.5", "OUTBOX_MAX_ATTEMPTS": "3"}
    )
    assert (settings.batch_size, settings.backoff_base_s, settings.max_attempts) == (25, 0.5, 3)
    assert settings.poll_interval_s == 2 and settings.dead_letter_alert_threshold == 10
    with pytest.raises(ValueError):
        DispatchSettings(poll_interval_s=60)


def test_poll_cron_fires_every_interval_seconds() -> None:
    assert outbox_jobs.poll_cron(2) == "* * * * * */2"
    with pytest.raises(ValueError):
        outbox_jobs.poll_cron(0)


async def _noop(conn: AsyncConnection, event: DomainEvent) -> None:
    return None


def _module(module_id: str, *subscribes: tuple[str, int]) -> Any:
    refs = [EventRef(name=name, version=version) for name, version in subscribes]
    return SimpleNamespace(id=module_id, manifest=SimpleNamespace(subscribes=refs))


def test_a_subscriber_must_be_listed_in_its_manifest() -> None:
    reg = SubscriberRegistry()
    reg.register("widget.created", 1, _noop, "widgets")
    verify_manifest_subscribers([_module("widgets", ("widget.created", 1))], reg)
    with pytest.raises(ManifestSubscriberMismatchError, match=r"widget\.created v1"):
        verify_manifest_subscribers([_module("widgets")], reg)
    # A module this process does not load is not checked.
    verify_manifest_subscribers([_module("other")], reg)


def test_only_loaded_modules_subscribers_are_dispatched() -> None:
    reg = SubscriberRegistry()
    reg.register("widget.created", 1, _noop, "widgets")
    assert reg.for_modules(["widgets"]).for_event("widget.created", 1)
    assert reg.for_modules(["projects"]).for_event("widget.created", 1) == []


def test_the_owner_is_the_module_whose_events_py_registers() -> None:
    def handler() -> None: ...

    handler.__module__ = "aip.modules.search.events"
    assert owner_of(handler) == "search"
    handler.__module__ = "aip.modules.search.service"
    with pytest.raises(ValueError, match=r"events\.py"):
        owner_of(handler)


# --- integration ------------------------------------------------------------------------------


def ctx(tenant: UUID = TENANT_A_ID, actor: UUID | None = ALICE_ID) -> RequestContext:
    return RequestContext(tenant_id=tenant, request_id=f"test-{uuid.uuid4().hex}", actor_id=actor)


@contextlib.asynccontextmanager
async def role_engine(db: FreshDb, role: str) -> AsyncIterator[AsyncEngine]:
    engine = create_app_engine(EngineSettings(url=db.role_url(role)))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def app_engine(migrated_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    async with role_engine(migrated_db, APP) as engine:
        yield engine


@pytest.fixture
async def jobs_engine(migrated_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    async with role_engine(migrated_db, JOBS) as engine:
        yield engine


async def seed(engine: AsyncEngine, tenant: UUID, actor: UUID, count: int) -> list[UUID]:
    c = ctx(tenant, actor)
    ids: list[UUID] = []
    async with use_context(c), with_tenant(c, engine=engine) as conn:
        for _ in range(count):
            widget_id = uuid.uuid4()
            ids.append(
                await emit(
                    conn,
                    "widget.created",
                    1,
                    Aggregate("widget", widget_id),
                    {"widget_id": str(widget_id), "name": "w"},
                    schemas=SCHEMAS,
                )
            )
    return ids


async def su_fetch(db: FreshDb, sql: str) -> list[tuple[Any, ...]]:
    return await asyncio.to_thread(db.fetch, sql)


async def su_execute(db: FreshDb, sql: str) -> None:
    await asyncio.to_thread(db.execute, sql)


def counting(calls: Counter[UUID], *, fail_on: set[UUID] | None = None) -> SubscriberRegistry:
    reg = SubscriberRegistry()

    async def count_widget(conn: AsyncConnection, event: DomainEvent) -> None:
        # Runs as aip_app inside the event's tenant: RLS shows this tenant's rows only.
        tenant = (await conn.execute(text("SELECT current_setting('app.tenant_id')"))).scalar()
        assert tenant == str(event.tenant_id)
        await asyncio.sleep(0)  # let a concurrent dispatcher interleave
        if fail_on and event.id in fail_on:
            raise RuntimeError(f"subscriber refused {event.id}")
        calls[event.id] += 1

    reg.register("widget.created", 1, count_widget, "widgets")
    return reg


async def test_two_dispatchers_deliver_each_event_exactly_once(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    ids = await seed(app_engine, TENANT_A_ID, ALICE_ID, 50)
    ids += await seed(app_engine, TENANT_B_ID, BOB_ID, 50)
    calls: Counter[UUID] = Counter()
    reg = counting(calls)
    settings = DispatchSettings(batch_size=7)
    jobs_b = create_app_engine(EngineSettings(url=migrated_db.role_url(JOBS)))

    async def loop(engine: AsyncEngine) -> None:
        while (await dispatch_batch(engine, app_engine, reg, settings)).claimed:
            pass

    try:
        await asyncio.gather(loop(jobs_engine), loop(jobs_b))
    finally:
        await jobs_b.dispose()
    assert sum(calls.values()) == 100
    assert set(calls) == set(ids) and set(calls.values()) == {1}
    rows = await su_fetch(
        migrated_db, "SELECT count(*) FROM domain_events WHERE published_at IS NULL"
    )
    assert rows == [(0,)]


async def test_a_failing_subscriber_does_not_block_other_events(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    ids = await seed(app_engine, TENANT_A_ID, ALICE_ID, 100)
    bad = ids[40]
    calls: Counter[UUID] = Counter()
    result = await dispatch_batch(
        jobs_engine, app_engine, counting(calls, fail_on={bad}), DispatchSettings(batch_size=100)
    )
    assert (result.claimed, result.published, result.retried) == (100, 99, 1)
    assert bad not in calls and len(calls) == 99
    (row,) = await su_fetch(
        migrated_db,
        "SELECT attempts, last_error, published_at,"
        " extract(epoch FROM next_attempt_at - now()), dead_lettered_at"
        f" FROM domain_events WHERE id = '{bad}'",
    )
    attempts, last_error, published_at, wait_s, dead = row
    assert attempts == 1 and published_at is None and dead is None
    assert last_error == "widgets.count_widget: RuntimeError"  # never the message
    assert 0 < float(wait_s) <= 2.0
    # Not due yet: an immediate second batch leaves it alone.
    again = await dispatch_batch(jobs_engine, app_engine, counting(calls), DispatchSettings())
    assert again.claimed == 0


async def test_the_error_message_is_never_stored(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    (event_id,) = await seed(app_engine, TENANT_A_ID, ALICE_ID, 1)
    reg = SubscriberRegistry()

    async def noisy(conn: AsyncConnection, event: DomainEvent) -> None:
        await conn.execute(
            text("SELECT 1 / 0 WHERE :secret <> ''"), {"secret": "tenant-data" * 500}
        )

    reg.register("widget.created", 1, noisy, "widgets")
    await dispatch_batch(jobs_engine, app_engine, reg)
    ((last_error,),) = await su_fetch(
        migrated_db, f"SELECT last_error FROM domain_events WHERE id = '{event_id}'"
    )
    assert last_error.startswith("widgets.noisy: DBAPIError") and "[22012]" in last_error
    assert "tenant-data" not in last_error and len(last_error) <= LAST_ERROR_MAX


async def test_a_delivery_that_never_finishes_still_dead_letters(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    (event_id,) = await seed(app_engine, TENANT_A_ID, ALICE_ID, 1)
    reg = SubscriberRegistry()

    async def hangs(conn: AsyncConnection, event: DomainEvent) -> None:
        raise asyncio.CancelledError  # the worker cancelled the job mid-delivery

    reg.register("widget.created", 1, hangs, "widgets")
    settings = DispatchSettings(max_attempts=1, lease_s=0.2)
    with pytest.raises(asyncio.CancelledError):
        await dispatch_batch(jobs_engine, app_engine, reg, settings)
    # The try was counted at claim and the event is leased, so nobody takes it at once.
    assert (await dispatch_batch(jobs_engine, app_engine, reg, settings)).claimed == 0
    await asyncio.sleep(0.3)
    result = await dispatch_batch(jobs_engine, app_engine, reg, settings)
    assert (result.claimed, result.dead_lettered) == (1, 1)
    ((attempts, last_error, dead),) = await su_fetch(
        migrated_db,
        "SELECT attempts, last_error, dead_lettered_at IS NOT NULL FROM domain_events"
        f" WHERE id = '{event_id}'",
    )
    assert (attempts, dead) == (2, True) and "lease expired" in last_error


async def test_subscribers_cannot_change_the_payload(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    await seed(app_engine, TENANT_A_ID, ALICE_ID, 1)
    reg = SubscriberRegistry()

    async def meddles(conn: AsyncConnection, event: DomainEvent) -> None:
        event.payload["name"] = "changed"  # type: ignore[index]

    reg.register("widget.created", 1, meddles, "widgets")
    result = await dispatch_batch(jobs_engine, app_engine, reg)
    assert result.retried == 1


async def test_retry_after_dead_letter_redelivers_once(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    (event_id,) = await seed(app_engine, TENANT_A_ID, ALICE_ID, 1)
    calls: Counter[UUID] = Counter()
    once = DispatchSettings(max_attempts=1)
    result = await dispatch_batch(
        jobs_engine, app_engine, counting(calls, fail_on={event_id}), once
    )
    assert result.dead_lettered == 1
    assert await su_fetch(
        migrated_db,
        f"SELECT dead_lettered_at IS NOT NULL FROM domain_events WHERE id = '{event_id}'",
    ) == [(True,)]
    # Dead letters are never claimed again on their own.
    assert (await dispatch_batch(jobs_engine, app_engine, counting(calls), once)).claimed == 0

    async with app_engine.begin() as conn:
        retried = (
            await conn.execute(text("SELECT event_name FROM outbox_retry(:id)"), {"id": event_id})
        ).all()
    assert [r.event_name for r in retried] == ["widget.created"]
    result = await dispatch_batch(jobs_engine, app_engine, counting(calls), once)
    assert result.published == 1 and calls[event_id] == 1
    (row,) = await su_fetch(
        migrated_db,
        "SELECT published_at IS NOT NULL, attempts, dead_lettered_at FROM domain_events"
        f" WHERE id = '{event_id}'",
    )
    assert row == (True, 1, None)  # attempts counts tries; the retry started again at 0
    # Once published, a retry finds nothing to do.
    async with app_engine.begin() as conn:
        again = await conn.execute(text("SELECT * FROM outbox_retry(:id)"), {"id": event_id})
        assert again.first() is None


async def test_discard_needs_a_reason_and_is_final(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    (event_id,) = await seed(app_engine, TENANT_A_ID, ALICE_ID, 1)
    calls: Counter[UUID] = Counter()
    await dispatch_batch(
        jobs_engine,
        app_engine,
        counting(calls, fail_on={event_id}),
        DispatchSettings(max_attempts=1),
    )
    discard = text("SELECT event_name FROM outbox_discard(:id, :reason, :by)")
    with pytest.raises(DBAPIError) as caught:
        async with app_engine.begin() as conn:
            await conn.execute(discard, {"id": event_id, "reason": "   ", "by": ALICE_ID})
    assert getattr(caught.value.orig, "sqlstate", None) == "22023"
    async with app_engine.begin() as conn:
        done = await conn.execute(discard, {"id": event_id, "reason": "bad data", "by": ALICE_ID})
        assert done.scalar_one() == "widget.created"
        assert (
            await conn.execute(text("SELECT * FROM outbox_retry(:id)"), {"id": event_id})
        ).first() is None
        listed = await conn.execute(text("SELECT id FROM outbox_dead_letters(50, NULL)"))
        assert listed.first() is None
    # Write-once: not even the superuser can rewrite the discard decision.
    with pytest.raises(Exception, match="write-once"):
        await su_execute(
            migrated_db,
            f"UPDATE domain_events SET discard_reason = 'other' WHERE id = '{event_id}'",
        )


async def test_published_at_is_write_once(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    (event_id,) = await seed(app_engine, TENANT_A_ID, ALICE_ID, 1)
    await dispatch_batch(jobs_engine, app_engine, SubscriberRegistry())
    with pytest.raises(Exception, match="write-once"):
        await su_execute(
            migrated_db, f"UPDATE domain_events SET published_at = NULL WHERE id = '{event_id}'"
        )


async def test_the_dead_letter_list_never_returns_a_payload(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    ids = await seed(app_engine, TENANT_A_ID, ALICE_ID, 2)
    ids += await seed(app_engine, TENANT_B_ID, BOB_ID, 1)
    calls: Counter[UUID] = Counter()
    await dispatch_batch(
        jobs_engine, app_engine, counting(calls, fail_on=set(ids)), DispatchSettings(max_attempts=1)
    )
    async with app_engine.begin() as conn:  # no tenant bound: still lists every tenant's
        result = await conn.execute(text("SELECT * FROM outbox_dead_letters(2, NULL)"))
        page = result.mappings().all()
        assert "payload" not in list(result.keys())
        rest = await conn.execute(
            text("SELECT id FROM outbox_dead_letters(2, :after)"), {"after": page[-1]["id"]}
        )
        assert len(page) + len(rest.all()) == 3


async def test_the_threshold_alert_is_emitted_once_per_hour(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    register_platform_events()
    ids = await seed(app_engine, TENANT_A_ID, ALICE_ID, 3)
    await seed(app_engine, TENANT_B_ID, BOB_ID, 1)
    calls: Counter[UUID] = Counter()
    await dispatch_batch(
        jobs_engine,
        app_engine,
        counting(calls, fail_on=set(ids)),
        DispatchSettings(max_attempts=1),
    )
    first = await alert_dead_letter_thresholds(jobs_engine, app_engine, threshold=2)
    second = await alert_dead_letter_thresholds(jobs_engine, app_engine, threshold=2)
    assert first == [TENANT_A_ID] and second == []
    rows = await su_fetch(
        migrated_db,
        "SELECT tenant_id, payload::text FROM domain_events"
        f" WHERE event_name = '{PLATFORM_OUTBOX_THRESHOLD_EXCEEDED}'",
    )
    assert [(t, json.loads(p)) for t, p in rows] == [(TENANT_A_ID, {"count": 3, "threshold": 2})]


async def test_dispatch_outbox_runs_on_the_outbox_queue_and_drains(
    migrated_db: FreshDb, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = await seed(app_engine, TENANT_A_ID, ALICE_ID, 5)
    calls: Counter[UUID] = Counter()
    reg = counting(calls)
    monkeypatch.setattr(outbox_jobs, "active_subscribers", lambda: reg)
    monkeypatch.setenv("DATABASE_URL", migrated_db.role_url(APP))
    monkeypatch.setenv("DATABASE_JOBS_URL", migrated_db.role_url(JOBS))
    await dispose_engine()
    await dispose_jobs_engine()

    task = procrastinate_app.tasks["platform.dispatch_outbox"]
    assert task.queue == "outbox"
    connector = testing.InMemoryConnector()
    try:
        with procrastinate_app.replace_connector(connector):
            async with procrastinate_app.open_async():
                await task.defer_async(timestamp=0)
                await procrastinate_app.run_worker_async(
                    queues=["outbox"], wait=False, install_signal_handlers=False
                )
    finally:
        await dispose_engine()
        await dispose_jobs_engine()
    statuses = {job["status"] for job in connector.jobs.values()}
    assert statuses == {"succeeded"}
    assert set(calls) == set(ids)
    rows = await su_fetch(
        migrated_db, "SELECT count(*) FROM domain_events WHERE published_at IS NULL"
    )
    assert rows == [(0,)]
