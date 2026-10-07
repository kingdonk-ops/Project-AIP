"""DATABASE-08: `aip-db lint` rules for files in migrations/versions/."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aip.platform.db.migrator import lint

REPO_VERSIONS = Path(__file__).resolve().parents[3] / "migrations" / "versions"
STANDARD_DOWNGRADE = 'def downgrade() -> None:\n    raise NotImplementedError("forward-only")\n'


def revision_source(
    rev: str = "202610071300",
    down: str | None = "202610071200",
    upgrade: str = '    op.execute("CREATE TABLE widgets (id uuid PRIMARY KEY)")\n',
    downgrade: str = STANDARD_DOWNGRADE,
    header: str = "",
) -> str:
    down_repr = "None" if down is None else f'"{down}"'
    return (
        f'"""fixture revision"""\n{header}\nfrom alembic import op\n\n'
        f'revision: str = "{rev}"\n'
        f"down_revision: str | None = {down_repr}\n"
        "branch_labels = None\ndepends_on = None\n\n\n"
        f"def upgrade() -> None:\n{upgrade}\n\n{downgrade}"
    )


def write_versions(tmp_path: Path, files: dict[str, str]) -> Path:
    versions = tmp_path / "versions"
    versions.mkdir(exist_ok=True)
    baseline = revision_source(
        rev="202610071200",
        down=None,
        upgrade='    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")\n',
    )
    (versions / "202610071200_baseline_extensions.py").write_text(baseline, encoding="utf-8")
    for name, text in files.items():
        (versions / name).write_text(text, encoding="utf-8")
    return versions


def messages(tmp_path: Path, files: dict[str, str]) -> list[str]:
    return [f.message for f in lint.lint_directory(write_versions(tmp_path, files), git_base=None)]


def test_well_formed_revision_has_no_findings(tmp_path: Path) -> None:
    assert messages(tmp_path, {"202610071300_add_widgets.py": revision_source()}) == []


def test_repository_revisions_are_lint_clean() -> None:
    assert lint.lint_directory(REPO_VERSIONS, git_base=None) == []


def test_invalid_filename(tmp_path: Path) -> None:
    assert "invalid migration filename" in messages(tmp_path, {"0001_widgets.py": ""})


def test_revision_must_match_filename_prefix(tmp_path: Path) -> None:
    found = messages(tmp_path, {"202610071300_add_widgets.py": revision_source(rev="202610071301")})
    assert "revision 202610071301 does not match filename prefix 202610071300" in found


def test_downgrade_that_does_work_is_rejected(tmp_path: Path) -> None:
    bad = 'def downgrade() -> None:\n    op.execute("DROP TABLE widgets")\n'
    found = messages(tmp_path, {"202610071300_add_widgets.py": revision_source(downgrade=bad)})
    assert "downgrades are not allowed" in found


def test_session_level_set_is_rejected(tmp_path: Path) -> None:
    up = '    op.execute("SET search_path = x")\n'
    found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=up)})
    assert "session-level SET is forbidden; use set_config(..., true)" in found


def test_set_config_true_is_allowed_but_false_is_not(tmp_path: Path) -> None:
    ok = "    op.execute(\"SELECT set_config('app.tenant_id', '', true)\")\n"
    assert messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=ok)}) == []
    bad = "    op.execute(\"SELECT set_config('app.tenant_id', '', false)\")\n"
    found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=bad)})
    assert "session-level SET is forbidden; use set_config(..., true)" in found


def test_destructive_change_needs_contract_comment(tmp_path: Path) -> None:
    up = '    op.execute("ALTER TABLE t DROP COLUMN c")\n'
    found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=up)})
    assert "destructive change needs a contract comment" in found

    for sql in ("DROP TABLE t", "ALTER TABLE t ALTER COLUMN c SET NOT NULL"):
        up = f'    op.execute("{sql}")\n'
        found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=up)})
        assert "destructive change needs a contract comment" in found, sql

    contracted = revision_source(
        upgrade='    # contract: 202610071200\n    op.execute("ALTER TABLE t DROP COLUMN c")\n',
    )
    assert messages(tmp_path, {"202610071300_x.py": contracted}) == []


def test_contract_comment_must_sit_on_or_just_above_the_call(tmp_path: Path) -> None:
    same_line = revision_source(
        upgrade='    op.execute("DROP TABLE t")  # contract: 202610071200\n',
    )
    assert messages(tmp_path, {"202610071300_x.py": same_line}) == []
    block_above = revision_source(
        upgrade=(
            "    # Contract phase of the widgets split.\n"
            "    # contract: 202610071200\n"
            "    # (expand shipped in 202610071200)\n"
            '    op.execute("DROP TABLE t")\n'
        ),
    )
    assert messages(tmp_path, {"202610071300_x.py": block_above}) == []

    # Anywhere else in the file no longer counts, and one contract covers one call only.
    in_header = revision_source(
        upgrade='    op.execute("DROP TABLE t")\n', header="# contract: 202610071200\n"
    )
    found = messages(tmp_path, {"202610071300_x.py": in_header})
    assert "destructive change needs a contract comment" in found
    second_call = revision_source(
        upgrade=(
            "    # contract: 202610071200\n"
            '    op.execute("DROP TABLE t")\n'
            '    op.execute("DROP TABLE u")\n'
        ),
    )
    findings = lint.lint_directory(
        write_versions(tmp_path, {"202610071300_x.py": second_call}), git_base=None
    )
    assert [f.message for f in findings] == ["destructive change needs a contract comment"]
    assert 'op.execute("DROP TABLE u")' in second_call.splitlines()[findings[0].line - 1]


def test_destructive_change_inside_a_dollar_quoted_body_is_found(tmp_path: Path) -> None:
    for body in (
        "DROP TABLE t;",
        "EXECUTE 'DROP TABLE ' || quote_ident('t');",
        "EXECUTE $q$ALTER TABLE t DROP COLUMN c$q$;",
    ):
        sql = f"DO $$ BEGIN {body} END $$;"
        found = messages(
            tmp_path, {"202610071300_x.py": revision_source(upgrade=f"    op.execute({sql!r})\n")}
        )
        assert "destructive change needs a contract comment" in found, body


def test_session_set_inside_a_dollar_quoted_body_is_found(tmp_path: Path) -> None:
    for body in (
        "SET search_path = x;",
        "PERFORM 1; SET LOCAL statement_timeout = 0;",
        "PERFORM set_config('app.tenant_id', 'x', false);",
    ):
        sql = f"DO $$ BEGIN {body} END $$;"
        found = messages(
            tmp_path, {"202610071300_x.py": revision_source(upgrade=f"    op.execute({sql!r})\n")}
        )
        assert "session-level SET is forbidden; use set_config(..., true)" in found, body
    ok = "DO $$ BEGIN UPDATE t SET a = 1; ALTER ROLE r SET work_mem = '4MB'; END $$;"
    assert (
        messages(
            tmp_path, {"202610071300_x.py": revision_source(upgrade=f"    op.execute({ok!r})\n")}
        )
        == []
    )


def test_escape_string_literals_are_parsed(tmp_path: Path) -> None:
    # One E'' string holding an escaped quote: there is no COMMIT statement here.
    quoted = "SELECT E'it\\'s; COMMIT'"
    assert (
        messages(
            tmp_path,
            {"202610071300_x.py": revision_source(upgrade=f"    op.execute({quoted!r})\n")},
        )
        == []
    )
    # An escaped backslash ends the string, so this COMMIT is real.
    real = "SELECT E'x\\\\'; COMMIT"
    found = messages(
        tmp_path, {"202610071300_x.py": revision_source(upgrade=f"    op.execute({real!r})\n")}
    )
    assert "explicit transaction control (BEGIN/COMMIT) is forbidden" in found
    assert lint.strip_sql("SELECT E'a\\'b', e'c', 'd''e'") == "SELECT '', '', ''"


def test_only_known_statements_at_module_level(tmp_path: Path) -> None:
    for extra in (
        'print("side effect")\n',
        "def helper() -> None:\n    pass\n",
        "if True:\n    x = 1\n",
    ):
        found = messages(tmp_path, {"202610071300_x.py": revision_source() + "\n\n" + extra})
        assert (
            "only a docstring, imports, assignments, upgrade() and downgrade() may be top-level"
            in found
        ), extra


def test_autocommit_block_allows_one_statement_per_execute(tmp_path: Path) -> None:
    two = (
        "    with op.get_context().autocommit_block():\n"
        '        op.execute("CREATE INDEX CONCURRENTLY a ON w (id); "\n'
        '                   "CREATE INDEX CONCURRENTLY b ON w (x)")\n'
    )
    found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=two)})
    assert found == ["autocommit_block allows one statement per op.execute"]


TEMPLATE_IMPORT = "\nfrom aip.platform.db.templates import render_template\n"


def test_render_template_calls_are_rendered_and_linted(tmp_path: Path) -> None:
    ok = '    op.execute(render_template("tenant_table", table="widgets", columns="name text"))\n'
    good = revision_source(upgrade=ok, header=TEMPLATE_IMPORT)
    assert messages(tmp_path, {"202610071300_x.py": good}) == []

    bad = '    op.execute(render_template("tenant_table", table="Widgets", columns="name text"))\n'
    found = messages(
        tmp_path, {"202610071300_x.py": revision_source(upgrade=bad, header=TEMPLATE_IMPORT)}
    )
    assert any(m.startswith("template render failed:") for m in found), found

    dynamic = (
        '    cols = "name text"\n'
        '    op.execute(render_template("tenant_table", table="widgets", columns=cols))\n'
    )
    found = messages(
        tmp_path, {"202610071300_x.py": revision_source(upgrade=dynamic, header=TEMPLATE_IMPORT)}
    )
    assert "only op.execute(raw SQL) is allowed" in found


def test_alembic_operations_other_than_execute_are_rejected(tmp_path: Path) -> None:
    up = '    op.create_table("widgets")\n'
    found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=up)})
    assert "only op.execute(raw SQL) is allowed" in found


def test_non_literal_sql_is_rejected(tmp_path: Path) -> None:
    up = '    name = "widgets"\n    op.execute(f"CREATE TABLE {name} (id int)")\n'
    found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=up)})
    assert "only op.execute(raw SQL) is allowed" in found


def test_autocommit_block_only_for_create_index_concurrently(tmp_path: Path) -> None:
    ok = (
        "    with op.get_context().autocommit_block():\n"
        '        op.execute("CREATE INDEX CONCURRENTLY ix_w ON widgets (id)")\n'
    )
    assert messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=ok)}) == []
    bad = (
        "    with op.get_context().autocommit_block():\n"
        '        op.execute("CREATE TABLE w (id int)")\n'
    )
    found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=bad)})
    assert "autocommit_block is only allowed around CREATE INDEX CONCURRENTLY" in found


def test_explicit_transaction_control_is_rejected(tmp_path: Path) -> None:
    for sql in ("BEGIN; CREATE TABLE w (id int); COMMIT;", "COMMIT", "START TRANSACTION"):
        up = f'    op.execute("{sql}")\n'
        found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=up)})
        assert "explicit transaction control (BEGIN/COMMIT) is forbidden" in found, sql


def test_plpgsql_begin_inside_dollar_quotes_is_allowed(tmp_path: Path) -> None:
    up = (
        '    op.execute("""\n'
        "    DO $$\n    BEGIN\n      PERFORM 1;\n    END\n    $$;\n"
        "    -- BEGIN in a comment is fine too\n"
        "    SELECT 'COMMIT';\n"
        '    """)\n'
    )
    assert messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=up)}) == []


