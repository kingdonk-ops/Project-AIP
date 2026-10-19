"""The DATABASE-07 isolation generator: one cross-tenant check per tenant-scoped table.

- :func:`cases` lists the tenant tables from the declared ``MetaData`` (a ``tenant_id`` column, or
  ``tenants`` itself, whose ``id`` is the tenant id), so pytest can parametrize at collection time.
- :func:`check_table` seeds one row for tenant A and one for tenant B as the superuser (FKs and
  triggers off through ``session_replication_role = replica``; RLS does not bind a superuser), then
  connects as ``aip_app`` (refused if it is a superuser, BYPASSRLS or the table's owner) and,
  with tenant A set in each rolled-back transaction exactly as ``with_tenant`` does, checks that:
  A's row is visible; B's row is invisible by key, in a full scan and in every child partition;
  UPDATE or DELETE of B's row by key changes nothing; an unqualified UPDATE or DELETE touches
  at most A's one row; and A's row can be neither moved nor copied into tenant B (WITH CHECK).
  A missing grant counts as isolation for that command, but a table aip_app cannot SELECT
  fails unless ``overrides.toml`` says why (``no_app_select``) and aip_app may not write it.
  The artefact records each privilege and each check's outcome.
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
    "seed_pair",
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
    no_app_select: bool = False
    move_refused: str = ""
    update_set: str = ""
    principal_kind: str = ""


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


_OVERRIDE_KEYS = frozenset(
    {"reason", "values", "skip", "no_app_select", "move_refused", "update_set", "principal_kind"}
)
_PRINCIPAL_KINDS = frozenset({"user", "api_client", "system"})


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
        principal_kind = str(entry.get("principal_kind", ""))
        if principal_kind and principal_kind not in _PRINCIPAL_KINDS:
            raise OverrideError(
                f"{table}: principal_kind must be one of {sorted(_PRINCIPAL_KINDS)}"
            )
        out[table] = Override(
            table,
            reason,
            dict(values),
            bool(entry.get("skip", False)),
            bool(entry.get("no_app_select", False)),
            str(entry.get("move_refused", "")),
            str(entry.get("update_set", "")),
            principal_kind,
        )
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

_POSTURE = """
    SELECT r.rolsuper OR r.rolbypassrls OR pg_get_userbyid(c.relowner) = current_user
    FROM pg_roles r, pg_class c WHERE r.rolname = current_user AND c.oid = $1::regclass
"""
_PRIVILEGES = """
    SELECT has_table_privilege(current_user, $1, 'SELECT'),
           has_table_privilege(current_user, $1, 'INSERT'),
           has_table_privilege(current_user, $1, 'UPDATE'),
           has_table_privilege(current_user, $1, 'DELETE')
"""
_CHILDREN = "SELECT inhrelid::regclass::text FROM pg_inherits WHERE inhparent = $1::regclass"
_RLS_VIOLATION = "row-level security"

Outcome = tuple[str, Any]
"""``("ok", value)``, ``("denied", None)`` (no grant), ``("rls", None)`` (a policy's WITH CHECK
refused the row) or ``("error", "<SQLSTATE>: <message>")``."""


async def _probe(
    app: Any, tenant: UUID, statements: list[str], principal_kind: str = ""
) -> Outcome:
    """Run ``statements`` as aip_app with ``tenant`` set (as ``with_tenant`` does), always rolled
    back; the outcome is the last statement's count (or value, for a SELECT).

    ``principal_kind`` (ACCESS-03) also sets ``app.principal_kind`` for a table behind the
    project-scope RLS: ``system`` makes it tenant-wide, so the own-row probe sees its tenant's row
    while the permissive tenant-isolation policy still hides the other tenant's."""
    tx = app.transaction()
    await tx.start()
    try:
        await app.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant))
        if principal_kind:
            await app.execute("SELECT set_config('app.principal_kind', $1, true)", principal_kind)
        result: Any = None
        for sql in statements:
            if sql.lstrip().upper().startswith("SELECT"):
                result = await app.fetchval(sql)
            else:
                status: str = await app.execute(sql)
                last = status.rsplit(" ", 1)[-1]
                result = int(last) if last.isdigit() else status
        return "ok", result
    except asyncpg.InsufficientPrivilegeError as exc:
        return ("rls", None) if _RLS_VIOLATION in str(exc) else ("denied", None)
    except asyncpg.PostgresError as exc:
        return "error", f"{getattr(exc, 'sqlstate', '?')}: {exc}"
    finally:
        await tx.rollback()


