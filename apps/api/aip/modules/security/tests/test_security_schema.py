"""SECURITY-02: the seven security tables, their RLS and the append-only grants.

Integration tests run on real Postgres (migrations applied as ``aip_owner``) and connect as
``aip_app`` inside ``with_tenant``. The unit tests cover the Pydantic models.
"""

from __future__ import annotations

from typing import Any, get_args
from uuid import UUID

import asyncpg
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb, _execute  # pyright: ignore[reportPrivateUsage]

from aip.modules.security.schemas import ControlRecordCreate, ControlStatus
from aip.modules.security.tables import (
    access_reviews,
    breach_incidents,
    control_records,
    data_map_entries,
    evidence_items,
    provenance_entries,
    restore_test_records,
)
from aip.platform.context import new_request_id
from aip.platform.db.schema_guard import inspect_schema

SECURITY_TABLES = (
    control_records,
    evidence_items,
    access_reviews,
    restore_test_records,
    data_map_entries,
    breach_incidents,
    provenance_entries,
)
APPEND_ONLY = ("evidence_items", "restore_test_records", "provenance_entries")
MUTABLE = ("control_records", "access_reviews", "data_map_entries", "breach_incidents")


def new_id() -> UUID:
    return UUID(new_request_id())  # UUIDv7, generated in the app (ADR 0002)


def sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


async def add_control(
    conn: AsyncConnection, key: str = "SEC-01", status: str = "specified"
) -> UUID:
    control_id = new_id()
    await conn.execute(
        text(
            "INSERT INTO control_records (id, tenant_id, control_key, title, status)"
            " VALUES (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid,"
            " :key, 'Tenant isolation', :status)"
        ),
        {"id": control_id, "key": key, "status": status},
    )
    return control_id


async def add_evidence(conn: AsyncConnection, control_id: UUID) -> None:
    await conn.execute(
        text(
            "INSERT INTO evidence_items (id, tenant_id, control_id, evidence_type, collected_at)"
            " VALUES (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid,"
            " :control, 'ci_artefact', now())"
        ),
        {"id": new_id(), "control": control_id},
    )


async def add_restore_test(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "INSERT INTO restore_test_records (id, tenant_id, environment, backup_taken_at,"
            " restore_started_at, result)"
            " VALUES (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid,"
            " 'staging', now() - interval '1 hour', now(), 'pass')"
        ),
        {"id": new_id()},
    )


async def add_provenance(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "INSERT INTO provenance_entries (id, tenant_id, feature, reference_source,"
            " own_spec_path, author, recorded_at)"
            " VALUES (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid,"
            " 'boq', 'public demo video', 'docs/blueprint/modules/boq/README.md', 'ClaudeK', now())"
        ),
        {"id": new_id()},
    )


async def seed_append_only(conn: AsyncConnection) -> None:
    await add_evidence(conn, await add_control(conn))
    await add_restore_test(conn)
    await add_provenance(conn)


# --- unit -------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["specified", "implemented", "proven"])
def test_control_record_create_accepts_the_three_statuses(status: str) -> None:
    model = ControlRecordCreate.model_validate(
        {"controlKey": "SEC-01", "title": "Tenant isolation", "status": status}
    )
    assert model.status == status


def test_control_record_create_rejects_done() -> None:
    with pytest.raises(ValidationError):
        ControlRecordCreate.model_validate(
            {"controlKey": "SEC-01", "title": "Tenant isolation", "status": "done"}
        )


def test_control_status_lists_exactly_the_three_values() -> None:
    assert set(get_args(ControlStatus)) == {"specified", "implemented", "proven"}


def test_mutable_tables_soft_delete_and_append_only_tables_have_no_updated_at() -> None:
    by_name = {t.name: t for t in SECURITY_TABLES}
    for name in MUTABLE:
        assert {"updated_at", "deleted_at"} <= set(by_name[name].c.keys()), name
    for name in APPEND_ONLY:
        assert not {"updated_at", "deleted_at"} & set(by_name[name].c.keys()), name


# --- integration: schema guard and grants ----------------------------------------------------


async def test_schema_guard_passes_for_all_seven_tables(tenant_db: TenantDb) -> None:
    conn: Any = await asyncpg.connect(tenant_db.db.owner_url)  # pyright: ignore[reportUnknownMemberType]
    try:
        names = {t.name for t in SECURITY_TABLES}
        rows = await conn.fetch(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
            " WHERE relname = ANY($1::text[]) AND relkind IN ('r', 'p')",
            list(names),
        )
        assert {r["relname"]: (r["relrowsecurity"], r["relforcerowsecurity"]) for r in rows} == {
            name: (True, True) for name in names
        }
        violations = [v for v in await inspect_schema(conn) if v.table in names]
        assert violations == []
    finally:
        await conn.close()


