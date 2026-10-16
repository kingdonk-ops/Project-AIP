"""OPS-13: the scheduled-job trigger (``python -m aip.modules.ops.schedule``).

Integration tests run the real command against a migrated database as ``aip_app``: tenants A and B
are active, C is suspended.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import AsyncIterator, Iterator
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    _fetch,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

from aip.modules.ops import api as ops
from aip.modules.ops import registry
from aip.modules.ops.schedule import (
    check_schedules,
    enqueue_scheduled,
    idempotency_key,
    main,
    period_key,
    schedules,
)
from aip.platform.db.engine import dispose_engine
from aip.platform.modules.manifest import ModuleManifest

TENANT_C_ID = UUID("00000000-0000-4000-8000-00000000000c")
SEED = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active'), "
    f"('{TENANT_C_ID}', 'Tenant C', 'tenant-c', 'ap-southeast-2', 'suspended');"
)


def manifest(*jobs: str) -> ModuleManifest:
    return ModuleManifest.model_validate(
        {
            "id": "demo",
            "context": "demo",
            "schedules": [{"job": j, "cron": "0 3 1 * *", "period": "month"} for j in jobs],
        }
    )


# --- unit -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("month", "2026-10"),
        ("week", "2026-W42"),
        ("day", "2026-10-16"),
        ("hour", "2026-10-16T13"),
    ],
)
def test_the_period_key_names_the_window_now_falls_in(period: str, expected: str) -> None:
    now = datetime.datetime(2026, 10, 16, 13, 5, tzinfo=datetime.UTC)
    assert period_key(period, now) == expected
    assert idempotency_key("ops.review", expected) == f"schedule:ops.review:{expected}"


def test_a_schedule_naming_an_unregistered_job_fails_the_check() -> None:
    assert check_schedules([manifest("ops.monthly_review")], {"ops.send_email"}) == [
        "demo: schedule names job 'ops.monthly_review', which is not registered"
    ]
    assert check_schedules([manifest("ops.send_email")], {"ops.send_email"}) == []
    assert set(schedules([manifest("a", "b")])) == {"a", "b"}


@pytest.mark.parametrize("cron", ["daily", "0 3 * *", "0 3 * * * *"])
def test_a_schedule_needs_a_five_field_cron(cron: str) -> None:
    with pytest.raises(ValidationError):
        ModuleManifest.model_validate(
            {"id": "demo", "context": "demo", "schedules": [{"job": "x", "cron": cron}]}
        )


def test_every_declared_schedule_names_a_registered_job() -> None:
    assert main(["check"]) == 0


def test_an_unknown_job_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["enqueue", "nobody.registered.this", "--all-tenants"]) == 2
    assert "unknown job 'nobody.registered.this'" in capsys.readouterr().err


# --- integration ------------------------------------------------------------------------------


@pytest.fixture
def job_type() -> Iterator[str]:
    async def handler(conn: AsyncConnection, job: ops.JobView) -> str | None:
        return None

    name = f"test.scheduled.{uuid.uuid4().hex[:10]}"
    ops.register(name, handler, timeout_s=30, max_attempts=1)
    yield name
    registry.unregister(name)


@pytest.fixture
async def db(tenant_db: TenantDb, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[TenantDb]:  # noqa: F811
    await _execute(tenant_db.db.superuser_url, SEED)
    monkeypatch.setenv("DATABASE_URL", tenant_db.db.app_url)
    await dispose_engine()
    yield tenant_db
    await dispose_engine()


async def counts(db: TenantDb, job_type: str) -> tuple[list[tuple[object, ...]], int]:
    per_tenant = await _fetch(
        db.db.superuser_url,
        "SELECT tenant_id, idempotency_key FROM jobs WHERE job_type = $1 ORDER BY tenant_id",
        job_type,
    )
    queued = await _fetch(
        db.db.superuser_url,
        "SELECT count(*) FROM procrastinate_jobs WHERE task_name = $1",
        job_type,
    )
    return per_tenant, int(queued[0][0])


async def test_enqueueing_twice_in_one_period_leaves_one_job(db: TenantDb, job_type: str) -> None:
    first = await enqueue_scheduled(job_type, [TENANT_A_ID], "2026-10")
    again = await enqueue_scheduled(job_type, [TENANT_A_ID], "2026-10")
    assert first[0][1].id == again[0][1].id
    rows, queued = await counts(db, job_type)
    assert rows == [(TENANT_A_ID, f"schedule:{job_type}:2026-10")]
    assert queued == 1
    await enqueue_scheduled(job_type, [TENANT_A_ID], "2026-11")  # the next period is a new job
    assert (await counts(db, job_type))[1] == 2


async def test_all_tenants_enqueues_one_job_per_active_tenant(
    db: TenantDb, job_type: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["enqueue", job_type, "--all-tenants", "--period", "2026-10"]) == 0
    assert main(["enqueue", job_type, "--all-tenants", "--period", "2026-10"]) == 0
    rows, queued = await counts(db, job_type)
    assert [r[0] for r in rows] == [TENANT_A_ID, TENANT_B_ID]  # C is suspended
    assert queued == 2
    assert "2 tenant(s)" in capsys.readouterr().out


async def test_only_aip_app_may_list_tenant_ids(db: TenantDb) -> None:
    async with db.no_tenant() as conn:
        ids = (await conn.execute(text("SELECT ops_active_tenant_ids()"))).scalars().all()
        assert [UUID(str(i)) for i in ids] == [TENANT_A_ID, TENANT_B_ID]
        names = (await conn.execute(text("SELECT count(*) FROM tenants"))).scalar_one()
        assert names == 0  # still nothing readable from the table itself
    rows = await _fetch(
        db.db.superuser_url,
        "SELECT r.rolname FROM pg_roles r WHERE has_function_privilege("
        "r.oid, 'ops_active_tenant_ids()', 'EXECUTE') AND r.rolname LIKE 'aip_%' ORDER BY 1",
    )
    assert [r[0] for r in rows] == ["aip_app", "aip_owner"]
