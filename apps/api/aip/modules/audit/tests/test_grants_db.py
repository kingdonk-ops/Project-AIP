"""Integration tests for the append-only guards on ``audit_log`` (AUDIT-01).

Proves the database, not just the application, refuses to rewrite the chain: the app role cannot
INSERT/UPDATE/DELETE, the writer role cannot UPDATE/DELETE/TRUNCATE, a trigger stops even the
owner, and no runtime role has BYPASSRLS.
"""

from __future__ import annotations

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import AUDIT_WRITER, FreshDb, TenantDb

from aip.modules.audit.repository import append_audit_entries
from aip.modules.audit.tables import audit_log

from .conftest import Writer, db_connection, owner_conn_with_tenant
from .test_repository_db import _entry

INSERT_SQL = (
    "INSERT INTO audit_log (id, tenant_id, stream, seq, event_type, prev_hash, hash, "
    "occurred_at) VALUES (gen_random_uuid(), :t, 'audit', 1, 'x', "
    "'\\x0000000000000000000000000000000000000000000000000000000000000000'::bytea, "
    "'\\x0000000000000000000000000000000000000000000000000000000000000000'::bytea, now())"
)


async def test_app_role_cannot_write_audit_log(tenant_db: TenantDb) -> None:
    # A fresh transaction per attempt: the first "permission denied" aborts its own transaction.
    for sql in ("UPDATE audit_log SET payload = '{}'::jsonb", "DELETE FROM audit_log", INSERT_SQL):
        async with tenant_db.with_tenant(TENANT_A_ID) as conn:
            with pytest.raises(DBAPIError) as exc:
                await conn.execute(text(sql), {"t": str(TENANT_A_ID)})
            assert "permission denied" in str(exc.value).lower(), sql


async def test_writer_role_cannot_update_delete_or_truncate(writer: Writer) -> None:
    # Seed one row so UPDATE/DELETE would otherwise match it.
    async with writer.tenant(TENANT_A_ID) as conn:
        await append_audit_entries(conn, TENANT_A_ID, "audit", [_entry(1)])
    for sql in (
        "UPDATE audit_log SET payload = '{}'::jsonb",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ):
        async with writer.tenant(TENANT_A_ID) as conn:
            with pytest.raises(DBAPIError) as exc:
                await conn.execute(text(sql))
            assert "permission denied" in str(exc.value).lower(), sql


async def test_owner_cannot_edit_rows_the_trigger_blocks(
    writer: Writer, migrated_db: FreshDb
) -> None:
    async with writer.tenant(TENANT_A_ID) as conn:
        await append_audit_entries(conn, TENANT_A_ID, "audit", [_entry(1)])

    # The owner owns the table (grants do not restrict it) and FORCE RLS lets it see the row once a
    # tenant is set, so only the trigger stops the edit.
    async with owner_conn_with_tenant(migrated_db, TENANT_A_ID) as owner:
        with pytest.raises(asyncpg.PostgresError) as exc:
            await owner.execute("UPDATE audit_log SET event_type = 'x'")
        assert "audit_log is append-only" in str(exc.value)
        with pytest.raises(asyncpg.PostgresError) as exc:
            await owner.execute("DELETE FROM audit_log")
        assert "audit_log is append-only" in str(exc.value)


async def test_no_runtime_role_has_bypassrls(migrated_db: FreshDb) -> None:
    async with db_connection(migrated_db.owner_url) as conn:
        rows = await conn.fetch(
            "SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname = ANY($1::text[])",
            ["aip_app", AUDIT_WRITER],
        )
    assert {r["rolname"]: r["rolbypassrls"] for r in rows} == {
        "aip_app": False,
        AUDIT_WRITER: False,
    }


async def test_app_and_readonly_may_read_audit_log(tenant_db: TenantDb, writer: Writer) -> None:
    async with writer.tenant(TENANT_A_ID) as conn:
        await append_audit_entries(conn, TENANT_A_ID, "audit", [_entry(1)])
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        count = (await conn.execute(audit_log.select())).rowcount
    assert count == 1
