"""Render the SQL templates in ``db/templates/`` for Alembic revisions (DATABASE-02, ADR 0002).

A revision creates a tenant table with::

    from alembic import op

    from aip.platform.db.templates import render_template

    def upgrade() -> None:
        op.execute(render_template("tenant_table", table="widgets", columns="name text NOT NULL"))

Placeholders are ``{{name}}``. Every placeholder must be given and every argument must be used,
so a typo fails at migration time instead of producing odd SQL. ``table`` must be a plain
snake_case identifier; ``columns`` must be a non-empty column list with no statement separator
or comment. ``aip-db lint`` renders the same call and lints the resulting SQL.

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
        return value
    if not value.strip():
        raise TemplateError(f"template variable {key!r} must not be empty")
    if ";" in value or "--" in value or "/*" in value:
        raise TemplateError(f"template variable {key!r} must not contain ';' or comments")
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
