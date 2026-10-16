"""The DATABASE-07 isolation generator: one cross-tenant check per tenant-scoped table.

- :func:`cases` lists the tenant tables from the declared ``MetaData`` (a ``tenant_id`` column, or
  ``tenants`` itself, whose ``id`` is the tenant id), so pytest can parametrize at collection time.
- :func:`check_table` seeds one row for tenant A and one for tenant B as the superuser (FKs and
  triggers off through ``session_replication_role = replica``; RLS does not bind a superuser), then
  connects as ``aip_app``, sets tenant A in each transaction exactly as ``with_tenant`` does, and
  checks that A's row is visible, B's row is invisible by key and in a full scan, and that an
  UPDATE or DELETE of B's row by key changes nothing. A missing grant counts as isolation.
- Seed values come from the column types; a single-column ``CHECK (col = ANY (ARRAY[...]))`` or
  ``CHECK (col = '...')`` supplies its first literal. Anything else a table needs goes in
  ``overrides.toml`` with a ``reason``; a table can be skipped only there, also with a reason.
- :func:`write_results` writes the per-table outcome as JSON, the CI evidence artefact.

Lives under ``tests/`` because it opens raw connections (only ``aip.platform.db`` may, in ``aip/``).
"""

from __future__ import annotations

import json
import re
import tomllib
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import MetaData

__all__ = [
    "OVERRIDES_PATH",
    "Case",
    "Override",
    "OverrideError",
    "Result",
    "cases",
    "catalogue_tables",
    "check_literals",
    "check_table",
    "literal_for",
    "load_overrides",
    "parse_overrides",
    "write_results",
]

OVERRIDES_PATH = Path(__file__).with_name("overrides.toml")
TENANT_REGISTRY = "tenants"
LEAK = "cross-tenant read returned rows"


@dataclass(frozen=True, slots=True)
class Case:
    table: str
    tenant_column: str
    primary_key: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Override:
    table: str
    reason: str
    values: Mapping[str, str] = field(default_factory=dict[str, str])
    skip: bool = False


class OverrideError(ValueError):
    """An ``overrides.toml`` entry is malformed (no reason, unknown keys)."""


@dataclass(slots=True)
class Result:
    table: str
    status: Literal["passed", "failed", "exempt"]
    message: str = ""
    checks: dict[str, str] = field(default_factory=dict[str, str])


# --- cases and overrides ----------------------------------------------------------------------


def cases(meta: MetaData) -> list[Case]:
    """One case per declared tenant table, by name."""
    out: list[Case] = []
    for table in meta.tables.values():
        if table.schema not in (None, "public"):
            continue
        if table.name == TENANT_REGISTRY:
            tenant_column = "id"
        elif "tenant_id" in table.c:
            tenant_column = "tenant_id"
        else:
            continue
        key = tuple(c.name for c in table.primary_key.columns)
        out.append(Case(table.name, tenant_column, key))
    return sorted(out, key=lambda c: c.table)


_OVERRIDE_KEYS = frozenset({"reason", "values", "skip"})


def parse_overrides(raw: Mapping[str, Any]) -> dict[str, Override]:
    out: dict[str, Override] = {}
    for table, entry in dict(raw.get("tables", {})).items():
        unknown = set(entry) - _OVERRIDE_KEYS
        if unknown:
            raise OverrideError(f"{table}: unknown keys {sorted(unknown)}")
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise OverrideError(f"{table}: needs a reason")
        values = entry.get("values", {})
        if not isinstance(values, dict) or not all(isinstance(v, str) for v in values.values()):
            raise OverrideError(f"{table}: values must map columns to SQL literals")
        out[table] = Override(table, reason, dict(values), bool(entry.get("skip", False)))
    return out


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, Override]:
    return parse_overrides(tomllib.loads(path.read_text(encoding="utf-8")))


# --- seed values ------------------------------------------------------------------------------

_CHAR_N = re.compile(r"^character\((\d+)\)$")


