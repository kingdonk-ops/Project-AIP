"""ENT-01: when the database-size estimate runs; per-tenant, single-pass and replica modes."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.tenancy.entitlements.db_estimate import (
    DbEstimateConfigError,
    PerTenantEstimator,
    SinglePassEstimator,
    configured_method,
    db_estimate_due,
)
from aip.modules.tenancy.entitlements.service import EntitlementService
from aip.modules.tenancy.entitlements.snapshot_cli import build_estimator, main, run

from .conftest import FakeClock, su_execute, su_fetch

PERIOD = date(2026, 10, 1)

# --- schedule (unit) --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "due"),
    [
        (date(2026, 10, 18), True),  # Sunday
        (date(2026, 10, 19), False),  # Monday mid-month
        (date(2026, 10, 15), False),  # Thursday
        (date(2026, 10, 31), True),  # last day of the month (a Saturday)
        (date(2027, 2, 28), True),  # last day of a short month
        (date(2028, 2, 28), False),  # leap year: the 29th is the last day
        (date(2028, 2, 29), True),
    ],
)
def test_the_estimate_runs_on_sundays_and_at_month_end(day: date, due: bool) -> None:
    assert db_estimate_due(day) is due


def test_settings_are_validated() -> None:
    assert configured_method("") == "per_tenant"
    assert configured_method("single_pass") == "single_pass"
    with pytest.raises(DbEstimateConfigError):
        configured_method("nightly_magic")
    with pytest.raises(DbEstimateConfigError):
        build_estimator("single_pass", None)  # never on the app connection


def test_the_cli_refuses_single_pass_without_its_own_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = ["--period", "2026-10", "--tenant", str(TENANT_A_ID), "--db-method", "single_pass"]
    assert main(argv) == 2
    assert "single_pass needs its own" in capsys.readouterr().err


# --- the run (integration) ---------------------------------------------------------------------


def projects(tenant: UUID, count: int) -> str:
    padding = "x" * 4000
    values = ", ".join(
        f"(gen_random_uuid(), '{tenant}', 'P{i:03d}', '{padding}', 'draft')" for i in range(count)
    )
    return f"INSERT INTO projects (id, tenant_id, code, name, status) VALUES {values}"


async def estimates(db: TenantDb) -> dict[UUID, tuple[int | None, datetime | None]]:
    rows = await su_fetch(db, "SELECT tenant_id, db_bytes_est, db_estimated_at FROM tenant_usage")
    return {row[0]: (row[1], row[2]) for row in rows}


async def test_the_run_estimates_only_on_estimate_days_and_keeps_the_last_figure(
    db: TenantDb,
) -> None:
    clock = FakeClock(datetime(2026, 10, 15, 16, 0, tzinfo=UTC))  # a Thursday
    service = EntitlementService(connect=db.with_tenant, clock=clock)
    estimator = PerTenantEstimator(db.with_tenant)
    tenants = [TENANT_A_ID]
    await su_execute(db, projects(TENANT_A_ID, 3))

    result = await run(service, tenants, PERIOD, estimator=estimator)
    assert result.estimated is False
    assert (await estimates(db))[TENANT_A_ID] == (None, None)

    clock.advance(timedelta(days=3))  # Sunday
    assert (await run(service, tenants, PERIOD, estimator=estimator)).estimated is True
    sunday = (await estimates(db))[TENANT_A_ID]
    assert sunday[0] is not None and sunday[0] > 0
    assert sunday[1] == clock.now

    clock.advance(timedelta(days=1))  # Monday: the usage row is refreshed, the estimate kept
    assert (await run(service, tenants, PERIOD, estimator=estimator)).estimated is False
    assert (await estimates(db))[TENANT_A_ID] == sunday

    forced = await run(service, tenants, PERIOD, estimator=estimator, db_estimate="always")
    assert forced.estimated is True
    assert (await estimates(db))[TENANT_A_ID][1] == clock.now


async def test_the_page_shows_the_last_estimate_even_from_an_earlier_month(
    db: TenantDb,
) -> None:
    clock = FakeClock(datetime(2026, 10, 31, 16, 0, tzinfo=UTC))  # month end
    service = EntitlementService(connect=db.with_tenant, clock=clock)
    estimator = PerTenantEstimator(db.with_tenant)
    await run(service, [TENANT_A_ID], PERIOD, estimator=estimator)
    clock.advance(timedelta(days=2))  # Monday 2 November: a new month, not an estimate day
    await run(service, [TENANT_A_ID], date(2026, 11, 1), estimator=estimator)
    page = await service.plan_and_usage(TENANT_A_ID)
    assert page.usage_period == date(2026, 11, 1)
    assert page.db_estimate is not None
    assert page.db_estimate.captured_at == datetime(2026, 10, 31, 16, 0, tzinfo=UTC)


async def test_single_pass_and_the_replica_path_agree_on_the_ratio(db: TenantDb) -> None:
    await su_execute(db, projects(TENANT_A_ID, 10))
    await su_execute(db, projects(TENANT_B_ID, 20))
    tenants = [TENANT_A_ID, TENANT_B_ID]

    # Option 3: one GROUP BY scan per table, on a connection that reads across tenants (the test
    # superuser stands in for the role the owner would have to approve).
    single = SinglePassEstimator.from_url(db.db.superuser_url)
    try:
        by_single = await single.estimate(tenants)
    finally:
        await single.engine.dispose()

    # Option 4: per tenant as aip_app on another connection URL (a replica in production).
    built = build_estimator("per_tenant", db.db.app_url)
    try:
        by_replica = await built.estimator.estimate(tenants)
    finally:
        assert built.engine is not None
        await built.engine.dispose()
    by_primary = await PerTenantEstimator(db.with_tenant).estimate(tenants)

    assert by_replica == by_primary
    for sizes in (by_single, by_primary):
        assert 1.8 < sizes[TENANT_B_ID] / sizes[TENANT_A_ID] < 2.2
    # Single pass may see tables aip_app cannot read; it never sees less.
    assert all(by_single[t] >= by_primary[t] for t in tenants)
