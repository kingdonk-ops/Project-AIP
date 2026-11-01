"""DATABASE-05: append-only grants and monthly partitions.

Unit tests cover the pure helpers in ``aip.platform.db.partitions``. Integration tests run on a
real Postgres migrated to head: ``evidence_probe`` is rendered from ``append_only_table.sql.tpl``
(partitioned on ``created_at``) and registered in ``partition_settings``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.fixtures.postgres import JOBS, FreshDb, OwnerSeeder, TenantDb

from aip.platform.db import jobs as partition_jobs
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.partitions import missing_partitions, month_start, partition_name
from aip.platform.db.templates import render_template

TENANT = UUID("00000000-0000-4000-8000-00000000000a")
PROBE_COLUMNS = "body text NOT NULL"

# --- unit -------------------------------------------------------------------------------------


def test_partition_name_is_table_year_month() -> None:
    assert partition_name("audit_log", date(2025, 7, 15)) == "audit_log_2025_07"
    assert partition_name("audit_log", date(2025, 12, 1)) == "audit_log_2025_12"


def test_missing_partitions_lists_this_month_to_months_ahead_minus_existing() -> None:
    assert missing_partitions({"audit_log_2025_07"}, date(2025, 7, 15), 2, table="audit_log") == [
        "audit_log_2025_08",
        "audit_log_2025_09",
    ]


def test_missing_partitions_crosses_the_year_and_ignores_other_tables() -> None:
    existing = {"audit_log_2025_12", "activity_2026_01", "audit_log_default"}
    assert missing_partitions(existing, date(2025, 12, 31), 1, table="audit_log") == [
        "audit_log_2026_01"
    ]
    assert missing_partitions(set(), date(2025, 12, 31), 0, table="audit_log") == [
        "audit_log_2025_12"
    ]


def test_missing_partitions_rejects_a_negative_horizon() -> None:
    with pytest.raises(ValueError, match="months_ahead"):
        missing_partitions(set(), date(2025, 7, 1), -1, table="audit_log")


def test_month_start_adds_whole_months() -> None:
    assert month_start(date(2025, 11, 30), 0) == date(2025, 11, 1)
    assert month_start(date(2025, 11, 30), 3) == date(2026, 2, 1)


# --- integration helpers ----------------------------------------------------------------------


def _today() -> date:
    return datetime.now(UTC).date()


def _next_month_ts() -> datetime:
    start = month_start(_today(), 1)
    return datetime(start.year, start.month, 10, 12, 0, tzinfo=UTC)


async def _ddl(seeder: OwnerSeeder, sql: str) -> None:
    # The seeder and FreshDb.fetch use asyncio.run, so async tests call them in a thread.
    await asyncio.to_thread(seeder.ddl, sql)


async def _db_fetch(db: FreshDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await asyncio.to_thread(db.fetch, sql, *args)


async def _create_probe(
    seeder: OwnerSeeder, table: str = "evidence_probe", months_ahead: int = 3
) -> None:
    await _ddl(
        seeder,
        render_template(
            "append_only_table", table=table, columns=PROBE_COLUMNS, partition_column="created_at"
        ),
    )
    await _ddl(
        seeder,
        "INSERT INTO partition_settings (table_name, months_ahead) "
        f"VALUES ('{table}', {months_ahead})",
    )


def _sqlstate(exc: BaseException) -> str | None:
    orig: Any = getattr(exc, "orig", exc)
    return getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )


@pytest.fixture
async def jobs_engine(migrated_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    engine = create_app_engine(
        EngineSettings(url=migrated_db.role_url(JOBS), pool_size=2, max_overflow=0)
    )
    try:
        yield engine
    finally:
        await engine.dispose()


async def _insert_probe(tenant_db: TenantDb, created_at: datetime) -> str:
    async with tenant_db.with_tenant(TENANT) as conn:
        return (
            await conn.execute(
                text(
                    "INSERT INTO evidence_probe (id, tenant_id, body, created_at) "
                    "VALUES (:id, :t, 'x', :c) RETURNING tableoid::regclass::text"
                ),
                {"id": uuid4(), "t": TENANT, "c": created_at},
            )
        ).scalar_one()


# --- integration: append-only grants ----------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE evidence_probe SET body = 'changed'",
        "DELETE FROM evidence_probe",
        "TRUNCATE evidence_probe",
    ],
)
async def test_app_cannot_update_delete_or_truncate(
    tenant_db: TenantDb, owner_conn_for_seeding_only: OwnerSeeder, statement: str
) -> None:
    await _create_probe(owner_conn_for_seeding_only)
    await _insert_probe(tenant_db, datetime.now(UTC))
    with pytest.raises(DBAPIError) as info:
        async with tenant_db.with_tenant(TENANT) as conn:
            await conn.execute(text(statement))
    assert _sqlstate(info.value) == "42501", info.value


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE evidence_probe SET body = 'changed'",
        "DELETE FROM evidence_probe",
        "TRUNCATE evidence_probe",
    ],
)
async def test_jobs_cannot_update_delete_or_truncate(
    migrated_db: FreshDb, owner_conn_for_seeding_only: OwnerSeeder, statement: str
) -> None:
    await _create_probe(owner_conn_for_seeding_only)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _run_as(migrated_db.role_url(JOBS), statement)


async def _run_as(url: str, sql: str) -> None:
    conn: Any = await asyncpg.connect(url)  # pyright: ignore[reportUnknownMemberType]
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def test_app_can_insert_and_read_its_own_rows(
    tenant_db: TenantDb, owner_conn_for_seeding_only: OwnerSeeder
) -> None:
    await _create_probe(owner_conn_for_seeding_only)
    await _insert_probe(tenant_db, datetime.now(UTC))
    async with tenant_db.with_tenant(TENANT) as conn:
        assert (await conn.execute(text("SELECT count(*) FROM evidence_probe"))).scalar_one() == 1
    async with tenant_db.no_tenant() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM evidence_probe"))).scalar_one() == 0


# --- integration: partition maintenance -------------------------------------------------------


async def test_ensure_partitions_moves_default_rows_and_creates_months_ahead(
    tenant_db: TenantDb, owner_conn_for_seeding_only: OwnerSeeder, jobs_engine: AsyncEngine
) -> None:
    await _create_probe(owner_conn_for_seeding_only, months_ahead=3)
    early = await _insert_probe(tenant_db, _next_month_ts())
    assert early == "evidence_probe_default"

    created = await partition_jobs.ensure_all_partitions(jobs_engine, today=_today())

    expected = [partition_name("evidence_probe", month_start(_today(), n)) for n in range(4)]
    # Scoped to the probe: real append-only tables (SECURITY-02 on) are registered too.
    assert created["evidence_probe"] == expected
    existing = {
        r[0]
        for r in await _db_fetch(
            tenant_db.db,
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = 'evidence_probe'::regclass",
        )
    }
    assert set(expected) <= existing
    next_month = partition_name("evidence_probe", month_start(_today(), 1))
    # The row that arrived early moved out of DEFAULT; a new one goes straight to its month.
    assert await _db_fetch(tenant_db.db, "SELECT count(*) FROM evidence_probe_default") == [(0,)]
    assert await _db_fetch(tenant_db.db, f"SELECT count(*) FROM {next_month}") == [(1,)]
    assert await _insert_probe(tenant_db, _next_month_ts()) == next_month


async def test_ensure_partitions_is_idempotent(
    owner_conn_for_seeding_only: OwnerSeeder, jobs_engine: AsyncEngine
) -> None:
    await _create_probe(owner_conn_for_seeding_only, months_ahead=1)
    first = await partition_jobs.ensure_all_partitions(jobs_engine, today=_today())
    assert len(first["evidence_probe"]) == 2
    again = await partition_jobs.ensure_all_partitions(jobs_engine, today=_today())
    assert "evidence_probe" in again
    assert all(not made for made in again.values())  # nothing new for any registered table


async def test_periodic_task_runs_the_maintenance(
    migrated_db: FreshDb,
    owner_conn_for_seeding_only: OwnerSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aip.platform.db.engine import JOBS_DATABASE_URL_ENV, dispose_jobs_engine

    await _create_probe(owner_conn_for_seeding_only, months_ahead=1)
    monkeypatch.setenv(JOBS_DATABASE_URL_ENV, migrated_db.role_url(JOBS))
    await dispose_jobs_engine()
    try:
        await partition_jobs.ensure_partitions(timestamp=0)
    finally:
        await dispose_jobs_engine()
    next_month = partition_name("evidence_probe", month_start(_today(), 1))
    assert await _db_fetch(migrated_db, "SELECT to_regclass($1)::text", next_month) == [
        (next_month,)
    ]
    task = partition_jobs.ensure_partitions
    assert task.queue == "default"
    assert any(
        p.task is task and p.cron == "17 2 * * *"
        for p in partition_jobs.app.periodic_registry.periodic_tasks.values()
    )


async def test_failures_are_logged_counted_and_raised(
    owner_conn_for_seeding_only: OwnerSeeder,
    jobs_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_probe(owner_conn_for_seeding_only, months_ahead=1)
    # A registered table that is not partitioned: the function refuses it.
    await _ddl(
        owner_conn_for_seeding_only,
        "CREATE TABLE not_partitioned (id uuid PRIMARY KEY);"
        "INSERT INTO partition_settings (table_name) VALUES ('not_partitioned')",
    )
    counted: list[dict[str, str]] = []
    monkeypatch.setattr(
        partition_jobs, "_record_failure", lambda attrs: counted.append(dict(attrs))
    )
    with pytest.raises(partition_jobs.PartitionMaintenanceError, match="not_partitioned"):
        await partition_jobs.ensure_all_partitions(jobs_engine, today=_today())
    assert counted == [{"table": "not_partitioned"}]
    assert any(
        r.levelname == "ERROR" and "db_partition_create_failed" in r.getMessage()
        for r in caplog.records
    )
    # The other table was still maintained.
    next_month = partition_name("evidence_probe", month_start(_today(), 1))
    assert await _db_fetch(
        owner_conn_for_seeding_only.db, "SELECT to_regclass($1)::text", next_month
    ) == [(next_month,)]


async def test_only_aip_jobs_may_run_the_function(
    tenant_db: TenantDb, owner_conn_for_seeding_only: OwnerSeeder, jobs_engine: AsyncEngine
) -> None:
    await _create_probe(owner_conn_for_seeding_only)
    with pytest.raises(DBAPIError) as info:
        async with tenant_db.with_tenant(TENANT) as conn:
            await conn.execute(text("SELECT aip_ensure_partitions('evidence_probe', 3)"))
    assert _sqlstate(info.value) == "42501", info.value
    async with jobs_engine.begin() as conn:
        await conn.execute(text("SELECT aip_ensure_partitions('evidence_probe', 3)"))


async def test_function_refuses_tables_not_in_partition_settings(
    owner_conn_for_seeding_only: OwnerSeeder, jobs_engine: AsyncEngine
) -> None:
    await _ddl(
        owner_conn_for_seeding_only,
        render_template(
            "append_only_table",
            table="unregistered",
            columns=PROBE_COLUMNS,
            partition_column="created_at",
        ),
    )
    with pytest.raises(DBAPIError, match="partition_settings"):
        async with jobs_engine.begin() as conn:
            await conn.execute(text("SELECT aip_ensure_partitions('unregistered', 3)"))


# --- integration: foreign keys to FORCE-RLS tables (DATABASE-09) ------------------------------

_FK_PARENT_DDL = """
CREATE TABLE evidence_probe_parent (
  id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  CONSTRAINT pk_evidence_probe_parent PRIMARY KEY (id),
  CONSTRAINT uq_evidence_probe_parent_id_tenant_id UNIQUE (id, tenant_id)
);
ALTER TABLE evidence_probe_parent ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_probe_parent FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON evidence_probe_parent FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

