"""TESTING-02: the schema guard fails on any table lacking tenant_id, FORCE RLS or a policy.

Unit tests need no database. Integration tests migrate a real Postgres to head (``aip-db migrate``)
and create scratch tables as ``aip_owner`` inside a transaction that is always rolled back.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
import yaml  # pyright: ignore[reportMissingModuleSource]

from aip.platform.db.schema_guard import (
    AllowlistEntry,
    AllowlistError,
    Violation,
    format_violations,
    inspect_schema,
    parse_allowlist,
)
from aip.platform.db.templates import render_template
from tests.platform.db.conftest import (  # noqa: F401 - re-exported pytest fixtures
    APP,
    FreshDb,
    execute,
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    with_db,
)

ALLOWLIST_PATH = Path(__file__).with_name("schema_guard_allowlist.yaml")
USING = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def load_allowlist() -> list[AllowlistEntry]:
    return parse_allowlist(yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8")))


# --- unit -------------------------------------------------------------------------------------


def test_allowlist_rejects_an_empty_reason() -> None:
    with pytest.raises(AllowlistError, match="x"):
        parse_allowlist([{"table": "x", "reason": ""}])
    with pytest.raises(AllowlistError, match="x"):
        parse_allowlist([{"table": "x", "reason": "   "}])
    with pytest.raises(AllowlistError, match="x"):
        parse_allowlist([{"table": "x"}])


def test_allowlist_rejects_unknown_checks_keys_and_duplicates() -> None:
    with pytest.raises(AllowlistError, match="x"):
        parse_allowlist([{"table": "x", "reason": "r", "checks_skipped": ["everything"]}])
    with pytest.raises(AllowlistError, match="x"):
        parse_allowlist([{"table": "x", "reason": "r", "colour": "red"}])
    with pytest.raises(AllowlistError, match="x"):
        parse_allowlist([{"table": "x", "reason": "r"}, {"table": "x", "reason": "r"}])


def test_committed_allowlist_is_valid_and_every_entry_has_a_reason() -> None:
    entries = load_allowlist()
    assert {"login_directory", "tenants", "procrastinate_*"} <= {e.table for e in entries}
    assert all(e.reason for e in entries)
    login = next(e for e in entries if e.table == "login_directory")
    assert login.forbid_runtime_privileges


def test_violation_formatting_sorts_by_table() -> None:
    text = format_violations(
        [
            Violation("t_b", "rls", "missing ENABLE ROW LEVEL SECURITY"),
            Violation("t_a", "tenant_id", "missing tenant_id uuid NOT NULL"),
        ]
    )
    assert text.splitlines() == [
        "t_a: missing tenant_id uuid NOT NULL",
        "t_b: missing ENABLE ROW LEVEL SECURITY",
    ]


# --- integration ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def migrated_url(pg_superuser_url: str) -> Iterator[str]:  # noqa: F811
    """Owner URL of a database migrated to head once for the whole module."""
    name = f"aip_test_{uuid.uuid4().hex[:12]}"
    execute(pg_superuser_url, f'CREATE DATABASE "{name}" TEMPLATE template0')
    try:
        db = FreshDb(name=name, superuser_url=with_db(pg_superuser_url, name))
        db.migrate()
        yield db.owner_url
    finally:
        execute(pg_superuser_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@asynccontextmanager
async def scratch(url: str, *statements: str) -> AsyncIterator[Any]:
    """An owner connection in a transaction that is rolled back, with ``statements`` applied."""
    conn: Any = await asyncpg.connect(url)  # pyright: ignore[reportUnknownMemberType]
    tx = conn.transaction()
    await tx.start()
    try:
        for sql in statements:
            await conn.execute(sql)
        yield conn
    finally:
        await tx.rollback()
        await conn.close()


async def guard(url: str, *statements: str) -> list[Violation]:
    async with scratch(url, *statements) as conn:
        return await inspect_schema(conn, load_allowlist())


def lines(violations: list[Violation]) -> list[str]:
    return format_violations(violations).splitlines()


def test_real_schema_has_no_violations(migrated_url: str) -> None:
    assert lines(asyncio.run(guard(migrated_url))) == []


def test_t_bad_is_reported_for_every_missing_control(migrated_url: str) -> None:
    """Negative control: the guard really fails on a planted unprotected table."""
    found = lines(asyncio.run(guard(migrated_url, "CREATE TABLE t_bad (id uuid)")))
    assert found == [
        "t_bad: missing tenant_id uuid NOT NULL",
        "t_bad: missing ENABLE ROW LEVEL SECURITY",
        "t_bad: missing FORCE ROW LEVEL SECURITY",
        "t_bad: missing tenant policy FOR ALL commands",
    ]


def test_nullable_or_wrongly_typed_tenant_id_is_reported(migrated_url: str) -> None:
    found = lines(
        asyncio.run(
            guard(
                migrated_url,
                "CREATE TABLE t_nullable (id uuid, tenant_id uuid)",
                "CREATE TABLE t_text (id uuid, tenant_id text NOT NULL)",
            )
        )
    )
    assert "t_nullable: missing tenant_id uuid NOT NULL" in found
    assert "t_text: missing tenant_id uuid NOT NULL" in found


def _protected(table: str, policy: str) -> list[str]:
    return [
        f"CREATE TABLE {table} (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)",
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        policy,
    ]


def test_policy_without_with_check_is_reported(migrated_url: str) -> None:
    found = lines(
        asyncio.run(
            guard(
                migrated_url,
                *_protected("t_nocheck", f"CREATE POLICY p ON t_nocheck FOR ALL USING ({USING})"),
            )
        )
    )
    assert found == ["t_nocheck: missing WITH CHECK on the tenant policy"]


def test_policy_for_one_command_or_ignoring_the_setting_is_reported(migrated_url: str) -> None:
    found = lines(
        asyncio.run(
            guard(
                migrated_url,
                *_protected(
                    "t_select_only",
                    f"CREATE POLICY p ON t_select_only FOR SELECT USING ({USING})",
                ),
                *_protected(
                    "t_open",
                    "CREATE POLICY p ON t_open FOR ALL USING (true) WITH CHECK (true)",
                ),
            )
        )
    )
    assert found == [
        "t_open: tenant policy does not compare tenant_id with current_setting('app.tenant_id') "
        "in both USING and WITH CHECK",
        "t_select_only: missing tenant policy FOR ALL commands",
    ]


def test_rls_enabled_but_not_forced_is_reported(migrated_url: str) -> None:
    found = lines(
        asyncio.run(
            guard(
                migrated_url,
                "CREATE TABLE t_noforce (id uuid, tenant_id uuid NOT NULL)",
                "ALTER TABLE t_noforce ENABLE ROW LEVEL SECURITY",
                f"CREATE POLICY p ON t_noforce FOR ALL USING ({USING}) WITH CHECK ({USING})",
            )
        )
    )
    assert found == ["t_noforce: missing FORCE ROW LEVEL SECURITY"]


def test_table_from_the_template_has_no_violations(migrated_url: str) -> None:
    sql = render_template("tenant_table", table="t_ok", columns="name text NOT NULL")
    assert asyncio.run(guard(migrated_url, sql)) == []


def test_partitions_are_checked_through_their_parent(migrated_url: str) -> None:
    parent = [
        "CREATE TABLE t_part (id uuid, tenant_id uuid NOT NULL) PARTITION BY HASH (tenant_id)",
        "ALTER TABLE t_part ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE t_part FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY p ON t_part FOR ALL USING ({USING}) WITH CHECK ({USING})",
    ]
    child = "CREATE TABLE t_part_0 PARTITION OF t_part FOR VALUES WITH (MODULUS 1, REMAINDER 0)"
    assert asyncio.run(guard(migrated_url, *parent, child)) == []
    broken = "CREATE TABLE t_part2 (id uuid) PARTITION BY HASH (id)"
    found = lines(asyncio.run(guard(migrated_url, broken)))
    assert found[0] == "t_part2: missing tenant_id uuid NOT NULL"


def test_allow_listed_tables_are_exempt_only_from_the_checks_they_name(migrated_url: str) -> None:
    found = lines(
        asyncio.run(
            guard(
                migrated_url,
                # The real tables may exist by now (TENANCY-01, OPS-02): swap in bare stand-ins. The
                # scratch transaction is rolled back, so the real tables are untouched.
                "DROP TABLE IF EXISTS procrastinate_jobs CASCADE",
                "DROP TABLE IF EXISTS tenants CASCADE",
                "CREATE TABLE procrastinate_jobs (id bigint)",  # exempt: queue internals
                "CREATE TABLE tenants (id uuid)",  # exempt from nothing: keyed on id
            )
        )
    )
    assert found == [
        "tenants: missing id uuid NOT NULL",
        "tenants: missing ENABLE ROW LEVEL SECURITY",
        "tenants: missing FORCE ROW LEVEL SECURITY",
        "tenants: missing tenant policy FOR ALL commands",
    ]


def test_tenants_with_an_id_policy_passes_the_dedicated_rule(migrated_url: str) -> None:
    id_expr = "id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    found = asyncio.run(
        guard(
            migrated_url,
            "DROP TABLE IF EXISTS tenants CASCADE",  # the real one exists since TENANCY-01
            "CREATE TABLE tenants (id uuid PRIMARY KEY, slug text NOT NULL)",
            "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE tenants FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY p ON tenants FOR ALL USING ({id_expr}) WITH CHECK ({id_expr})",
        )
    )
    assert found == []


def test_login_directory_is_exempt_from_rls_but_aip_app_has_no_privileges(
    migrated_url: str,
) -> None:
    async def run() -> None:
        async with scratch(migrated_url) as conn:
            rls = await conn.fetchrow(
                "SELECT relrowsecurity FROM pg_class WHERE relname = 'login_directory'"
            )
            assert rls["relrowsecurity"] is False  # the reason it is allow-listed
            privs = [
                r["privilege_type"]
                for r in await conn.fetch(
                    "SELECT privilege_type FROM information_schema.table_privileges "
                    "WHERE table_name = 'login_directory' AND grantee = $1",
                    APP,
                )
            ]
            assert privs == []
            can_execute = await conn.fetchval(
                "SELECT has_function_privilege($1, 'identity_resolve_login(text, citext)', "
                "'EXECUTE')",
                APP,
            )
            assert can_execute is True

    asyncio.run(run())


def test_a_grant_on_login_directory_to_a_runtime_role_is_reported(migrated_url: str) -> None:
    found = lines(
        asyncio.run(
            guard(
                migrated_url,
                "GRANT SELECT ON login_directory TO aip_app",
                "GRANT UPDATE (idp_alias) ON login_directory TO aip_jobs",
            )
        )
    )
    assert found == [
        "login_directory: aip_app has SELECT (must have none)",
        "login_directory: aip_jobs has UPDATE (must have none)",
    ]