@pytest.mark.parametrize("table", APPEND_ONLY)
@pytest.mark.parametrize("statement", ["UPDATE {t} SET tenant_id = tenant_id", "DELETE FROM {t}"])
async def test_append_only_tables_refuse_update_and_delete(
    tenant_db: TenantDb, table: str, statement: str
) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        await seed_append_only(conn)
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text(statement.format(t=table)))
    assert sqlstate(caught.value) == "42501", statement


async def app_as(tenant_db: TenantDb, tenant: UUID, sql: str) -> None:
    """Run ``sql`` as ``aip_app`` through asyncpg, with ``app.tenant_id`` bound to ``tenant``."""
    await _execute(
        tenant_db.db.app_url, f"SELECT set_config('app.tenant_id', '{tenant}', true); {sql}"
    )


async def test_update_evidence_items_raises_insufficient_privilege(tenant_db: TenantDb) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        await seed_append_only(conn)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_as(tenant_db, TENANT_A_ID, "UPDATE evidence_items SET evidence_type = 'report'")


async def test_delete_restore_test_records_raises_insufficient_privilege(
    tenant_db: TenantDb,
) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        await add_restore_test(conn)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_as(tenant_db, TENANT_A_ID, "DELETE FROM restore_test_records")


@pytest.mark.parametrize("table", APPEND_ONLY)
async def test_append_only_tables_refuse_truncate_by_aip_jobs(
    tenant_db: TenantDb, table: str
) -> None:
    conn: Any = await asyncpg.connect(tenant_db.db.role_url("aip_jobs"))  # pyright: ignore[reportUnknownMemberType]
    try:
        for statement in (
            f"TRUNCATE {table}",
            f"DELETE FROM {table}",
            f"UPDATE {table} SET id = id",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute(statement)
    finally:
        await conn.close()


@pytest.mark.parametrize("table", MUTABLE)
async def test_mutable_tables_are_soft_delete_only(tenant_db: TenantDb, table: str) -> None:
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text(f"DELETE FROM {table}"))
    assert sqlstate(caught.value) == "42501"


# --- integration: control_records ------------------------------------------------------------


async def test_duplicate_control_key_in_one_tenant_is_a_unique_violation(
    tenant_db: TenantDb,
) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        await add_control(conn, "SEC-01")
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.with_tenant(TENANT_A_ID) as conn:
            await add_control(conn, "SEC-01")
    assert sqlstate(caught.value) == "23505"

    async with tenant_db.with_tenant(TENANT_B_ID) as conn:
        await add_control(conn, "SEC-01")  # another tenant may use the same key


async def test_a_soft_deleted_control_key_can_be_reused(tenant_db: TenantDb) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        await add_control(conn, "SEC-01")
        await conn.execute(
            text("UPDATE control_records SET deleted_at = now() WHERE control_key = 'SEC-01'")
        )
        await add_control(conn, "SEC-01")


async def test_another_tenants_control_record_is_invisible(tenant_db: TenantDb) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        await add_control(conn)
    async with tenant_db.with_tenant(TENANT_B_ID) as conn:
        assert (await conn.execute(text("SELECT count(*) FROM control_records"))).scalar() == 0
    async with tenant_db.no_tenant() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM control_records"))).scalar() == 0
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        assert (await conn.execute(text("SELECT count(*) FROM control_records"))).scalar() == 1


async def test_control_status_done_is_a_check_violation(tenant_db: TenantDb) -> None:
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.with_tenant(TENANT_A_ID) as conn:
            await add_control(conn, status="done")
    assert sqlstate(caught.value) == "23514"


async def test_control_status_check_matches_the_pydantic_literal(tenant_db: TenantDb) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        for n, status in enumerate(get_args(ControlStatus)):
            await add_control(conn, f"SEC-{n}", status)


async def test_evidence_cannot_point_at_another_tenants_control(tenant_db: TenantDb) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        control_a = await add_control(conn)
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.with_tenant(TENANT_B_ID) as conn:
            await add_evidence(conn, control_a)
    assert sqlstate(caught.value) == "23503"


async def test_writes_without_a_tenant_fail_closed(tenant_db: TenantDb) -> None:
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.no_tenant() as conn:
            await conn.execute(
                text(
                    "INSERT INTO control_records (id, tenant_id, control_key, title)"
                    " VALUES (:id, :tenant, 'SEC-01', 'x')"
                ),
                {"id": new_id(), "tenant": TENANT_A_ID},
            )
    assert sqlstate(caught.value) == "42501"
