"""Small shared checks for the repository helpers (DATABASE-04). Internal to ``aip.platform.db``."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Table

_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def table_name(table: Table | str) -> str:
    """A plain snake_case table name, safe to put in ``text()`` SQL."""
    name = table if isinstance(table, str) else table.name
    if not _IDENT_RE.match(name):
        raise ValueError(f"not a plain table name: {name!r}")
    return name


def as_dict(row: Any) -> dict[str, Any]:
    """A SQLAlchemy ``Row`` (or any mapping) as a plain dict keyed by column name."""
    if isinstance(row, Mapping):
        return dict(row)  # pyright: ignore[reportUnknownArgumentType]
    return dict(row._mapping)
