"""ACCESS-03 coverage: every table with a ``project_id`` record column is project-scoped.

Scans ``pg_catalog`` on the migrated schema. A table with a ``project_id`` column must have a
RESTRICTIVE ``FOR ALL`` policy whose USING and WITH CHECK both call ``access_project_visible``,
unless it is listed in ``project_scope_allowlist.yaml`` with a reason. A new ``project_id`` table
that forgets ``db/templates/project_scoped_policy.sql`` therefore fails CI.

``projects`` is scoped on its own ``id`` (it is the project), so the allow-list mechanism keyed on a
``project_id`` column does not cover it; it is asserted directly.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml  # pyright: ignore[reportMissingModuleSource]

from aip.platform.db.templates import render_template
from tests.fixtures.postgres import FreshDb, _execute, _fetch  # pyright: ignore[reportPrivateUsage]

ALLOWLIST_PATH = Path(__file__).with_name("project_scope_allowlist.yaml")

_PROJECT_ID_TABLES_SQL = """
SELECT c.relname AS name
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
  AND a.attname = 'project_id' AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname
"""

# A restrictive FOR ALL policy whose USING and WITH CHECK both defer to access_project_visible.
_RESTRICTIVE_POLICIES_SQL = """
SELECT c.relname AS name,
       pg_get_expr(p.polqual, p.polrelid) AS qual,
       pg_get_expr(p.polwithcheck, p.polrelid) AS withcheck
FROM pg_policy p
JOIN pg_class c ON c.oid = p.polrelid
WHERE p.polpermissive = false AND p.polcmd = '*'
"""


def load_allowlist() -> list[str]:
    data = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    entries = data.get("tables", []) if isinstance(data, dict) else []
    patterns: list[str] = []
    for entry in entries:
        assert isinstance(entry, dict), f"allow-list entry is not a mapping: {entry!r}"
        table = entry.get("table")
        reason = entry.get("reason")
        assert isinstance(table, str) and table, f"allow-list entry needs a table: {entry!r}"
        assert isinstance(reason, str) and reason.strip(), f"{table}: needs a non-empty reason"
        patterns.append(table)
    return patterns


def _allowlisted(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def _scoped_tables(policies: Sequence[Mapping[str, object]]) -> set[str]:
    scoped: set[str] = set()
    for p in policies:
        qual, withcheck = str(p["qual"] or ""), str(p["withcheck"] or "")
        if all(
            "access_project_visible" in expr and "project_id" in expr for expr in (qual, withcheck)
        ):
            scoped.add(str(p["name"]))
    return scoped


def uncovered(
    tables: Sequence[Mapping[str, object]],
    policies: Sequence[Mapping[str, object]],
    allowlist: Sequence[str],
) -> list[str]:
    scoped = _scoped_tables(policies)
    return [
        f"table {t['name']!s} has project_id but no project scope policy"
        for t in tables
        if str(t["name"]) not in scoped and not _allowlisted(str(t["name"]), allowlist)
    ]


async def test_every_project_id_table_is_scoped_or_allowlisted(migrated_db: FreshDb) -> None:
    url = migrated_db.superuser_url
    tables = await _fetch(url, _PROJECT_ID_TABLES_SQL)
    policies = await _fetch(url, _RESTRICTIVE_POLICIES_SQL)
    tables = [{"name": r[0]} for r in tables]
    policies = [{"name": r[0], "qual": r[1], "withcheck": r[2]} for r in policies]
    violations = uncovered(tables, policies, load_allowlist())
    assert not violations, (
        "project-scope coverage gaps (add db/templates/project_scoped_policy.sql, or allow-list "
        "with a reason):\n" + "\n".join(violations)
    )


async def test_projects_table_has_the_restrictive_scope_policy(migrated_db: FreshDb) -> None:
    rows = await _fetch(
        migrated_db.superuser_url,
        "SELECT pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid)"
        " FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid"
        " WHERE c.relname = 'projects' AND p.polpermissive = false AND p.polcmd = '*'",
    )
    assert rows, "projects must carry a restrictive FOR ALL policy"
    assert any(
        "access_project_visible" in str(q) and "access_project_visible" in str(wc) for q, wc in rows
    ), "the projects restrictive policy must call access_project_visible in USING and WITH CHECK"


async def test_a_new_project_id_table_without_a_policy_is_flagged(migrated_db: FreshDb) -> None:
    url = migrated_db.superuser_url
    await _execute(
        url, render_template("tenant_table", table="widgets", columns="project_id uuid NULL")
    )
    tables = await _fetch(url, _PROJECT_ID_TABLES_SQL)
    policies = await _fetch(url, _RESTRICTIVE_POLICIES_SQL)
    tables = [{"name": r[0]} for r in tables]
    policies = [{"name": r[0], "qual": r[1], "withcheck": r[2]} for r in policies]
    violations = uncovered(tables, policies, load_allowlist())
    assert "table widgets has project_id but no project scope policy" in violations


def test_allowlist_is_well_formed() -> None:
    assert load_allowlist(), (
        "the allow-list should not be empty while legacy project_id tables exist"
    )
