"""AUDIT-02: ``security_audit_events`` is append-only, FORCE RLS and writable only by the writer."""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import FreshDb

from .conftest import db_connection, owner_conn_with_tenant


async def _one(url: str, sql: str) -> Any:
    async with db_connection(url) as conn:
        return await conn.fetchval(sql)


async def test_the_table_forces_rls(migrated_db: FreshDb) -> None:
    row = await _one(
        migrated_db.superuser_url,
        "SELECT relforcerowsecurity AND relrowsecurity FROM pg_class"
        " WHERE relname = 'security_audit_events'",
    )
    assert row is True


@pytest.mark.parametrize(
    ("role", "privilege", "expected"),
    [
        ("aip_audit_writer", "INSERT", True),
        ("aip_audit_writer", "UPDATE", False),
        ("aip_audit_writer", "DELETE", False),
        ("aip_app", "SELECT", True),
        ("aip_app", "INSERT", False),
        ("aip_app", "UPDATE", False),
        ("aip_app", "DELETE", False),
        ("aip_jobs", "INSERT", False),
        ("aip_readonly", "SELECT", True),
        ("aip_readonly", "TRUNCATE", False),
    ],
)
async def test_grants(migrated_db: FreshDb, role: str, privilege: str, expected: bool) -> None:
    got = await _one(
        migrated_db.superuser_url,
        f"SELECT has_table_privilege('{role}', 'security_audit_events', '{privilege}')",
    )
    assert got is expected


async def test_even_the_owner_cannot_update_or_delete(migrated_db: FreshDb) -> None:
    async with owner_conn_with_tenant(migrated_db, TENANT_A_ID) as conn:
        await conn.execute(
            "INSERT INTO security_audit_events (id, tenant_id, seq, event_type, prev_hash, hash,"
            " occurred_at) VALUES (gen_random_uuid(), $1, 1, 'auth.logout',"
            " decode(repeat('00', 32), 'hex'), decode(repeat('11', 32), 'hex'), now())",
            TENANT_A_ID,
        )
        for sql in (
            "UPDATE security_audit_events SET event_type = 'x'",
            "DELETE FROM security_audit_events",
        ):
            with pytest.raises(asyncpg.PostgresError, match="is append-only"):
                await conn.execute(sql)
