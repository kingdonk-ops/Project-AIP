"""SECURITY-13 (review 11 M3): least-privilege ``aip_readonly``.

``set_config('app.tenant_id', ...)`` is available to any role, so RLS is only advisory for a role
that runs arbitrary SQL. ``aip_readonly`` therefore must not hold SELECT on the session, auth and
PII tables; reporting goes through the non-PII, tenant-scoped ``reporting.*`` views instead.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest

from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import READONLY, FreshDb, OwnerSeeder, db_connection

# The raw tables whose SELECT grant is revoked from aip_readonly (task spec + review 11 M3).
SENSITIVE_TABLES = (
    "user_session",
    "app_user",
    "auth_event",
    "audit_log",
    "security_audit_events",
    "breach_incidents",
)

# For each reporting view, columns that must never appear because they are PII or session/device
# metadata. The view is the sanctioned reporting surface, so a leak here is the bug this task fixes.
VIEW_FORBIDDEN_COLUMNS: dict[str, set[str]] = {
    "user_session": {"sid_hash", "kc_sid", "ip", "user_agent"},
    "app_user": {"email", "display_name", "idp_alias", "keycloak_user_id", "external_id"},
    "auth_event": {"ip", "user_agent", "detail"},
    "audit_log": {"payload", "reason_for_change", "source_ip", "device", "asset_path"},
    "security_audit_events": {"source_ip", "device", "detail", "target_ref"},
    "breach_incidents": {"description"},
}

INSUFFICIENT_PRIVILEGE = "42501"


def _sqlstate(exc: BaseException) -> str | None:
    orig: Any = getattr(exc, "orig", exc)
    return getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )


async def _fetch_as_readonly(db: FreshDb, sql: str, *, tenant: str | None = None) -> list[Any]:
    async with db_connection(db.role_url(READONLY)) as conn:
        if tenant is not None:
            await conn.execute("SELECT set_config('app.tenant_id', $1, false)", tenant)
        return await conn.fetch(sql)


def test_readonly_has_no_select_on_the_sensitive_tables(migrated_db: FreshDb) -> None:
    """Grant-posture check: aip_readonly keeps none of the revoked SELECT grants; aip_app does."""
    rows = migrated_db.fetch(
        "SELECT t, has_table_privilege('aip_readonly', t, 'SELECT'), "
        "has_table_privilege('aip_app', t, 'SELECT') "
        "FROM unnest($1::text[]) AS t ORDER BY t",
        list(SENSITIVE_TABLES),
    )
    assert rows == sorted((t, False, True) for t in SENSITIVE_TABLES)


async def test_readonly_cannot_read_the_raw_tables_for_any_tenant(migrated_db: FreshDb) -> None:
    """Even with another tenant's id set, a direct read of each raw table is permission denied."""
    for table in SENSITIVE_TABLES:
        with pytest.raises(asyncpg.PostgresError) as excinfo:
            await _fetch_as_readonly(migrated_db, f"SELECT * FROM {table}", tenant=str(TENANT_B_ID))
        assert _sqlstate(excinfo.value) == INSUFFICIENT_PRIVILEGE, table


async def test_reporting_views_expose_no_pii_and_are_security_barrier(
    migrated_db: FreshDb,
) -> None:
    """Each reporting view exists, is a security-barrier view, carries no forbidden column, and is
    selectable by aip_readonly (the sanctioned reporting path)."""
    for view, forbidden in VIEW_FORBIDDEN_COLUMNS.items():
        columns = {
            r[0]
            for r in await asyncio.to_thread(
                migrated_db.fetch,
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'reporting' AND table_name = $1",
                view,
            )
        }
        assert columns, f"reporting.{view} does not exist"
        assert columns.isdisjoint(forbidden), f"reporting.{view} leaks {columns & forbidden}"

        options = await asyncio.to_thread(
            migrated_db.fetch,
            "SELECT unnest(reloptions) FROM pg_class WHERE oid = $1::regclass",
            f"reporting.{view}",
        )
        assert ("security_barrier=true",) in options, f"reporting.{view} is not security_barrier"

        # No permission error: readonly can read the sanctioned surface.
        await _fetch_as_readonly(
            migrated_db, f"SELECT count(*) FROM reporting.{view}", tenant=str(TENANT_A_ID)
        )


async def test_reporting_view_is_tenant_scoped(
    migrated_db: FreshDb, owner_conn_for_seeding_only: OwnerSeeder
) -> None:
    """reporting.app_user still honours tenant isolation: the reader sees its own tenant only."""
    user_id = uuid4()
    await asyncio.to_thread(
        owner_conn_for_seeding_only.insert,
        TENANT_A_ID,
        "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
        f"('{TENANT_A_ID}', 'Kaefer', 'kaefer-demo', 'ap-southeast-2', 'active');\n"
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
        f"('{user_id}', '{TENANT_A_ID}', 'staff', 'seed@kaefer.test', 'Seed User', 'active');",
    )

    own = await _fetch_as_readonly(
        migrated_db,
        f"SELECT id FROM reporting.app_user WHERE id = '{user_id}'",
        tenant=str(TENANT_A_ID),
    )
    assert [r[0] for r in own] == [user_id]

    other = await _fetch_as_readonly(
        migrated_db,
        f"SELECT id FROM reporting.app_user WHERE id = '{user_id}'",
        tenant=str(TENANT_B_ID),
    )
    assert other == []
