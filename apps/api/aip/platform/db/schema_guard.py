"""Schema guard (TESTING-02, ADR 0002): every table carries ``tenant_id`` and fails closed.

``inspect_schema(conn, allowlist)`` reads ``pg_catalog`` directly and returns one ``Violation``
per failed check per table in schema ``public``. Per table it asserts:

- ``tenant_id``: a column of type ``uuid`` that is ``NOT NULL``;
- ``rls``: ``relrowsecurity``;
- ``force_rls``: ``relforcerowsecurity`` (so the owner is bound by the policy too);
- ``policy``: a permissive policy for all commands with both ``USING`` and ``WITH CHECK``, each
  reading ``current_setting('app.tenant_id'...)`` and the tenant column; a missing ``WITH CHECK``
  is reported separately from a missing policy.

Partitions are checked through their parent (``relispartition`` is skipped) and ``alembic_version``
is never inspected. Global tables are exempt only through an allow-list entry that names the table
(or a ``name_*`` prefix), a non-empty reason and the checks it skips. An entry may also move the
tenant column (``tenants`` keys on ``id``) or forbid runtime-role privileges (``login_directory``).

This module imports only the standard library, so the migrator image can ship it, and it takes any
connection with an asyncpg-style ``fetch`` (the later schema-coverage page reuses it). The
allow-list file is parsed by the caller; ``parse_allowlist`` takes the already-loaded data.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = [
    "CHECKS",
    "RUNTIME_ROLES",
    "AllowlistEntry",
    "AllowlistError",
    "Fetcher",
    "Violation",
    "format_violations",
    "inspect_schema",
    "parse_allowlist",
]

CHECKS = ("tenant_id", "rls", "force_rls", "policy")
RUNTIME_ROLES = ("aip_app", "aip_jobs", "aip_readonly")
_ORDER = (*CHECKS, "privileges")
_TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_PATTERN_RE = re.compile(r"^[a-z_][a-z0-9_]*\*?$")
_ENTRY_KEYS = frozenset(
    {"table", "reason", "checks_skipped", "tenant_column", "forbid_runtime_privileges"}
)
_SETTING_RE = re.compile(r"current_setting\(\s*'app\.tenant_id'")


class AllowlistError(ValueError):
    """The allow-list is malformed (the message names the offending table when it has one)."""


class Fetcher(Protocol):
    """The slice of an asyncpg connection the guard needs."""

    async def fetch(self, query: str, /, *args: Any) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class AllowlistEntry:
    table: str
    reason: str
    checks_skipped: frozenset[str] = field(default_factory=frozenset[str])
    tenant_column: str = "tenant_id"
    forbid_runtime_privileges: bool = False

    def matches(self, name: str) -> bool:
        return fnmatch.fnmatchcase(name, self.table)


@dataclass(frozen=True)
class Violation:
    table: str
    check: str
    message: str

    def __str__(self) -> str:
        return f"{self.table}: {self.message}"


def parse_allowlist(data: object) -> list[AllowlistEntry]:
    """Validate loaded allow-list data (a list of mappings, or ``{"tables": [...]}``)."""
    raw: Any = data.get("tables") if isinstance(data, dict) else data  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AllowlistError("allow-list must be a list of {table, reason, checks_skipped}")
    entries: list[AllowlistEntry] = []
    seen: set[str] = set()
    for item in raw:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(item, dict):
            raise AllowlistError(f"allow-list entry is not a mapping: {item!r}")
        entry: dict[str, Any] = item  # pyright: ignore[reportUnknownVariableType]
        table = entry.get("table")
        if not isinstance(table, str) or not _PATTERN_RE.match(table):
            raise AllowlistError(f"allow-list entry has an invalid table name: {table!r}")
        if table in seen:
            raise AllowlistError(f"{table}: listed twice in the allow-list")
        seen.add(table)
        unknown = sorted(set(entry) - _ENTRY_KEYS)
        if unknown:
            raise AllowlistError(f"{table}: unknown allow-list keys {unknown}")
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise AllowlistError(f"{table}: allow-list entry needs a non-empty reason")
        skipped: Any = entry.get("checks_skipped", [])
        if not isinstance(skipped, list) or any(
            not isinstance(c, str) or c not in CHECKS
            for c in skipped  # pyright: ignore[reportUnknownVariableType]
        ):
            raise AllowlistError(f"{table}: checks_skipped must be a list drawn from {CHECKS}")
        column = entry.get("tenant_column", "tenant_id")
        if not isinstance(column, str) or not _IDENT_RE.match(column):
            raise AllowlistError(f"{table}: invalid tenant_column {column!r}")
        forbid = entry.get("forbid_runtime_privileges", False)
        if not isinstance(forbid, bool):
            raise AllowlistError(f"{table}: forbid_runtime_privileges must be true or false")
        entries.append(
            AllowlistEntry(
                table=table,
                reason=reason.strip(),
                checks_skipped=frozenset(skipped),  # pyright: ignore[reportUnknownArgumentType]
                tenant_column=column,
                forbid_runtime_privileges=forbid,
            )
        )
    return entries


def format_violations(violations: Iterable[Violation]) -> str:
    """One line per violation, sorted by table name then check order."""
    order = {c: i for i, c in enumerate(_ORDER)}
    ordered = sorted(violations, key=lambda v: (v.table, order.get(v.check, len(order)), v.message))
    return "\n".join(str(v) for v in ordered)


_TABLES_SQL = """
SELECT c.oid::bigint AS oid, c.relname AS name, c.relrowsecurity AS rls,
       c.relforcerowsecurity AS force_rls
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
  AND c.relname <> 'alembic_version'