def literal_for(type_name: str, column: str, tag: str) -> str | None:
    """A SQL literal of ``type_name`` for ``column`` in the row tagged ``tag`` (``None``: generate a
    uuid; ``"?"``: unknown, needs an override)."""
    t = type_name.lower()
    if t == "uuid":
        return None
    if t in {"text", "citext"} or t.startswith("character varying"):
        return f"'iso_{column}_{tag}'"  # identifier-shaped: passes the usual code CHECKs
    if match := _CHAR_N.match(t):
        return "'" + "A" * int(match.group(1)) + "'"
    if t in {"integer", "bigint", "smallint"} or t.startswith("numeric"):
        return "1"
    if t == "boolean":
        return "false"
    if t.startswith("timestamp"):
        return "now()"
    if t == "date":
        return "current_date"
    if t in {"jsonb", "json"}:
        return f"'{{}}'::{t}"
    if t == "inet":
        return "'192.0.2.1'::inet"
    if t == "bytea":
        return f"decode(repeat('{tag * 2}', 32), 'hex')"  # 32 bytes, distinct per row
    if t == "ltree":
        return "'iso'::ltree"
    if t.endswith("[]"):
        return f"'{{}}'::{t}"
    if t == "interval":
        return "'1 hour'::interval"
    return "?"


_IN_LIST = re.compile(r"^CHECK \(\((\w+) = ANY \(\(?ARRAY\['((?:[^']|'')*)'")
_EQUALS = re.compile(r"^CHECK \(\((\w+) = '((?:[^']|'')*)'::")


def check_literals(definitions: list[str]) -> dict[str, str]:
    """Seed values from single-column ``= ANY (ARRAY[...])`` / ``= '...'`` CHECKs."""
    out: dict[str, str] = {}
    for definition in definitions:
        match = _IN_LIST.match(definition) or _EQUALS.match(definition)
        if match:
            out.setdefault(match.group(1), f"'{match.group(2)}'")
    return out


# --- catalogue --------------------------------------------------------------------------------

_TENANT_TABLES = """
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
      AND (c.relname = 'tenants' OR EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped))
"""
_COLUMNS = """
    SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
           a.atthasdef, a.attidentity <> '', a.attgenerated <> ''
    FROM pg_attribute a
    WHERE a.attrelid = $1::regclass AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY a.attnum
"""
_CHECKS = (
    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
    " WHERE conrelid = $1::regclass AND contype = 'c'"
)


async def catalogue_tables(superuser_url: str) -> set[str]:
    conn: Any = await asyncpg.connect(superuser_url)  # pyright: ignore[reportUnknownMemberType]
    try:
        return {r[0] for r in await conn.fetch(_TENANT_TABLES)}
    finally:
        await conn.close()


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def _seed(
    conn: Any, case: Case, override: Override | None, tenant: UUID, tag: str
) -> dict[str, str]:
    """Insert one row for ``tenant``; return the primary key as ``{column: SQL literal}``."""
    columns = await conn.fetch(_COLUMNS, case.table)
    from_checks = check_literals([r[0] for r in await conn.fetch(_CHECKS, case.table)])
    values: dict[str, str] = {}
    for name, type_name, not_null, has_default, identity, generated in columns:
        if identity or generated:
            continue
        if name == case.tenant_column:
            values[name] = f"'{tenant}'::uuid"
        elif override is not None and name in override.values:
            values[name] = override.values[name].replace("{tag}", tag)
        elif name in case.primary_key or (not_null and not has_default):
            literal = from_checks.get(name) or literal_for(type_name, name, tag)
            if literal is None:
                literal = f"'{uuid.uuid4()}'::uuid"
            if literal == "?":
                raise LookupError(f"no seed value for {case.table}.{name} ({type_name})")
            values[name] = literal
    cols = ", ".join(_ident(c) for c in values)
    sql = f"INSERT INTO {_ident(case.table)} ({cols}) VALUES ({', '.join(values.values())})"
    key = ", ".join(_ident(c) for c in case.primary_key)
    row = await conn.fetchrow(f"{sql} RETURNING {key}")
    return {c: _literal_of(row[c]) for c in case.primary_key}


