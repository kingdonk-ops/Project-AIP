"""TESTING-13 (review 11 M10): the outbox-lag smoke check, on real Postgres as ``aip_jobs``."""

from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from aip.platform.db.session import JobsRoleError
from aip.platform.events.dispatcher import DispatchSettings, dispatch_batch
from aip.platform.events.lag import OutboxLag, lag_problems, main, outbox_lag
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import APP, JOBS, FreshDb

from .test_dispatcher import counting, role_engine, seed, su_execute


@pytest.fixture
async def app_engine(migrated_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    async with role_engine(migrated_db, APP) as engine:
        yield engine


@pytest.fixture
async def jobs_engine(migrated_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    async with role_engine(migrated_db, JOBS) as engine:
        yield engine


def test_a_drained_outbox_has_no_problems() -> None:
    assert lag_problems(OutboxLag(0, 0.0, 0, 12), max_lag_s=60, max_dead_letters=0) == []
    # Waiting, but younger than the limit: still draining.
    assert lag_problems(OutboxLag(3, 5.0, 0, 12), max_lag_s=60, max_dead_letters=0) == []


def test_an_old_waiting_event_or_a_dead_letter_is_a_problem() -> None:
    (lagging,) = lag_problems(OutboxLag(2, 90.0, 0, 0), max_lag_s=60, max_dead_letters=0)
    assert "2 event(s) waiting" in lagging and "90 s" in lagging
    (dead,) = lag_problems(OutboxLag(0, 0.0, 1, 5), max_lag_s=60, max_dead_letters=0)
    assert "1 dead-lettered" in dead
    assert lag_problems(OutboxLag(0, 0.0, 1, 5), max_lag_s=60, max_dead_letters=1) == []


async def test_the_lag_is_read_across_tenants_and_clears_once_drained(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    ids = await seed(app_engine, TENANT_A_ID, ALICE_ID, 3)
    await su_execute(
        migrated_db,
        "UPDATE domain_events SET occurred_at = now() - interval '5 minutes'",
    )
    lag = await outbox_lag(jobs_engine)
    assert (lag.waiting, lag.dead_lettered, lag.published) == (3, 0, 0)
    assert lag.oldest_waiting_s >= 300
    assert lag_problems(lag, max_lag_s=60, max_dead_letters=0)

    calls: Counter[UUID] = Counter()
    while (
        await dispatch_batch(jobs_engine, app_engine, counting(calls), DispatchSettings())
    ).claimed:
        pass
    assert set(calls) == set(ids)
    drained = await outbox_lag(jobs_engine)
    assert (drained.waiting, drained.oldest_waiting_s, drained.published) == (0, 0.0, 3)
    assert lag_problems(drained, max_lag_s=60, max_dead_letters=0) == []


async def test_the_check_refuses_any_login_but_aip_jobs(app_engine: AsyncEngine) -> None:
    with pytest.raises(JobsRoleError):
        await outbox_lag(app_engine)


def test_the_command_fails_on_a_stuck_outbox_and_passes_once_drained(
    migrated_db: FreshDb, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_JOBS_URL", migrated_db.role_url(JOBS))
    assert main(["--max-lag", "60"]) == 0  # an empty outbox
    assert "OK outbox: waiting=0" in capsys.readouterr().out

    tenant = TENANT_A_ID
    migrated_db.execute(
        "INSERT INTO domain_events (id, tenant_id, event_name, event_version, aggregate_type,"
        " aggregate_id, payload, occurred_at)"
        f" VALUES (gen_random_uuid(), '{tenant}', 'widget.created', 1, 'widget',"
        " gen_random_uuid(), '{}'::jsonb, now() - interval '10 minutes')"
    )
    assert main(["--max-lag", "60", "--wait", "0"]) == 1
    assert "waiting, the oldest for" in capsys.readouterr().err
