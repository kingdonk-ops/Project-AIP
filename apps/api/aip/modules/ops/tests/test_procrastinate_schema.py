"""OPS-02: the Procrastinate schema migration and the licence/pin guards around it.

The library's ``schema.sql`` starts with a plpgsql ``DO`` block that the migration lint forbids
outside the baseline. The owner approved stripping it, replaced by a fail-closed check. These
tests pin the exact removed text and fail if the installed library or the migration copy drifts,
so a Procrastinate upgrade cannot slip in without a new reviewed migration.
"""

from __future__ import annotations

import ast
import importlib.metadata
from importlib import resources

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from tests.platform.db.conftest import API_DIR, JOBS, FreshDb

MIGRATION = next((API_DIR / "migrations" / "versions").glob("*_procrastinate_schema.py"))

# The text removed from the top of procrastinate 3.10's schema.sql.
REMOVED_DO_BLOCK = """DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;
EXCEPTION
    WHEN OTHERS THEN
        -- On managed PostgreSQL services (e.g. Azure Database for PostgreSQL, Amazon RDS,
        -- Google Cloud SQL), CREATE EXTENSION may fail with various error codes:
        -- insufficient_privilege, feature_not_supported, or provider-specific errors.
        -- Before ignoring, verify the extension actually exists — if it does not exist
        -- and cannot be created, re-raise so the failure is explicit.
        IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'plpgsql') THEN
            RAISE NOTICE 'plpgsql extension already exists, skipping creation.';
        ELSE
            RAISE;
        END IF;
END;
$$;
"""

HEADER = "-- Procrastinate Schema\n\n"
PATCHED_HEADER = "-- Procrastinate Schema (v3.10.0)\n\n"


def installed_schema() -> str:
    return (resources.files("procrastinate.sql") / "schema.sql").read_text(encoding="utf-8")


def migration_statements() -> list[str]:
    """The string literals passed to ``op.execute`` in the migration, in order."""
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    upgrade = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade")
    found: list[str] = []
    for stmt in upgrade.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            arg = stmt.value.args[0]
            assert isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            found.append(arg.value)
    return found


def test_the_library_schema_still_starts_with_the_pinned_do_block() -> None:
    assert installed_schema().startswith(HEADER + REMOVED_DO_BLOCK + "\n")


def test_the_migration_is_the_library_schema_without_that_block() -> None:
    expected = installed_schema().replace(HEADER + REMOVED_DO_BLOCK + "\n", PATCHED_HEADER, 1)
    assert expected != installed_schema()
    assert migration_statements()[1] == expected


def test_the_migration_has_no_do_block_of_its_own() -> None:
    for sql in migration_statements():
        assert not any(line.strip().startswith("DO ") for line in sql.splitlines())


def test_the_stripped_block_is_replaced_by_a_fail_closed_plpgsql_check() -> None:
    check = migration_statements()[0]
    assert "pg_extension" in check and "plpgsql" in check and "1 /" in check


def test_the_plpgsql_check_aborts_when_the_extension_is_missing(empty_db: FreshDb) -> None:
    check = migration_statements()[0]
    empty_db.execute(check)  # plpgsql is installed: passes
    empty_db.execute("DROP EXTENSION plpgsql")
    with pytest.raises(asyncpg.DivisionByZeroError):
        empty_db.execute(check)


def test_procrastinate_is_pinned_to_the_reviewed_minor_version() -> None:
    assert importlib.metadata.version("procrastinate").startswith("3.10.")


def test_procrastinate_is_mit_licensed() -> None:
    meta = importlib.metadata.metadata("procrastinate")
    licence = (meta.get("License-Expression") or meta.get("License") or "") + " ".join(
        meta.get_all("Classifier") or []
    )
    assert "MIT" in licence


def test_worker_and_app_grants_on_the_queue(migrated_db: FreshDb) -> None:
    def can(role: str, table: str, privilege: str) -> bool:
        return bool(
            migrated_db.fetch("SELECT has_table_privilege($1, $2, $3)", role, table, privilege)[0][
                0
            ]
        )

    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert can(JOBS, "procrastinate_jobs", privilege)
    assert not can("aip_app", "procrastinate_jobs", "INSERT")  # column-level only
    allowed = {
        "queue_name",
        "task_name",
        "priority",
        "lock",
        "queueing_lock",
        "args",
        "scheduled_at",
    }
    columns = migrated_db.fetch(
        "SELECT attname FROM pg_attribute WHERE attrelid = 'procrastinate_jobs'::regclass "
        "AND attnum > 0 AND NOT attisdropped "
        "AND has_column_privilege('aip_app', attrelid, attnum, 'INSERT')"
    )
    assert {c[0] for c in columns} == allowed
    assert not can("aip_app", "procrastinate_jobs", "SELECT")  # only the id column
    assert not can("aip_app", "procrastinate_jobs", "UPDATE")
    assert not can("aip_app", "procrastinate_jobs", "DELETE")
    assert not can("aip_readonly", "procrastinate_jobs", "SELECT")
    owner = migrated_db.fetch(
        "SELECT tableowner FROM pg_tables WHERE tablename = 'procrastinate_jobs'"
    )
    assert owner == [("aip_owner",)]