def _literal_of(value: Any) -> str:
    if isinstance(value, UUID):
        return f"'{value}'::uuid"
    if isinstance(value, int | float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _where(key: dict[str, str]) -> str:
    return " AND ".join(f"{_ident(c)} = {v}" for c, v in key.items())


# --- the check --------------------------------------------------------------------------------


async def _as_tenant(app: Any, tenant: UUID, sql: str) -> tuple[str, Any]:
    """Run ``sql`` as aip_app in a transaction with ``tenant`` set: ``("ok", value)`` or
    ``("denied", None)`` for a missing grant."""
    try:
        async with app.transaction():
            await app.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant))
            if sql.lstrip().upper().startswith("SELECT"):
                return "ok", await app.fetchval(sql)
            status: str = await app.execute(sql)
            return "ok", int(status.rsplit(" ", 1)[-1])
    except asyncpg.InsufficientPrivilegeError:
        return "denied", None


async def check_table(
    superuser_url: str,
    app_url: str,
    case: Case,
    override: Override | None,
    tenant_a: UUID,
    tenant_b: UUID,
) -> Result:
    """Seed A and B rows and check that tenant A can neither see nor change B's (see module doc)."""
    if override is not None and override.skip:
        return Result(case.table, "exempt", override.reason)
    if not case.primary_key:
        return Result(case.table, "failed", "no primary key: add an overrides.toml entry")

    su: Any = await asyncpg.connect(superuser_url)  # pyright: ignore[reportUnknownMemberType]
    try:
        async with su.transaction():
            await su.execute("SET LOCAL session_replication_role = replica")
            key_a = await _seed(su, case, override, tenant_a, "a")
            key_b = await _seed(su, case, override, tenant_b, "b")
    except (LookupError, asyncpg.PostgresError) as exc:
        return Result(
            case.table,
            "failed",
            f"cannot seed ({type(exc).__name__}: {exc}); add values for it in"
            " tests/isolation/overrides.toml",
        )
    finally:
        await su.close()

    table, tenant_col = _ident(case.table), _ident(case.tenant_column)
    first_key = _ident(case.primary_key[0])
    app: Any = await asyncpg.connect(app_url)  # pyright: ignore[reportUnknownMemberType]
    checks: dict[str, str] = {}
    try:
        own = await _as_tenant(app, tenant_a, f"SELECT count(*) FROM {table} WHERE {_where(key_a)}")
        cross = await _as_tenant(
            app, tenant_a, f"SELECT count(*) FROM {table} WHERE {_where(key_b)}"
        )
        scan = await _as_tenant(
            app, tenant_a, f"SELECT count(*) FROM {table} WHERE {tenant_col} <> '{tenant_a}'::uuid"
        )
        update = await _as_tenant(
            app, tenant_a, f"UPDATE {table} SET {first_key} = {first_key} WHERE {_where(key_b)}"
        )
        delete = await _as_tenant(app, tenant_a, f"DELETE FROM {table} WHERE {_where(key_b)}")
    finally:
        await app.close()

    for name, (outcome, value) in {
        "own_read": own,
        "cross_read": cross,
        "cross_scan": scan,
        "cross_update": update,
        "cross_delete": delete,
    }.items():
        checks[name] = "denied" if outcome == "denied" else str(value)

    if cross[1] or scan[1]:
        return Result(case.table, "failed", f"{LEAK} (by key: {cross[1]}, scan: {scan[1]})", checks)
    if update[1] or delete[1]:
        return Result(case.table, "failed", "cross-tenant write changed rows", checks)
    if own[0] == "ok" and own[1] != 1:
        return Result(case.table, "failed", "tenant A's own row is not visible to tenant A", checks)
    return Result(case.table, "passed", "", checks)


def write_results(path: Path, results: list[Result]) -> None:
    """The CI evidence artefact: every table with its status and each check's outcome."""
    body = {
        "summary": {
            status: sum(1 for r in results if r.status == status)
            for status in ("passed", "failed", "exempt")
        },
        "tables": [asdict(r) for r in sorted(results, key=lambda r: r.table)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
