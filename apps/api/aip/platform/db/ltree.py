"""ltree path operations (DATABASE-04, ADR 0002: ``text()`` for ltree).

The table has a ``path ltree`` column. Paths are validated here (dot-separated labels of letters,
digits and underscore) and passed as bind parameters; table names are validated identifiers.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.db._sql import table_name
from aip.platform.db.errors import CycleError

__all__ = ["ancestors", "descendants", "move_subtree"]

_PATH_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")
_LTREE = "CAST(:{} AS text)::ltree"


def _path(value: str) -> str:
    if not _PATH_RE.match(value):
        raise ValueError(f"not an ltree path: {value!r}")
    return value


async def descendants(
    conn: AsyncConnection, table: Table | str, path: str, *, include_self: bool = False
) -> list[dict[str, Any]]:
    """Live rows strictly below ``path`` (and ``path`` itself with ``include_self``), by path."""
    name, p = table_name(table), _path(path)
    not_self = "" if include_self else f" AND path <> {_LTREE.format('p')}"
    sql = text(
        f"SELECT * FROM {name} WHERE path <@ {_LTREE.format('p')}{not_self} "
        "AND deleted_at IS NULL ORDER BY path"
    )
    return [dict(r) for r in (await conn.execute(sql, {"p": p})).mappings()]


async def ancestors(
    conn: AsyncConnection, table: Table | str, path: str, *, include_self: bool = False
) -> list[dict[str, Any]]:
    """Live rows strictly above ``path``, root first (``path`` too with ``include_self``)."""
    name, p = table_name(table), _path(path)
    not_self = "" if include_self else f" AND path <> {_LTREE.format('p')}"
    sql = text(
        f"SELECT * FROM {name} WHERE path @> {_LTREE.format('p')}{not_self} "
        "AND deleted_at IS NULL ORDER BY nlevel(path)"
    )
    return [dict(r) for r in (await conn.execute(sql, {"p": p})).mappings()]


async def move_subtree(
    conn: AsyncConnection, table: Table | str, from_path: str, to_parent_path: str | None
) -> int:
    """Re-parent the node at ``from_path`` and everything below it; return the rows moved.

    ``to_parent_path=None`` moves the node to the root. Raises ``CycleError`` before any SQL runs
    when the new parent is the node or one of its descendants. All rows move in one ``UPDATE``;
    soft-deleted descendants move with their subtree so a restore finds them in place.
    """
    name, old = table_name(table), _path(from_path)
    new_parent = None if to_parent_path is None else _path(to_parent_path)
    if new_parent is not None and (new_parent == old or new_parent.startswith(old + ".")):
        raise CycleError(f"cannot move {old!r} under {new_parent!r}")
    tail = f"subpath(path, nlevel({_LTREE.format('old')}) - 1)"
    new_path = tail if new_parent is None else f"{_LTREE.format('parent')} || {tail}"
    sql = text(
        f"UPDATE {name} SET path = {new_path}, updated_at = now() "
        f"WHERE path <@ {_LTREE.format('old')}"
    )
    params: dict[str, Any] = {"old": old}
    if new_parent is not None:
        params["parent"] = new_parent
    result = await conn.execute(sql, params)
    return result.rowcount