def test_create_extension_only_in_baseline(tmp_path: Path) -> None:
    up = '    op.execute("CREATE EXTENSION IF NOT EXISTS hstore")\n'
    found = messages(tmp_path, {"202610071300_x.py": revision_source(upgrade=up)})
    assert "CREATE EXTENSION is only allowed in the baseline revision" in found


def test_more_than_one_head_is_rejected(tmp_path: Path) -> None:
    found = messages(
        tmp_path,
        {
            "202610071300_a.py": revision_source(rev="202610071300"),
            "202610071301_b.py": revision_source(rev="202610071301"),
        },
    )
    assert "multiple heads: 202610071300, 202610071301" in found


def test_modified_or_deleted_revisions_are_rejected(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    versions = write_versions(tmp_path, {"202610071300_add_widgets.py": revision_source()})
    git("init", "-q", "-b", "main")
    git("-c", "user.email=t@example.test", "-c", "user.name=t", "add", ".")
    git("-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-qm", "base")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    assert lint.lint_directory(versions, git_base="origin/main") == []

    target = versions / "202610071300_add_widgets.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    found = [f.message for f in lint.lint_directory(versions, git_base="origin/main")]
    assert "applied revision modified relative to origin/main" in found

    target.unlink()
    found = [f.message for f in lint.lint_directory(versions, git_base="origin/main")]
    assert "applied revision deleted relative to origin/main" in found


def test_unknown_git_base_is_an_error_not_a_pass(tmp_path: Path) -> None:
    versions = write_versions(tmp_path, {})
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    found = [f.message for f in lint.lint_directory(versions, git_base="origin/nope")]
    assert any(m.startswith("cannot diff against origin/nope") for m in found)


def test_cli_lint_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from aip.platform.db.migrator import cli

    versions = write_versions(tmp_path, {"0001_widgets.py": ""})
    assert cli.main(["lint", "--versions-dir", str(versions), "--no-git"]) == 1
    assert "0001_widgets.py:1: invalid migration filename" in capsys.readouterr().out
    (versions / "0001_widgets.py").unlink()
    assert cli.main(["lint", "--versions-dir", str(versions), "--no-git"]) == 0