_FK_CHILD = """
ALTER TABLE evidence_probe_child
  ADD CONSTRAINT fk_evidence_probe_child_parent
    FOREIGN KEY (parent_id, tenant_id) REFERENCES evidence_probe_parent (id, tenant_id);
INSERT INTO partition_settings (table_name, months_ahead) VALUES ('evidence_probe_child', 2);
"""


async def test_ensure_partitions_moves_default_rows_with_a_foreign_key_to_a_force_rls_table(
    owner_conn_for_seeding_only: OwnerSeeder, jobs_engine: AsyncEngine
) -> None:
    seeder = owner_conn_for_seeding_only
    await _ddl(seeder, _FK_PARENT_DDL)
    await _ddl(
        seeder,
        render_template(
            "append_only_table",
            table="evidence_probe_child",
            columns=f"{PROBE_COLUMNS}, parent_id uuid NOT NULL",
            partition_column="created_at",
        ),
    )
    await _ddl(seeder, _FK_CHILD)
    parent, child = uuid4(), uuid4()
    await asyncio.to_thread(
        seeder.insert,
        TENANT,
        f"INSERT INTO evidence_probe_parent (id, tenant_id) VALUES ('{parent}', '{TENANT}');"
        "INSERT INTO evidence_probe_child (id, tenant_id, body, parent_id, created_at) "
        f"VALUES ('{child}', '{TENANT}', 'x', '{parent}', '{_next_month_ts().isoformat()}');",
    )
    db = seeder.db
    assert await _db_fetch(db, "SELECT count(*) FROM evidence_probe_child_default") == [(1,)]

    created = await partition_jobs.ensure_all_partitions(jobs_engine, today=_today())

    expected = [partition_name("evidence_probe_child", month_start(_today(), n)) for n in range(3)]
    assert created["evidence_probe_child"] == expected
    next_month = expected[1]
    assert await _db_fetch(db, "SELECT count(*) FROM evidence_probe_child_default") == [(0,)]
    # Superuser read: the moved row is whole and still joins its parent.
    assert await _db_fetch(
        db,
        f"SELECT c.id, c.parent_id FROM {next_month} AS c "
        "JOIN evidence_probe_parent AS p ON p.id = c.parent_id AND p.tenant_id = c.tenant_id",
    ) == [(child, parent)]
    # The partition carries the foreign key, and the parent table still forces RLS.
    assert await _db_fetch(
        db,
        "SELECT conname::text FROM pg_constraint WHERE conrelid = $1::regclass AND contype = 'f'",
        next_month,
    ) == [("fk_evidence_probe_child_parent",)]
    assert await _db_fetch(
        db,
        "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'evidence_probe_parent'::regclass",
    ) == [(True,)]