ORDER BY c.relname
"""

_COLUMNS_SQL = """
SELECT a.attrelid::bigint AS oid, a.attname AS name,
       format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull AS notnull
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped
"""

_POLICIES_SQL = """
SELECT p.polrelid::bigint AS oid, p.polcmd::text AS cmd, p.polpermissive AS permissive,
       pg_get_expr(p.polqual, p.polrelid) AS qual,
       pg_get_expr(p.polwithcheck, p.polrelid) AS withcheck
FROM pg_policy p
"""

_ROLES_SQL = "SELECT rolname FROM pg_roles WHERE rolname = ANY($1::text[])"

_TABLE_PRIV_SQL = "SELECT has_table_privilege($1::text, $2::text, $3::text) AS p"
_COLUMN_PRIV_SQL = "SELECT has_any_column_privilege($1::text, $2::text, $3::text) AS p"
_COLUMN_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "REFERENCES"})


async def inspect_schema(
    conn: Fetcher, allowlist: Sequence[AllowlistEntry] = ()
) -> list[Violation]:
    """Return every violation in schema ``public`` (empty means the schema is covered)."""
    tables = await conn.fetch(_TABLES_SQL)
    columns: dict[int, dict[str, Mapping[str, Any]]] = {}
    for col in await conn.fetch(_COLUMNS_SQL):
        columns.setdefault(int(col["oid"]), {})[str(col["name"])] = col
    policies: dict[int, list[Mapping[str, Any]]] = {}
    for pol in await conn.fetch(_POLICIES_SQL):
        policies.setdefault(int(pol["oid"]), []).append(pol)
    present_roles = {str(r["rolname"]) for r in await conn.fetch(_ROLES_SQL, list(RUNTIME_ROLES))}
    found: list[Violation] = []
    for t in tables:
        name = str(t["name"])
        entry = next((e for e in allowlist if e.matches(name)), None)
        skipped = entry.checks_skipped if entry else frozenset[str]()
        column = entry.tenant_column if entry else "tenant_id"
        oid = int(t["oid"])
        if "tenant_id" not in skipped:
            col = columns.get(oid, {}).get(column)
            if col is None or col["type"] != "uuid" or not col["notnull"]:
                found.append(Violation(name, "tenant_id", f"missing {column} uuid NOT NULL"))
        if "rls" not in skipped and not t["rls"]:
            found.append(Violation(name, "rls", "missing ENABLE ROW LEVEL SECURITY"))
        if "force_rls" not in skipped and not t["force_rls"]:
            found.append(Violation(name, "force_rls", "missing FORCE ROW LEVEL SECURITY"))
        if "policy" not in skipped:
            found.extend(_policy_violations(name, column, policies.get(oid, [])))
        if entry is not None and entry.forbid_runtime_privileges:
            found.extend(await _privilege_violations(conn, name, present_roles))
    return found


def _policy_violations(
    table: str, column: str, policies: Sequence[Mapping[str, Any]]
) -> list[Violation]:
    all_cmd = [p for p in policies if p["cmd"] == "*" and p["permissive"]]
    if not all_cmd:
        return [Violation(table, "policy", "missing tenant policy FOR ALL commands")]
    complete = [p for p in all_cmd if p["qual"] and p["withcheck"]]
    if not complete:
        if any(not p["withcheck"] for p in all_cmd):
            return [Violation(table, "policy", "missing WITH CHECK on the tenant policy")]
        return [Violation(table, "policy", "missing USING on the tenant policy")]
    column_re = re.compile(rf"\b{re.escape(column)}\b")
    for p in complete:
        exprs = (str(p["qual"]), str(p["withcheck"]))
        if all(_SETTING_RE.search(x) and column_re.search(x) for x in exprs):
            return []
    return [
        Violation(
            table,
            "policy",
            f"tenant policy does not compare {column} with current_setting('app.tenant_id') "
            "in both USING and WITH CHECK",
        )
    ]


async def _privilege_violations(
    conn: Fetcher, table: str, present_roles: set[str]
) -> list[Violation]:
    found: list[Violation] = []
    for role in RUNTIME_ROLES:
        if role not in present_roles:
            continue
        for priv in _TABLE_PRIVILEGES:
            args = (role, f"public.{table}", priv)
            has = bool((await conn.fetch(_TABLE_PRIV_SQL, *args))[0]["p"])
            # Column-level grants count too; only these four exist at column level.
            if not has and priv in _COLUMN_PRIVILEGES:
                has = bool((await conn.fetch(_COLUMN_PRIV_SQL, *args))[0]["p"])
            if has:
                found.append(Violation(table, "privileges", f"{role} has {priv} (must have none)"))
    return found
