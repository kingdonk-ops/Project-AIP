"""DATABASE-07: a generated cross-tenant isolation test for every tenant-scoped table.

The cases come from the declared tables (``aip-db check-schema`` keeps them equal to the migrated
schema, and ``test_every_catalogue_table_has_a_case`` checks that here too). One database is
migrated for the whole module; each table gets one row for tenant A and one for tenant B, seeded
as the superuser. The checks then run as ``aip_app`` with tenant A set (``generator.check_table``).
Per-table results are written to ``AIP_ISOLATION_RESULTS`` (CI uploads it as evidence).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from aip.platform.db.migrator.cli import load_declared_tables
from aip.platform.db.templates import render_template
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    APP,
    FreshDb,
    assert_unprivileged_url,
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    execute,
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    with_db,
)

from .generator import (
    Case,
    Result,
    cases,
    catalogue_tables,
    check_table,
    load_overrides,
    write_results,
)

CASES = cases(load_declared_tables())
OVERRIDES = load_overrides()


@pytest.fixture(scope="module")
def isolation_db(pg_superuser_url: str) -> Iterator[FreshDb]:  # noqa: F811
    """One migrated database for every generated case (a migration per table would be too slow)."""
    name = f"aip_iso_{uuid.uuid4().hex[:12]}"
    execute(pg_superuser_url, f'CREATE DATABASE "{name}" TEMPLATE template0')
    db = FreshDb(name=name, superuser_url=with_db(pg_superuser_url, name))
    try:
        db.migrate()
        assert_unprivileged_url(db.role_url(APP))
        yield db
    finally:
        execute(pg_superuser_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="module")
def results(isolation_db: FreshDb) -> dict[str, Result]:
    async def run() -> dict[str, Result]:
        out: dict[str, Result] = {}
        for case in CASES:
            out[case.table] = await check_table(
                isolation_db.superuser_url,
                isolation_db.role_url(APP),
                case,
                OVERRIDES.get(case.table),
                TENANT_A_ID,
                TENANT_B_ID,
            )
        return out

    found = asyncio.run(run())
    target = os.environ.get("AIP_ISOLATION_RESULTS")
    if target:
        write_results(Path(target), list(found.values()))
    return found


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.table)
def test_table_isolates_tenants(results: dict[str, Result], case: Case) -> None:
    result = results[case.table]
    assert result.status in {"passed", "exempt"}, f"{case.table}: {result.message}"


def test_every_catalogue_table_has_a_case(isolation_db: FreshDb) -> None:
    in_db = asyncio.run(catalogue_tables(isolation_db.superuser_url))
    assert in_db == {c.table for c in CASES}


def test_unused_overrides_are_reported() -> None:
    assert set(OVERRIDES) <= {c.table for c in CASES}, "overrides.toml names a table that is gone"


def test_a_permissive_policy_fails_with_cross_tenant_rows(migrated_db: FreshDb) -> None:  # noqa: F811
    ddl = render_template("tenant_table", table="iso_leaky", columns="name text NOT NULL")
    execute(
        migrated_db.owner_url,
        ddl + "DROP POLICY tenant_isolation ON iso_leaky;"
        " CREATE POLICY leaky ON iso_leaky FOR ALL USING (true) WITH CHECK (true);",
    )
    case = Case("iso_leaky", "tenant_id", ("id",))
    result = asyncio.run(
        check_table(
            migrated_db.superuser_url,
            migrated_db.role_url(APP),
            case,
            None,
            TENANT_A_ID,
            TENANT_B_ID,
        )
    )
    assert result.status == "failed"
    assert "cross-tenant read returned rows" in result.message


def test_a_table_with_no_policy_fails(migrated_db: FreshDb) -> None:  # noqa: F811
    ddl = render_template("tenant_table", table="iso_nopolicy", columns="name text NOT NULL")
    execute(migrated_db.owner_url, ddl + "DROP POLICY tenant_isolation ON iso_nopolicy;")
    case = Case("iso_nopolicy", "tenant_id", ("id",))
    result = asyncio.run(
        check_table(
            migrated_db.superuser_url,
            migrated_db.role_url(APP),
            case,
            None,
            TENANT_A_ID,
            TENANT_B_ID,
        )
    )
    assert result.status == "failed"
    assert "own row is not visible" in result.message
