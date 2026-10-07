"""DATABASE-08: migrator (`aip-db`), bootstrap, baseline revision, snapshot and schema check."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid

from aip.platform.db.metadata import metadata as declared_metadata
from aip.platform.db.migrator import cli, new, schema_check, snapshot

if TYPE_CHECKING:  # fixtures come from conftest.py; this import is for type hints only
    from tests.platform.db.conftest import FreshDb

REPO_ROOT = Path(__file__).resolve().parents[5]

BASELINE = "202610071200"
HEAD = "202610072200"  # DATABASE-02 platform_roles
EXTENSIONS = {"ltree", "pgcrypto", "pg_trgm", "citext", "btree_gist", "vector"}
OWNER_ERROR = "migrator must run as aip_owner"


# --- unit ------------------------------------------------------------------------------------


def test_new_rejects_a_slug_that_is_not_snake_case(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["new", "Add Widgets"]) == 1
    assert "invalid slug" in capsys.readouterr().err


def test_new_renders_a_lint_clean_revision_from_the_template(migrations_copy: Path) -> None:
    from datetime import UTC, datetime

    from aip.platform.db.migrator import lint

    path = new.create_revision(
        "add_widgets", config_path=migrations_copy, now=datetime(2026, 10, 8, 13, 0, tzinfo=UTC)
    )
    assert path.name == "202610081300_add_widgets.py"
    text = path.read_text(encoding="utf-8")
    assert f'down_revision: str | None = "{HEAD}"' in text
    assert 'raise NotImplementedError("forward-only")' in text
    assert lint.lint_directory(path.parent, git_base=None) == []

    with pytest.raises(new.RevisionExistsError):
        new.create_revision(
            "other", config_path=migrations_copy, now=datetime(2026, 10, 8, 13, 0, tzinfo=UTC)
        )


def test_normalise_strips_pg_dump_version_and_is_deterministic() -> None:
    dump = "\n".join(
        [
            "--",
            "-- PostgreSQL database dump",
            "--",
            "",
            "-- Dumped from database version 16.4",
            "-- Dumped by pg_dump version 16.4",
            "",
            "SET statement_timeout = 0;",
            "SELECT pg_catalog.set_config('search_path', '', false);",
            "",
            "--",
            "-- Name: b; Type: SCHEMA; Schema: -; Owner: aip_owner",
            "--",
            "",
            "CREATE SCHEMA b;",
            "",
            "--",
            "-- Name: a; Type: SCHEMA; Schema: -; Owner: aip_owner",
            "--",
            "",
            "CREATE SCHEMA a;",
            "",
            "--",
            "-- PostgreSQL database dump complete",
            "--",
        ]
    )
    once = snapshot.normalise_dump(dump)
    assert "Dumped by pg_dump version" not in once
    assert "16.4" not in once
    assert "SET statement_timeout" not in once
    assert "set_config" not in once
    assert once.index("CREATE SCHEMA a;") < once.index("CREATE SCHEMA b;")
    assert snapshot.normalise_dump(dump) == once
    assert snapshot.normalise_dump(once) == once
    assert once.endswith("\n")


def test_normalise_keeps_comment_and_set_lines_inside_function_bodies() -> None:
    dump = "\n".join(
        [
            "SET client_encoding = 'UTF8';",
            "--",
            "-- Name: f(); Type: FUNCTION; Schema: public; Owner: aip_owner",
            "--",
            "",
            "CREATE FUNCTION public.f() RETURNS void",
            "    LANGUAGE plpgsql",
            "    AS $_$",
            "BEGIN",
            "-- keep me: part of the function",
            "SET LOCAL statement_timeout = '1s';",
            "  PERFORM 1;",
            "END",
            "$_$;",
            "",
            "SET default_table_access_method = heap;",
            "-- dropped again once the body is closed",
        ]
    )
    once = snapshot.normalise_dump(dump)
    assert "-- keep me: part of the function" in once
    assert "SET LOCAL statement_timeout = '1s';" in once
    assert "SET client_encoding" not in once
    assert "SET default_table_access_method" not in once
    assert "dropped again" not in once
    assert snapshot.normalise_dump(once) == once


def test_declared_metadata_is_a_single_shared_instance() -> None:
    from aip.platform.db import metadata as metadata_module

    assert isinstance(declared_metadata, MetaData)
    assert metadata_module.metadata is declared_metadata


# --- integration (real Postgres 16 + pgvector) ----------------------------------------------


def _version(db: FreshDb) -> list[str]:
    return [r[0] for r in db.fetch("SELECT version_num FROM aip_meta.alembic_version")]


def test_bootstrap_then_migrate_an_empty_database(empty_db: FreshDb) -> None:
    empty_db.bootstrap()
    first = empty_db.aip_db("migrate")
    assert first.returncode == 0, first.stderr
    assert _version(empty_db) == [HEAD]

    extensions = {r[0] for r in empty_db.fetch("SELECT extname FROM pg_extension")}
    assert extensions >= EXTENSIONS

    probe = f"probe_{empty_db.name[-12:]}"
    empty_db.execute(f"CREATE ROLE {probe}")
    try:
        rows = empty_db.fetch("SELECT has_schema_privilege($1, 'public', 'CREATE')", probe)
        assert rows == [(False,)]
    finally:
        empty_db.execute(f"DROP ROLE {probe}")

    owner = empty_db.fetch(
        "SELECT rolsuper, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = 'aip_owner'"
    )
    assert owner == [(False, False, False)]

    # Bootstrap is idempotent; a second migrate applies nothing and exits 0.
    empty_db.bootstrap()
    second = empty_db.aip_db("migrate")
    assert second.returncode == 0, second.stderr
    assert "Running upgrade" in first.stderr
    assert "Running upgrade" not in second.stderr
    assert _version(empty_db) == [HEAD]


def test_concurrent_migrations_serialise_on_the_advisory_lock(empty_db: FreshDb) -> None:
    empty_db.bootstrap()
    procs = [empty_db.aip_db_popen("migrate") for _ in range(2)]
    results = [p.communicate(timeout=120) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], results
    applied = sum(1 for _, err in results if f"-> {HEAD}" in err)
    assert applied == 1, results
    assert _version(empty_db) == [HEAD]


def test_failing_revision_rolls_back_and_keeps_the_previous_head(
    empty_db: FreshDb, migrations_copy: Path
) -> None:
    versions = migrations_copy.parent / "migrations" / "versions"
    (versions / "209901010000_boom.py").write_text(
        '"""boom"""\n\nfrom alembic import op\n\n'
        'revision: str = "209901010000"\n'
        f'down_revision: str | None = "{HEAD}"\n'
        "branch_labels = None\ndepends_on = None\n\n\n"
        "def upgrade() -> None:\n"
        '    op.execute("""CREATE TABLE t1(id int); SELECT 1/0;""")\n\n\n'
        "def downgrade() -> None:\n"
        '    raise NotImplementedError("forward-only")\n',
        encoding="utf-8",
    )
    empty_db.bootstrap()
    result = empty_db.aip_db("migrate", "--config", str(migrations_copy))
    assert result.returncode != 0
    assert "division by zero" in result.stderr
    assert _version(empty_db) == [HEAD]
    assert empty_db.fetch("SELECT to_regclass('public.t1') IS NULL") == [(True,)]


def test_migrate_refuses_any_role_other_than_aip_owner(empty_db: FreshDb) -> None:
    empty_db.bootstrap()
    result = empty_db.aip_db("migrate", url=empty_db.superuser_url)
    assert result.returncode == 1
    assert OWNER_ERROR in result.stderr
    assert empty_db.fetch("SELECT to_regclass('aip_meta.alembic_version') IS NULL") == [(True,)]


def test_baseline_fails_when_vector_was_not_bootstrapped(empty_db: FreshDb) -> None:
    empty_db.bootstrap(skip_vector=True)
    result = empty_db.aip_db("migrate")
    assert result.returncode != 0
    assert "missing extension vector" in result.stderr
    assert empty_db.fetch("SELECT to_regclass('aip_meta.alembic_version') IS NULL") == [(True,)]


def test_check_schema_reports_declared_but_unmigrated_table(
    empty_db: FreshDb, capsys: pytest.CaptureFixture[str]
) -> None:
    empty_db.bootstrap()
    assert empty_db.aip_db("migrate").returncode == 0

    # The real declared tables match the migrated schema.
    assert asyncio.run(schema_check.diff_schema(empty_db.owner_url, declared_metadata)) == []

    fixture = MetaData()
    Table("ghost", fixture, Column("id", Uuid))
    assert schema_check.check_schema(empty_db.owner_url, fixture) == 1
    assert "table ghost declared but not migrated" in capsys.readouterr().out


def test_check_schema_reports_column_differences(empty_db: FreshDb) -> None:
    from sqlalchemy import Integer, Text

    empty_db.bootstrap()
    assert empty_db.aip_db("migrate").returncode == 0
    empty_db.execute("CREATE TABLE public.widgets (id uuid NOT NULL, name text, extra int)")

    fixture = MetaData()
    Table(
        "widgets",
        fixture,
        Column("id", Uuid, nullable=False),
        Column("name", Integer),
        Column("label", Text),
    )
    diffs = asyncio.run(schema_check.diff_schema(empty_db.owner_url, fixture))
    assert "column widgets.label declared but not migrated" in diffs
    assert "column widgets.extra migrated but not declared" in diffs
    assert any(d.startswith("column widgets.name type") for d in diffs), diffs


def test_snapshot_of_a_fresh_database_matches_the_committed_file(
    empty_db: FreshDb, tmp_path: Path
) -> None:
    pg_dump = snapshot.pg_dump_command()
    if shutil.which(pg_dump[0]) is None:
        pytest.skip("pg_dump not installed (the CI db job enforces the snapshot)")
    version = subprocess.run([*pg_dump, "--version"], capture_output=True, text=True, check=True)
    server = empty_db.fetch("SHOW server_version_num")[0][0]
    match = re.search(r"(\d+)\.", version.stdout)
    if match is None or match.group(1) != str(int(server) // 10000):
        pytest.skip(f"pg_dump major differs from the server ({version.stdout.strip()})")

    empty_db.bootstrap()
    assert empty_db.aip_db("migrate").returncode == 0
    out = tmp_path / "schema.snapshot.sql"
    result = empty_db.aip_db("snapshot", "--output", str(out))
    assert result.returncode == 0, result.stderr
    committed = (REPO_ROOT / "db" / "schema.snapshot.sql").read_text(encoding="utf-8")
    assert out.read_text(encoding="utf-8") == committed
