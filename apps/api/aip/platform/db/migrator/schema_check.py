"""``aip-db check-schema``: compare the migrated database with the declared SQLAlchemy tables.

Compares tables, columns, types and nullability, ignoring schemas ``aip_meta`` and
``procrastinate`` (and the system schemas) and the ``procrastinate_*`` queue tables that the
OPS-02 migration creates in ``public`` (Procrastinate's own schema, not declared here). Prints one
line per difference.
"""

from __future__ import annotations

import asyncio
import re

from sqlalchemy import MetaData, NullPool, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.asyncio import create_async_engine

from aip.platform.db.migrator.run import to_async_url

IGNORED_SCHEMAS = ("aip_meta", "procrastinate", "information_schema")

_COLUMNS_SQL = """
SELECT n.nspname, c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attribute a
  ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE c.relkind IN ('r', 'p')
  AND NOT c.relispartition
  AND n.nspname NOT LIKE 'pg\\_%'
  AND c.relname NOT LIKE 'procrastinate\\_%'
  AND n.nspname NOT IN ('aip_meta', 'procrastinate', 'information_schema')
  AND NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_depend d
    WHERE d.classid = 'pg_catalog.pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'
  )
ORDER BY 1, 2, a.attnum
"""

_ALIASES = {
    "varchar": "character varying",
    "char": "character",
    "float": "double precision",
    "int": "integer",
    "int4": "integer",
    "int8": "bigint",
    "bool": "boolean",
    "decimal": "numeric",
}
_ZONELESS = {"timestamp": "timestamp without time zone", "time": "time without time zone"}
_TYPE_RE = re.compile(r"^(?P<base>[a-z_][a-z0-9_ ]*?)\s*(?P<args>\([^)]*\))?(?P<rest>.*)$")

Columns = dict[str, tuple[str, bool]]  # column -> (normalised type, nullable)


def normalise_type(spec: str) -> str:
    s = " ".join(spec.lower().replace('"', "").split())
    s = re.sub(r"\s*,\s*", ",", s)
    s = re.sub(r"\s*\(\s*", "(", s)
    s = re.sub(r"\s*\)", ")", s)
    m = _TYPE_RE.match(s)
    if m is None:
        return s
    base, args, rest = m["base"], m["args"] or "", m["rest"].strip()
    base = _ALIASES.get(base, base)
    if not rest and base in _ZONELESS:
        base = _ZONELESS[base]
        if args:  # timestamp(3) -> timestamp(3) without time zone
            return f"{base.split(' ', 1)[0]}{args} {base.split(' ', 1)[1]}"
    return f"{base}{args}{(' ' + rest) if rest and not rest.startswith('[') else rest}"


def _qualified(schema: str | None, name: str) -> str:
    return name if schema in (None, "public") else f"{schema}.{name}"


def declared_tables(metadata: MetaData) -> dict[str, Columns]:
    dialect = postgresql.dialect()
    tables: dict[str, Columns] = {}
    for table in metadata.tables.values():
        cols: Columns = {}
        for col in table.columns:
            try:
                spec = str(col.type.compile(dialect=dialect))
            except CompileError:
                spec = type(col.type).__name__
            cols[col.name] = (normalise_type(spec), bool(col.nullable))
        tables[_qualified(table.schema, table.name)] = cols
    return tables


async def migrated_tables(url: str) -> dict[str, Columns]:
    engine = create_async_engine(to_async_url(url), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(text(_COLUMNS_SQL))).all()
    finally:
        await engine.dispose()
    tables: dict[str, Columns] = {}
    for schema, table, column, type_spec, not_null in rows:
        cols = tables.setdefault(_qualified(str(schema), str(table)), {})
        if column is not None:
            cols[str(column)] = (normalise_type(str(type_spec)), not bool(not_null))
    return tables


def compare(declared: dict[str, Columns], migrated: dict[str, Columns]) -> list[str]:
    diffs: list[str] = []
    for name in sorted(declared.keys() - migrated.keys()):
        diffs.append(f"table {name} declared but not migrated")
    for name in sorted(migrated.keys() - declared.keys()):
        diffs.append(f"table {name} migrated but not declared")
    for name in sorted(declared.keys() & migrated.keys()):
        want, have = declared[name], migrated[name]
        for col in sorted(want.keys() - have.keys()):
            diffs.append(f"column {name}.{col} declared but not migrated")
        for col in sorted(have.keys() - want.keys()):
            diffs.append(f"column {name}.{col} migrated but not declared")
        for col in sorted(want.keys() & have.keys()):
            (want_type, want_null), (have_type, have_null) = want[col], have[col]
            if want_type != have_type:
                diffs.append(
                    f"column {name}.{col} type: declared {want_type}, migrated {have_type}"
                )
            if want_null != have_null:
                diffs.append(
                    f"column {name}.{col} nullability: declared {_null(want_null)}, "
                    f"migrated {_null(have_null)}"
                )
    return diffs


def _null(nullable: bool) -> str:
    return "NULL" if nullable else "NOT NULL"


async def diff_schema(url: str, metadata: MetaData) -> list[str]:
    return compare(declared_tables(metadata), await migrated_tables(url))


def check_schema(url: str, metadata: MetaData) -> int:
    """Print one line per difference; 0 when the migrated schema matches the declared tables."""
    diffs = asyncio.run(diff_schema(url, metadata))
    for line in diffs:
        print(line)
    if not diffs:
        print("schema matches declared tables")
    return 1 if diffs else 0
