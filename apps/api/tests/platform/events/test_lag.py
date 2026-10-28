"""TESTING-13 (review 11 M10): the outbox-lag smoke check, as ``aip_jobs`` on real Postgres."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.events.lag import OutboxLag, check, measure, problems
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    JOBS,
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

SEED_TENANTS_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active')"
)


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await _execute(tenant_db.db.superuser_url, SEED_TENANTS_SQL)
    return tenant_db


@pytest.fixture
async def jobs(db: TenantDb) -> AsyncIterator[AsyncEngine]:
    engine = create_app_engine(EngineSettings(url=db.db.role_url(JOBS)))
    try:
        yield engine
    finally:
        await engine.dispose()


async def insert_event(db: TenantDb, tenant: UUID, *, age_s: int, extra: str = "") -> UUID:
    event_id = uuid4()
    await _execute(
        db.db.superuser_url,
        "INSERT INTO domain_events (id, tenant_id, event_name, event_version, aggregate_type,"
        " aggregate_id, payload, occurred_at) VALUES"
        f" ('{event_id}', '{tenant}', 'widget.created', 1, 'widget', '{uuid4()}',"
        f" '{{\"name\": \"w\"}}'::jsonb, now() - interval '{age_s} seconds')",
    )
    if extra:
        await _execute(
            db.db.superuser_url, f"UPDATE domain_events SET {extra} WHERE id = '{event_id}'"
        )
    return event_id


def test_problems_name_the_lag_and_the_dead_letters() -> None:
    assert problems(OutboxLag(0, 0, None), 60) == []
    assert problems(OutboxLag(3, 0, 59.0), 60) == []
    [lag] = problems(OutboxLag(3, 0, 61.0), 60)
    assert "3 event(s) unpublished" in lag and "61 s" in lag
    [dead] = problems(OutboxLag(0, 2, None), 60)
    assert "2 dead-lettered" in dead


async def test_an_empty_outbox_is_healthy(jobs: AsyncEngine) -> None:
    assert await measure(jobs) == OutboxLag(0, 0, None)


async def test_published_and_discarded_events_do_not_count(db: TenantDb, jobs: AsyncEngine) -> None:
    await insert_event(db, TENANT_A_ID, age_s=600, extra="published_at = now()")
    await insert_event(
        db,
        TENANT_B_ID,
        age_s=600,
        extra="dead_lettered_at = now(), discarded_at = now(), discard_reason = 'test'",
    )
    _, found = await check(jobs, max_age_s=60)
    assert found == []


async def test_an_old_unpublished_event_in_any_tenant_fails_the_check(
    db: TenantDb, jobs: AsyncEngine
) -> None:
    await insert_event(db, TENANT_A_ID, age_s=5)
    await insert_event(db, TENANT_B_ID, age_s=300)  # aip_jobs sees every tenant's events
    lag, found = await check(jobs, max_age_s=60)
    assert lag.pending == 2
    assert lag.oldest_pending_s is not None and lag.oldest_pending_s >= 300
    assert len(found) == 1 and "outbox lag" in found[0]


async def test_a_young_unpublished_event_is_in_flight_not_lag(
    db: TenantDb, jobs: AsyncEngine
) -> None:
    await insert_event(db, TENANT_A_ID, age_s=1)
    lag, found = await check(jobs, max_age_s=60)
    assert (lag.pending, found) == (1, [])


async def test_a_dead_lettered_event_fails_until_an_operator_discards_it(
    db: TenantDb, jobs: AsyncEngine
) -> None:
    event = await insert_event(
        db, TENANT_A_ID, age_s=10, extra="attempts = 1, last_error = 'x', dead_lettered_at = now()"
    )
    lag, found = await check(jobs, max_age_s=60)
    assert lag.dead_lettered == 1 and lag.pending == 0
    assert found and "dead-lettered" in found[0]
    await _execute(
        db.db.superuser_url,
        "UPDATE domain_events SET discarded_at = now(), discard_reason = 'ok'"
        f" WHERE id = '{event}'",
    )
    assert (await check(jobs, max_age_s=60))[1] == []


async def test_wait_rechecks_until_the_dispatcher_catches_up(
    db: TenantDb, jobs: AsyncEngine
) -> None:
    event = await insert_event(db, TENANT_A_ID, age_s=120)
    ticks = iter([0.0, 0.0, 0.5, 10.0])
    calls = 0

    def clock() -> float:
        nonlocal calls
        calls += 1
        if calls == 2:  # after the first measurement, the dispatcher publishes the event
            _publish(db, event)
        return next(ticks)

    _, found = await check(jobs, max_age_s=60, wait_s=5, clock=clock, poll_s=0)
    assert found == []


def _publish(db: TenantDb, event: UUID) -> None:
    import asyncio
    import threading

    # The check holds the running loop; publish from another thread with its own loop.
    worker = threading.Thread(
        target=lambda: asyncio.run(
            _execute(
                db.db.superuser_url,
                f"UPDATE domain_events SET published_at = now() WHERE id = '{event}'",
            )
        )
    )
    worker.start()
    worker.join()