def _render(outcome: Outcome) -> str:
    kind, value = outcome
    return str(value) if kind == "ok" else (kind if kind != "error" else f"error {value}")


async def _uuid_keys(app: Any, case: Case) -> list[str]:
    rows = await app.fetch(
        "SELECT attname FROM pg_attribute WHERE attrelid = $1::regclass"
        " AND atttypid = 'uuid'::regtype AND attname = ANY($2::text[])",
        case.table,
        list(case.primary_key),
    )
    return [r[0] for r in rows if r[0] != case.tenant_column]


async def _checks(
    app: Any,
    case: Case,
    override: Override | None,
    key_a: dict[str, str],
    key_b: dict[str, str],
    tenant_a: UUID,
    tenant_b: UUID,
) -> dict[str, Outcome]:
    table, tenant_col = _ident(case.table), _ident(case.tenant_column)
    first = _ident(case.primary_key[0])
    # Extra SET assignments a table trigger needs on every UPDATE (e.g. a version that must rise).
    extra = f", {override.update_set}" if override and override.update_set else ""
    fresh_ids = ", ".join(f"{_ident(c)} = gen_random_uuid()" for c in await _uuid_keys(app, case))
    move_b = f"{tenant_col} = '{tenant_b}'::uuid" + (f", {fresh_ids}" if fresh_ids else "")
    # ACCESS-03: a project-scoped table also needs a principal (overrides.toml principal_kind).
    pk = override.principal_kind if override else ""

    async def probe(statements: list[str]) -> Outcome:
        return await _probe(app, tenant_a, statements, principal_kind=pk)

    out: dict[str, Outcome] = {
        "own_read": await probe([f"SELECT count(*) FROM {table} WHERE {_where(key_a)}"]),
        "cross_read": await probe([f"SELECT count(*) FROM {table} WHERE {_where(key_b)}"]),
        "cross_scan": await probe(
            [f"SELECT count(*) FROM {table} WHERE {tenant_col} <> '{tenant_a}'::uuid"]
        ),
        "cross_update": await probe(
            [f"UPDATE {table} SET {first} = {first}{extra} WHERE {_where(key_b)}"]
        ),
        "cross_delete": await probe([f"DELETE FROM {table} WHERE {_where(key_b)}"]),
        # No WHERE: a correct policy limits these to tenant A's one row (rolled back).
        "update_all": await probe([f"UPDATE {table} SET {first} = {first}{extra}"]),
        "delete_all": await probe([f"DELETE FROM {table}"]),
        # WITH CHECK: A's row may not be moved, or copied, into tenant B.
        "move_to_b": await probe([f"UPDATE {table} SET {move_b}{extra} WHERE {_where(key_a)}"]),
        "insert_for_b": await probe(
            [
                f"CREATE TEMP TABLE iso_copy ON COMMIT DROP AS SELECT * FROM {table}"
                f" WHERE {_where(key_a)}",
                f"UPDATE iso_copy SET {move_b}",
                f"INSERT INTO {table} SELECT * FROM iso_copy",
            ],
        ),
    }
    for child in [r[0] for r in await app.fetch(_CHILDREN, case.table)]:
        part = _ident(child.strip('"'))
        out[f"partition {child} cross_scan"] = await probe(
            [f"SELECT count(*) FROM {part} WHERE {tenant_col} <> '{tenant_a}'::uuid"]
        )
    return out