async def test_workflow_definition_audit_gets_its_partitions_with_rows_in_default(
    migrated_db: FreshDb, owner_conn_for_seeding_only: OwnerSeeder, jobs_engine: AsyncEngine
) -> None:
    await asyncio.to_thread(
        migrated_db.execute,
        "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
        f"('{TENANT}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active');",
    )
    definition = uuid4()
    await asyncio.to_thread(
        owner_conn_for_seeding_only.insert,
        TENANT,
        "INSERT INTO workflow_definitions (id, tenant_id, record_type, key, version, status, "
        "states, transitions, initial_state) VALUES "
        f"('{definition}', '{TENANT}', 'probe', 'probe', 1, 'active', '[]', '[]', 'draft');"
        "INSERT INTO workflow_definition_audit (id, tenant_id, definition_id, change, created_at) "
        f"VALUES ('{uuid4()}', '{TENANT}', '{definition}', '{{}}', "
        f"'{_next_month_ts().isoformat()}');",
    )

    created = await partition_jobs.ensure_all_partitions(jobs_engine, today=_today())

    next_month = partition_name("workflow_definition_audit", month_start(_today(), 1))
    assert next_month in created["workflow_definition_audit"]
    assert await _db_fetch(migrated_db, f"SELECT definition_id FROM {next_month}") == [
        (definition,)
    ]
    assert await _db_fetch(
        migrated_db, "SELECT count(*) FROM workflow_definition_audit_default"
    ) == [(0,)]


