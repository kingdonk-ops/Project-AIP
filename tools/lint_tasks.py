#!/usr/bin/env python3
"""Lint task specs against the ADRs (PLAN-R1 step 8). Stdlib only.

Checks every tracking/tasks/<ID>.md whose board status is `todo` or `in-progress`:

  (a) paths only under the ADR 0004 roots; no backend/, frontend/, services/, apps/api/src/,
      TypeScript under apps/api/, 04-code-layout.md or non-ADR stack names (NestJS, Kysely, ...)
  (b) at most one migration, named apps/api/migrations/versions/<timestamp>_<name>.py
  (c) size XS, S or M
  (d) every dependency is on the board
  (e) module code from one module only (apps/api/aip/modules/<m>, apps/web/src/features/<m>)
  (f) a `tag: extend|harden|port`, and `port` only with an `AIP source:` citation
  (g) tables named in tests exist in a migration or in the task's or a dependency's files/steps
  (h) the template header table and the `hand-written` marker

Findings for rows under the board's `## R1` section are errors; elsewhere (P0 specs written before
ADR 0001 or the generator) they are warnings.

  python3 tools/lint_tasks.py            # lint the repo
  python3 tools/lint_tasks.py --root DIR # lint another checkout (tests)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

TASK_ID = r"[A-Z][A-Z0-9]*-[A-Z]?\d+[a-z]?"  # same as tools/next_task.py
ROW = re.compile(r"^\|\s*\[?(" + TASK_ID + r")\]?(?:\([^)]*\))?\s*\|(.*)\|\s*$")
CHECKED_STATUSES = {"todo", "in-progress"}
SIZES = {"XS", "S", "M"}
HEADER_FIELDS = ("Module", "Phase", "Size", "Depends on", "Status")
ALLOWED_ROOTS = (
    "apps/",
    "packages/",
    "db/",
    "config/",
    "infra/",
    "e2e/",
    "tests/",
    "tools/",
    "tracking/",
    "docs/",
    ".github/",
)

FORBIDDEN_PATHS = (
    (re.compile(r"(?<![\w./-])backend/"), "backend/"),
    (re.compile(r"(?<![\w./-])frontend/"), "frontend/"),
    (re.compile(r"(?<![\w./-])services/"), "services/"),
    (re.compile(r"apps/api/src/"), "apps/api/src/"),
    (re.compile(r"(?<![\w./-])db/migrations/"), "db/migrations/"),
    (re.compile(r"04-code-layout\.md"), "04-code-layout.md"),
    (re.compile(r"apps/api/[\w./<>-]*\.tsx?\b"), "TypeScript under apps/api/"),
)
FORBIDDEN_WORDS = re.compile(
    r"\b(nestjs|kysely|node-pg-migrate|bullmq|celery|arq|testcontainers-node)\b", re.IGNORECASE
)
MIGRATION_OK = re.compile(r"^apps/api/migrations/versions/(<timestamp>|\d{12})_[a-z0-9_]+\.py$")
MODULE_PATH = re.compile(r"^apps/(?:api/aip/modules|web/src/features)/([a-z][a-z0-9_]*)/")
TAG = re.compile(r"\btag:\s*(extend|harden|port)\b")
AIP_CITATION = re.compile(r"AIP source:")
MARKER = "<!-- hand-written"
TEST_TABLE = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+([a-z_][a-z0-9_]*)\b|`([a-z_][a-z0-9_]*)` rows?\b"
)
BACKTICKED_IDENT = re.compile(r"`([a-z_][a-z0-9_]*)`")
MIGRATION_TABLE = re.compile(
    r"\b(?:CREATE\s+(?:UNLOGGED\s+)?TABLE(?:\s+IF\s+NOT\s+EXISTS)?|CREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?:MATERIALIZED\s+)?VIEW)\s+([a-z_][a-z0-9_]*)|\btable=\"([a-z_][a-z0-9_]*)\"",
    re.IGNORECASE,
)
# Roles after FROM/TO in GRANT/REVOKE lines, and prose after an uppercase keyword, are not tables.
NOT_TABLES = {
    "aip_app",
    "aip_owner",
    "aip_jobs",
    "aip_readonly",
    "aip_audit_writer",
    "aip_migrator",
    "public",
    "a",
    "an",
    "and",
    "as",
    "by",
    "for",
    "if",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass
class BoardRow:
    id: str
    deps: list[str]
    status: str
    strict: bool


@dataclass
class Spec:
    header: dict[str, str] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    steps: str = ""
    tests: str = ""
    text: str = ""


def parse_board(text: str) -> dict[str, BoardRow]:
    """Board rows by id; `strict` is true for rows under a `## R1` heading."""
    rows: dict[str, BoardRow] = {}
    strict = False
    for line in text.splitlines():
        if line.startswith("## "):
            strict = line.startswith("## R1")
            continue
        m = ROW.match(line)
        if not m:
            continue
        cols = [c.strip() for c in m.group(2).split("|")]
        if len(cols) < 5:
            continue
        rows[m.group(1)] = BoardRow(
            m.group(1), re.findall(TASK_ID, cols[3]), cols[4].strip("`* ").lower(), strict
        )
    return rows


def _block(text: str, name: str) -> str:
    """The lines of a `- **name**:` field up to the next sibling field or heading."""
    m = re.search(r"^- \*\*" + re.escape(name) + r"\*\*:?(.*)$", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end() :]
    end = re.search(r"^(- \*\*|#)", rest, re.MULTILINE)
    return m.group(1) + "\n" + (rest[: end.start()] if end else rest)


def parse_spec(text: str) -> Spec:
    spec = Spec(text=text)
    for line in text.splitlines():
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$", line)
        if m and m.group(1) in HEADER_FIELDS:
            spec.header.setdefault(m.group(1), m.group(2))
    for line in _block(text, "files").splitlines():
        m = re.match(r"^\s+-\s+`?([^\s`,(]+)", line)
        if m and "/" in m.group(1):
            spec.files.append(m.group(1))
    spec.steps = _block(text, "steps")
    spec.tests = _block(text, "tests")
    return spec


def created_names(spec: Spec) -> set[str]:
    """Identifiers a spec names in backticks in its files and steps (the tables it may create)."""
    return set(BACKTICKED_IDENT.findall(spec.steps + "\n" + _block(spec.text, "files")))


def lint_spec(
    task_id: str,
    text: str,
    *,
    board: dict[str, BoardRow],
    known_tables: set[str],
    dep_names: set[str] | None = None,
) -> list[str]:
    """Return the findings for one spec (empty when it passes)."""
    spec = parse_spec(text)
    out: list[str] = []

    # (h) header table and marker
    missing = [f for f in HEADER_FIELDS if f not in spec.header]
    if missing:
        out.append(f"header table missing: {', '.join(missing)}")
    if MARKER not in text:
        out.append("missing hand-written marker")

    # (a) roots and forbidden paths and words
    for pattern, label in FORBIDDEN_PATHS:
        if pattern.search(text):
            out.append(f"forbidden path: {label}")
    for word in sorted({w.lower() for w in FORBIDDEN_WORDS.findall(text)}):
        out.append(f"forbidden stack name: {word}")
    for path in spec.files:
        if not path.startswith(ALLOWED_ROOTS):
            out.append(f"path outside the ADR 0004 roots: {path}")

    # (b) migrations
    migrations = [
        p for p in spec.files if "migrations/" in p or (p.endswith(".sql") and "migration" in p)
    ]
    for path in migrations:
        if not MIGRATION_OK.match(path):
            out.append(f"numbered or non-Alembic migration path: {path}")
    if len(set(migrations)) > 1:
        out.append("more than one migration")

    # (c) size
    size = spec.header.get("Size", "").strip()
    if size and size not in SIZES:
        out.append("size must be XS, S or M")

    # (d) dependencies
    deps = set(re.findall(TASK_ID, spec.header.get("Depends on", "")))
    if task_id in board:
        deps |= set(board[task_id].deps)
    for dep in sorted(deps - {task_id}):
        if dep not in board:
            out.append(f"unknown dependency {dep}")

    # (e) one module
    modules = sorted({m.group(1) for p in spec.files if (m := MODULE_PATH.match(p))})
    if len(modules) > 1:
        out.append(f"code from more than one module: {', '.join(modules)}")
    own = re.search(r"`([a-z_][a-z0-9_]*)`", spec.header.get("Module", ""))
    if own and modules and modules != [own.group(1)]:
        out.append(
            f"code paths in module {', '.join(modules)}, not this task's module {own.group(1)}"
        )

    # (f) tag
    tags = TAG.findall(text)
    if not tags:
        out.append("missing extend/harden/port tag")
    elif "port" in tags and not AIP_CITATION.search(text):
        out.append("port tag needs an AIP source citation")

    # (g) tables named in tests
    allowed = known_tables | created_names(spec) | (dep_names or set())
    for m in TEST_TABLE.finditer(spec.tests):
        table = m.group(1) or m.group(2)
        if table not in allowed and table not in NOT_TABLES:
            out.append(f"test names unknown table {table}")
    return sorted(set(out), key=out.index)


def migration_tables(root: Path) -> set[str]:
    names: set[str] = set()
    for path in sorted((root / "apps" / "api" / "migrations" / "versions").glob("*.py")):
        for a, b in MIGRATION_TABLE.findall(path.read_text(encoding="utf-8")):
            names.add((a or b).lower())
    return names


def _transitive(task_id: str, board: dict[str, BoardRow]) -> set[str]:
    seen: set[str] = set()
    todo = list(board[task_id].deps) if task_id in board else []
    while todo:
        dep = todo.pop()
        if dep in seen or dep not in board:
            continue
        seen.add(dep)
        todo.extend(board[dep].deps)
    return seen


def lint_repo(root: Path) -> tuple[list[str], list[str], int]:
    """Lint every todo/in-progress task; return (errors, warnings, tasks checked)."""
    board = parse_board((root / "tracking" / "BOARD.md").read_text(encoding="utf-8"))
    tasks_dir = root / "tracking" / "tasks"
    known = migration_tables(root)
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    for row in board.values():
        if row.status not in CHECKED_STATUSES:
            continue
        path = tasks_dir / f"{row.id}.md"
        if not path.exists():
            (errors if row.strict else warnings).append(
                f"{row.id}: missing tracking/tasks/{row.id}.md"
            )
            continue
        checked += 1
        dep_names: set[str] = set()
        for dep in _transitive(row.id, board):
            dep_path = tasks_dir / f"{dep}.md"
            if dep_path.exists():
                dep_names |= created_names(parse_spec(dep_path.read_text(encoding="utf-8")))
        findings = lint_spec(
            row.id,
            path.read_text(encoding="utf-8"),
            board=board,
            known_tables=known,
            dep_names=dep_names,
        )
        (errors if row.strict else warnings).extend(f"{row.id}: {f}" for f in findings)
    return errors, warnings, checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint task specs against the ADRs (PLAN-R1).")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--quiet", action="store_true", help="print errors and the summary only")
    args = parser.parse_args(argv)
    errors, warnings, checked = lint_repo(args.root)
    if not args.quiet:
        for w in warnings:
            print("WARNING:", w)
    for e in errors:
        print("ERROR:", e)
    print(f"{checked} tasks checked, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