def _verdict(
    case: Case, override: Override | None, privileges: dict[str, bool], checks: dict[str, Outcome]
) -> tuple[str, str]:
    """``(status, message)`` from the outcomes (see the module docstring for each rule)."""

    def count(name: str) -> int | None:
        kind, value = checks[name]
        return value if kind == "ok" and isinstance(value, int) else None

    if not privileges["select"]:
        if override is None or not override.no_app_select:
            return "failed", (
                "aip_app has no SELECT, so isolation cannot be observed: add `no_app_select = true`"
                " with a reason in tests/isolation/overrides.toml"
            )
        writes = [p for p in ("insert", "update", "delete") if privileges[p]]
        if writes:
            return "failed", f"aip_app may {'/'.join(writes)} but not SELECT this table"
        return "passed", f"aip_app holds no privilege on it ({override.reason})"

    leaks = {
        n: count(n)
        for n in checks
        if n in {"cross_read", "cross_scan"} or n.startswith("partition")
    }
    if any(leaks.values()):
        return "failed", f"{LEAK} ({', '.join(f'{n}: {v}' for n, v in leaks.items() if v)})"
    for name in ("cross_update", "cross_delete"):
        if count(name):
            return "failed", f"cross-tenant write changed rows ({name})"
    for name in ("update_all", "delete_all"):
        if (count(name) or 0) > 1:
            return (
                "failed",
                f"an unqualified {name.split('_')[0].upper()} reached other tenants' rows",
            )
    for name in ("move_to_b", "insert_for_b"):
        kind, value = checks[name]
        refusal = override.move_refused if override and name == "move_to_b" else ""
        if kind == "error" and refusal and refusal in str(value):
            continue  # a table trigger refuses every move (named in overrides.toml)
        if kind == "ok" and value:
            return "failed", f"a row could be written into tenant B ({name})"
        if kind == "error":
            return "failed", f"{name} could not run ({value}); fix the probe or add an override"
    for name, outcome in checks.items():
        if outcome[0] == "error" and name not in ("move_to_b", "insert_for_b"):
            return "failed", f"{name} failed to run ({outcome[1]})"
    if count("own_read") != 1:
        return "failed", "tenant A's own row is not visible to tenant A"
    return "passed", ""


async def seed_pair(
    superuser_url: str, case: Case, override: Override | None, tenant_a: UUID, tenant_b: UUID
) -> tuple[dict[str, str], dict[str, str]]:
    """Seed one row for each tenant as the superuser; their primary keys as SQL literals.

    TESTING-04 reuses this to get tenant B's ids for the route IDOR checks.
    """
    su: Any = await asyncpg.connect(superuser_url)  # pyright: ignore[reportUnknownMemberType]
    try:
        async with su.transaction():
            await su.execute("SET LOCAL session_replication_role = replica")
            key_a = await _seed(su, case, override, tenant_a, "a")
            key_b = await _seed(su, case, override, tenant_b, "b")
    finally:
        await su.close()
    return key_a, key_b


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

    try:
        key_a, key_b = await seed_pair(superuser_url, case, override, tenant_a, tenant_b)
    except (LookupError, asyncpg.PostgresError) as exc:
        return Result(
            case.table,
            "failed",
            f"cannot seed ({type(exc).__name__}: {exc}); add values for it in"
            " tests/isolation/overrides.toml",
        )

    app: Any = await asyncpg.connect(app_url)  # pyright: ignore[reportUnknownMemberType]
    try:
        if await app.fetchval(_POSTURE, case.table):
            return Result(
                case.table, "failed", "aip_app is a superuser, BYPASSRLS or owns this table"
            )
        row = await app.fetchrow(_PRIVILEGES, case.table)
        privileges: dict[str, bool] = {
            name: bool(value)
            for name, value in zip(("select", "insert", "update", "delete"), row, strict=True)
        }
        outcomes = await _checks(app, case, override, key_a, key_b, tenant_a, tenant_b)
    finally:
        await app.close()

    checks = {f"privilege {k}": str(v).lower() for k, v in privileges.items()}
    checks.update({name: _render(outcome) for name, outcome in outcomes.items()})
    status, message = _verdict(case, override, privileges, outcomes)
    return Result(case.table, status, message, checks)  # type: ignore[arg-type]


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
