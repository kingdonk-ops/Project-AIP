"""Render the SQL templates in ``db/templates/`` for Alembic revisions (DATABASE-02, ADR 0002).

A revision creates a tenant table with::

    from alembic import op

    from aip.platform.db.templates import render_template

    def upgrade() -> None:
        op.execute(render_template("tenant_table", table="widgets", columns="name text NOT NULL"))

Placeholders are ``{{name}}``. Every placeholder must be given and every argument must be used,
so a typo fails at migration time instead of producing odd SQL. ``table`` must be a plain
snake_case identifier that is not a reserved word and does not start with ``pg_``; ``columns``
must be a non-empty column list with no statement separator, comment, quote or ``$`` (so it
cannot open a string, a quoted name or a dollar-quoted body that swallows the rest).
``aip-db lint`` renders the same call and lints the resulting SQL.

This module only needs the standard library: the migrator image ships ``aip.platform.db`` alone.
"""

from __future__ import annotations

import re
from pathlib import Path

from aip.platform.db.errors import TemplateError
from aip.platform.db.migrator import repo_root

__all__ = ["render_template", "templates_dir"]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,47}$")  # room for the ix_/pk_ prefixes in 63
_IDENTIFIER_VARS = frozenset({"table"})
_FORBIDDEN_IN_LISTS = (";", "--", "/*", "'", '"', "$")

# PostgreSQL 16 keywords that cannot be a table name unquoted: "reserved" and "reserved (can be
# function or type)" in the SQL Key Words appendix.
RESERVED_WORDS = frozenset(
    [
        "all",
        "analyse",
        "analyze",
        "and",
        "any",
        "array",
        "as",
        "asc",
        "asymmetric",
        "authorization",
        "binary",
        "both",
        "case",
        "cast",
        "check",
        "collate",
        "collation",
        "column",
        "concurrently",
        "constraint",
        "create",
        "cross",
        "current_catalog",
        "current_date",
        "current_role",
        "current_schema",
        "current_time",
        "current_timestamp",
        "current_user",
        "default",
        "deferrable",
        "desc",
        "distinct",
        "do",
        "else",
        "end",
        "except",
        "false",
        "fetch",
        "for",
        "foreign",
        "freeze",
        "from",
        "full",
        "grant",
        "group",
        "having",
        "ilike",
        "in",
        "initially",
        "inner",
        "intersect",
        "into",
        "is",
        "isnull",
        "join",
        "lateral",
        "leading",
        "left",
        "like",
        "limit",
        "localtime",
        "localtimestamp",
        "natural",
        "not",
        "notnull",
        "null",
        "offset",
        "on",
        "only",
        "or",
        "order",
        "outer",
        "overlaps",
        "placing",
        "primary",
        "references",
        "returning",
        "right",
        "select",
        "session_user",
        "similar",
        "some",
        "symmetric",
        "system_user",
        "table",
        "tablesample",
        "then",
        "to",
        "trailing",
        "true",
        "union",
        "unique",
        "user",
        "using",
        "variadic",
        "verbose",
        "when",
        "where",
        "window",
        "with",
    ]
)


def templates_dir() -> Path:
    return repo_root() / "db" / "templates"


def _check_value(key: str, value: object) -> str:
    if not isinstance(value, str):
        raise TemplateError(f"template variable {key!r} must be a string")
    if key in _IDENTIFIER_VARS:
        if not _IDENTIFIER_RE.match(value):
            raise TemplateError(
                f"template variable {key!r} must be a snake_case identifier, got {value!r}"
            )
        if value in RESERVED_WORDS:
            raise TemplateError(f"template variable {key!r} is a reserved word: {value!r}")
        if value.startswith("pg_"):
            raise TemplateError(f"template variable {key!r} must not start with pg_: {value!r}")
        return value
    if not value.strip():
        raise TemplateError(f"template variable {key!r} must not be empty")
    if any(token in value for token in _FORBIDDEN_IN_LISTS):
        raise TemplateError(
            f"template variable {key!r} must not contain ';', comments, quotes or '$'"
        )
    return value


def render_template(name: str, **variables: object) -> str:
    """Return ``db/templates/<name>.sql.tpl`` with its ``{{placeholders}}`` filled in."""
    if not _NAME_RE.match(name):
        raise TemplateError(f"invalid template name {name!r}")
    path = templates_dir() / f"{name}.sql.tpl"
    if not path.is_file():
        raise TemplateError(f"unknown template {name!r} (no {path})")
    text = path.read_text(encoding="utf-8")

    wanted = set(_PLACEHOLDER_RE.findall(text))
    missing = sorted(wanted - variables.keys())
    unused = sorted(variables.keys() - wanted)
    if missing:
        raise TemplateError(f"template {name!r} needs {', '.join(missing)}")
    if unused:
        raise TemplateError(f"template {name!r} has no placeholder for {', '.join(unused)}")
    values = {key: _check_value(key, value) for key, value in variables.items()}
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], text)
