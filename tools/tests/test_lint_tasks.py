"""Tests for tools/lint_tasks.py (PLAN-R1 step 8)."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lint_tasks"

_spec = importlib.util.spec_from_file_location("lint_tasks", ROOT / "tools" / "lint_tasks.py")
assert _spec and _spec.loader
lint_tasks = importlib.util.module_from_spec(_spec)
sys.modules["lint_tasks"] = lint_tasks
_spec.loader.exec_module(lint_tasks)

VALID = (FIXTURES / "WIDGETS-01.md").read_text(encoding="utf-8")
MIGRATION_STEP = (
    "  - 1. Migration: create `widgets` from `db/templates/tenant_table.sql.tpl`"
    " with `name text NOT NULL`.\n"
)
BOARD = lint_tasks.parse_board((FIXTURES / "BOARD.md").read_text(encoding="utf-8"))


def lint(text: str) -> list[str]:
    return lint_tasks.lint_spec("WIDGETS-01", text, board=BOARD, known_tables=set())


def test_valid_fixture_has_no_findings() -> None:
    assert lint(VALID) == []


def test_backend_path_is_forbidden() -> None:
    text = VALID.replace(
        "  - apps/api/aip/modules/widgets/tables.py", "  - backend/app/modules/x/service.py"
    )
    assert "forbidden path: backend/" in lint(text)


def test_two_migrations() -> None:
    text = VALID.replace(
        "  - apps/api/aip/modules/widgets/tables.py",
        "  - apps/api/migrations/versions/<timestamp>_widgets_more.py",
    )
    assert "more than one migration" in lint(text)


def test_numbered_sql_migration() -> None:
    text = VALID.replace(
        "apps/api/migrations/versions/<timestamp>_widgets_table.py", "db/migrations/0100_x.sql"
    )
    assert "numbered or non-Alembic migration path: db/migrations/0100_x.sql" in lint(text)


def test_twelve_digit_timestamp_is_accepted() -> None:
    text = VALID.replace("<timestamp>_widgets_table.py", "202610190900_widgets_table.py")
    assert lint(text) == []


def test_size_l() -> None:
    assert "size must be XS, S or M" in lint(VALID.replace("| Size | M |", "| Size | L |"))


def test_unknown_dependency() -> None:
    text = VALID.replace("| Depends on | PLAN-R1 |", "| Depends on | PLAN-R1, FOO-99 |")
    assert "unknown dependency FOO-99" in lint(text)


def test_missing_tag() -> None:
    assert "missing extend/harden/port tag" in lint(VALID.replace(" (tag: extend)", ""))


def test_port_without_aip_citation() -> None:
    text = VALID.replace("(tag: extend)", "(tag: port)")
    assert "port tag needs an AIP source citation" in lint(text)
    assert lint(text.replace("(tag: port)", "(tag: port; AIP source: TASKS §48)")) == []


def test_stack_names_and_typescript_under_api() -> None:
    text = VALID.replace(
        "  - apps/api/aip/modules/widgets/routes.py",
        "  - apps/api/aip/modules/widgets/controller.ts",
    )
    text += "\nUse Kysely and BullMQ.\n"
    found = lint(text)
    assert "forbidden path: TypeScript under apps/api/" in found
    assert "forbidden stack name: kysely" in found
    assert "forbidden stack name: bullmq" in found


def test_code_from_two_modules() -> None:
    text = VALID.replace(
        "  - apps/api/aip/modules/widgets/routes.py", "  - apps/api/aip/modules/gadgets/routes.py"
    )
    found = lint(text)
    assert "code from more than one module: gadgets, widgets" in found


def test_unknown_table_in_tests() -> None:
    text = VALID.replace("FROM widgets", "FROM gadgets")
    assert "test names unknown table gadgets" in lint(text)


def test_table_from_a_dependency_is_known() -> None:
    text = VALID.replace("FROM widgets", "FROM gadgets")
    found = lint_tasks.lint_spec(
        "WIDGETS-01", text, board=BOARD, known_tables=set(), dep_names={"gadgets"}
    )
    assert found == []


def test_missing_header_and_marker() -> None:
    text = VALID.replace(
        "<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->", ""
    )
    text = text.replace("| Phase | R1 |\n", "")
    found = lint(text)
    assert "missing hand-written marker" in found
    assert "header table missing: Phase" in found


def test_board_marks_r1_rows_strict() -> None:
    assert BOARD["WIDGETS-01"].strict
    assert not BOARD["LEGACY-01"].strict


@pytest.fixture
def mini_repo(tmp_path: Path) -> Path:
    (tmp_path / "tracking" / "tasks").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "migrations" / "versions").mkdir(parents=True)
    shutil.copy(FIXTURES / "BOARD.md", tmp_path / "tracking" / "BOARD.md")
    shutil.copy(FIXTURES / "WIDGETS-01.md", tmp_path / "tracking" / "tasks" / "WIDGETS-01.md")
    (tmp_path / "tracking" / "tasks" / "WIDGETS-02.md").write_text(
        VALID.replace("WIDGETS-01", "WIDGETS-02")
        .replace("| Size | M |", "| Size | S |")
        .replace("| Depends on | PLAN-R1 |", "| Depends on | WIDGETS-01 |")
        .replace("  - apps/api/migrations/versions/<timestamp>_widgets_table.py\n", "")
        .replace(MIGRATION_STEP, ""),
        encoding="utf-8",
    )
    (tmp_path / "tracking" / "tasks" / "LEGACY-01.md").write_text(
        "# LEGACY-01 — old\n\n- **files**:\n  - backend/app/x.py\n", encoding="utf-8"
    )
    return tmp_path


def test_repo_run_errors_only_for_r1_rows(
    mini_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lint_tasks.main(["--root", str(mini_repo)]) == 0
    out = capsys.readouterr().out
    assert "WARNING: LEGACY-01: forbidden path: backend/" in out
    assert "3 tasks checked, 0 errors" in out


def test_repo_run_fails_on_a_broken_r1_row(
    mini_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = mini_repo / "tracking" / "tasks" / "WIDGETS-02.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("| Size | S |", "| Size | L |"), encoding="utf-8"
    )
    assert lint_tasks.main(["--root", str(mini_repo)]) == 1
    assert "ERROR: WIDGETS-02: size must be XS, S or M" in capsys.readouterr().out


def test_this_repo_has_no_errors() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "lint_tasks.py"), "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert re.search(r"\d+ tasks checked, 0 errors", result.stdout)


def test_r1_waves_become_ready_in_order(tmp_path: Path) -> None:
    """With every P0 row done (except hardening and Later rows), the first R1 wave is ready and the
    re-homed rows stay put (PLAN-R1 integration test)."""
    board = (ROOT / "tracking" / "BOARD.md").read_text(encoding="utf-8")
    lines, section, sub = [], "", ""
    for line in board.splitlines():
        if line.startswith("## "):
            section = line
        if line.startswith("### "):
            sub = line
        row = re.match(r"^(\|\s*\[[A-Z0-9-]+\][^|]*\|(?:[^|]*\|){4})\s*([a-z-]+)\s*(\|.*)$", line)
        if (
            row
            and section == "## P0"
            and "P0-hardening" not in sub
            and "Moved out of P0" not in sub
        ):
            line = f"{row.group(1)} done {row.group(3)}"
        lines.append(line)
    (tmp_path / "tracking" / "tasks").mkdir(parents=True)
    (tmp_path / "tracking" / "BOARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    shutil.copy(ROOT / "tools" / "next_task.py", tmp_path / "tools" / "next_task.py")
    out = subprocess.run(
        [sys.executable, str(tmp_path / "tools" / "next_task.py"), "--all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    ready = {line.split()[0] for line in out.splitlines() if line.strip()}
    # ASSETS-01 and ITEMTYPES-01 have left `todo` (in progress / review / merged), so they are no
    # longer among the ready rows; the other first-wave R1 rows still prove the wave opens once its
    # P0 dependencies are done.
    assert {"APPROVALS-08", "REPORTS-01", "UPLOADS-08"} <= ready
    assert {"TENANCY-06", "OPS-06"} <= ready  # P0-hardening rows
    assert not ready & {
        "TENANCY-04",
        "TESTING-07",
        "TERMS-04",
        "TERMS-06",
        "FORMS-01",
        "INSPECTIONS-01",
    }
    statuses = dict(
        re.findall(r"\[([A-Z0-9-]+)\][^|]*\|(?:[^|]*\|){4}\s*([a-z-]+)", "\n".join(lines))
    )
    assert statuses["DATABASE-03"] == "dropped"
    assert statuses["TESTING-06"] == "dropped"