# --- integration: expand/contract conversion ---------------------------------------------------

_LEGACY_DDL = """
CREATE TABLE evidence_probe_legacy (
  id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  body text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_evidence_probe_legacy PRIMARY KEY (id)
);
ALTER TABLE evidence_probe_legacy ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_probe_legacy FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON evidence_probe_legacy FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

_CHECKSUM = (
    "SELECT count(*), md5(string_agg(t::text, ',' ORDER BY id)) FROM evidence_probe_legacy AS t"
)


def test_expand_contract_conversion_keeps_every_row(
    owner_conn_for_seeding_only: OwnerSeeder,
) -> None:
    seeder = owner_conn_for_seeding_only
    seeder.ddl(_LEGACY_DDL)
    seeder.insert(
        TENANT,
        "INSERT INTO evidence_probe_legacy (id, tenant_id, body, created_at) "
        f"SELECT gen_random_uuid(), '{TENANT}', 'row ' || g, "
        "now() - make_interval(days => g % 120) FROM generate_series(1, 1000) AS g;",
    )
    before = seeder.db.fetch(_CHECKSUM)  # superuser: sees every tenant's rows
    assert before[0][0] == 1000

    seeder.ddl(
        render_template(
            "append_only_table",
            table="evidence_probe_legacy_p",
            columns=PROBE_COLUMNS,
            partition_column="created_at",
        )
    )
    seeder.ddl("SELECT aip_convert_to_partitioned('evidence_probe_legacy')")

    assert seeder.db.fetch(_CHECKSUM) == before
    rows = seeder.db.fetch(
        "SELECT c.relkind::text, c.relforcerowsecurity FROM pg_class c "
        "WHERE c.oid = 'evidence_probe_legacy'::regclass"
    )
    assert rows == [("p", True)]
    assert seeder.db.fetch("SELECT to_regclass('evidence_probe_legacy_p')") == [(None,)]
    assert seeder.db.fetch("SELECT to_regclass('evidence_probe_legacy_default')::text") == [
        ("evidence_probe_legacy_default",)
    ]


def test_conversion_refuses_when_the_copy_differs(
    owner_conn_for_seeding_only: OwnerSeeder,
) -> None:
    seeder = owner_conn_for_seeding_only
    seeder.ddl(_LEGACY_DDL)
    seeder.insert(
        TENANT,
        f"INSERT INTO evidence_probe_legacy (id, tenant_id, body) VALUES "
        f"(gen_random_uuid(), '{TENANT}', 'a');",
    )
    seeder.ddl(
        render_template(
            "append_only_table",
            table="evidence_probe_legacy_p",
            columns=PROBE_COLUMNS,
            partition_column="created_at",
        )
    )
    # A row already in the target makes the counts differ: nothing is swapped or dropped.
    seeder.insert(
        TENANT,
        f"INSERT INTO evidence_probe_legacy_p (id, tenant_id, body) VALUES "
        f"(gen_random_uuid(), '{TENANT}', 'stray');",
    )
    with pytest.raises(asyncpg.PostgresError, match=r"copy differs"):
        seeder.ddl("SELECT aip_convert_to_partitioned('evidence_probe_legacy')")
    assert seeder.db.fetch(
        "SELECT relkind::text FROM pg_class WHERE oid = 'evidence_probe_legacy'::regclass"
    ) == [("r",)]


# --- integration: grants revision ---------------------------------------------------------------


def test_partition_settings_is_readable_only_by_jobs(migrated_db: FreshDb) -> None:
    privileges = migrated_db.fetch(
        "SELECT r, has_table_privilege(r, 'partition_settings', 'SELECT'), "
        "has_table_privilege(r, 'partition_settings', 'INSERT') "
        "FROM unnest(ARRAY['aip_app', 'aip_jobs', 'aip_readonly']) AS r ORDER BY r"
    )
    assert privileges == [
        ("aip_app", False, False),
        ("aip_jobs", True, False),
        ("aip_readonly", False, False),
    ]
    can_execute = migrated_db.fetch(
        "SELECT r, has_function_privilege(r, 'aip_ensure_partitions(text, integer)', 'EXECUTE'), "
        "has_function_privilege(r, 'aip_convert_to_partitioned(text)', 'EXECUTE') "
        "FROM unnest(ARRAY['aip_app', 'aip_jobs', 'aip_readonly']) AS r ORDER BY r"
    )
    assert can_execute == [
        ("aip_app", False, False),
        ("aip_jobs", True, False),
        ("aip_readonly", False, False),
    ]
