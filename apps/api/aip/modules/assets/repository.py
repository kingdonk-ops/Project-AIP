"""Data access for the asset tree (ASSETS-01).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant; reads skip soft-deleted rows. ltree
path work (descendants, ancestors, subtree move) goes through ``aip.platform.db.ltree``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func, insert, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.assets.tables import assets
from aip.platform.db import ltree
from aip.platform.db.soft_delete import soft_delete

__all__ = [
    "SORTS",
    "Keyset",
    "ancestors",
    "child_count",
    "count_assets",
    "find_live_by_tag_number",
    "get_asset",
    "insert_asset",
    "list_assets",
    "live_child_ids",
    "lock_node",
    "lock_tree",
    "max_sibling_sort_order",
    "move_node",
    "soft_delete_asset",
    "subtree_ids",
    "subtree_max_level",
]

# Each sort maps to the SQL expressions that order it, before the ``id`` tiebreak. The keys are the
# allowed ``sort`` tokens, so nothing user-supplied reaches the SQL text.
SORTS: Final[dict[str, tuple[str, ...]]] = {
    "position": ("sort_order", "name"),
    "name": ("name",),
    "tagNumber": ("coalesce(tag_number, '')",),
    "updatedAt": ("updated_at",),
}

_LOCK = text(
    "SELECT pg_advisory_xact_lock(hashtextextended(current_setting('app.tenant_id') || :lock, 0))"
).bindparams(lock=":assets.tree")

_CHILD_COUNT_EXPR = (
    "(SELECT count(*) FROM assets c WHERE c.parent_id = a.id AND c.deleted_at IS NULL)"
)

# The live ancestors' names, root first (a node's own name is not part of its path).
_ANCESTOR_NAMES_EXPR = (
    "(SELECT coalesce(array_agg(p.name ORDER BY nlevel(p.path)), '{}') FROM assets p"
    " WHERE p.path @> a.path AND p.path <> a.path AND p.deleted_at IS NULL)"
)


@dataclass(frozen=True, slots=True)
class Keyset:
    """A keyset page request: the sort token, direction, limit and the row to start after."""

    sort: str
    descending: bool
    limit: int
    after_values: tuple[Any, ...] | None = None
    after_id: UUID | None = None


async def lock_tree(conn: AsyncConnection) -> None:
    """Serialise tree writes in this tenant: create-with-parent, move and delete take this lock."""
    await conn.execute(_LOCK)


async def insert_asset(conn: AsyncConnection, values: Mapping[str, Any]) -> dict[str, Any]:
    stmt = insert(assets).values(**values).returning(*assets.c)
    row = (await conn.execute(stmt)).mappings().one()
    return dict(row)


async def get_asset(conn: AsyncConnection, asset_id: UUID) -> dict[str, Any] | None:
    stmt = select(assets).where(assets.c.id == asset_id, assets.c.deleted_at.is_(None))
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def lock_node(conn: AsyncConnection, asset_id: UUID) -> dict[str, Any] | None:
    """Read a live asset and hold its row lock until commit, so a concurrent rename cannot slip
    between the read and a move or delete (which take only the coarse tree lock otherwise)."""
    stmt = (
        select(assets)
        .where(assets.c.id == asset_id, assets.c.deleted_at.is_(None))
        .with_for_update()
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def ancestors(conn: AsyncConnection, path: str) -> list[dict[str, Any]]:
    """The live ancestors of ``path`` (strictly above it), root first."""
    return await ltree.ancestors(conn, assets, path)


async def subtree_max_level(conn: AsyncConnection, path: str) -> int:
    """The deepest ``nlevel`` in the subtree at ``path`` (including soft-deleted rows, which a move
    re-paths with their subtree), so a move can refuse a result deeper than 15."""
    sql = text("SELECT max(nlevel(path)) FROM assets WHERE path <@ CAST(:p AS ltree)").bindparams(
        p=path
    )
    return int((await conn.execute(sql)).scalar_one())


async def live_child_ids(conn: AsyncConnection, asset_id: UUID) -> list[UUID]:
    """Ids of the live direct children of ``asset_id``."""
    stmt = select(assets.c.id).where(assets.c.parent_id == asset_id, assets.c.deleted_at.is_(None))
    return list((await conn.execute(stmt)).scalars())


async def subtree_ids(conn: AsyncConnection, path: str) -> list[UUID]:
    """Ids of the node at ``path`` and its live descendants, root first."""
    rows = await ltree.descendants(conn, assets, path, include_self=True)
    return [row["id"] for row in rows]


async def move_node(
    conn: AsyncConnection,
    *,
    old_path: str,
    new_parent_path: str | None,
    new_parent_id: UUID | None,
    sort_order: int,
) -> int:
    """Re-parent the node at ``old_path`` and its whole subtree in one statement; return rows moved.

    The node row gets its new ``path``, ``parent_id`` and ``sort_order`` (and a bumped
    ``sync_version``) together, so ``ck_assets_root`` stays satisfied even when the move toggles a
    node between root and child. Every descendant (soft-deleted ones too) is re-pathed under the
    node's new location. ``new_parent_path`` is ``None`` when the node becomes a root.
    """
    prefix = "" if new_parent_path is None else "CAST(:parent_path AS ltree) || "
    params: dict[str, Any] = {"old": old_path, "parent_id": new_parent_id, "sort_order": sort_order}
    if new_parent_path is not None:
        params["parent_path"] = new_parent_path
    sql = text(
        f"""
        UPDATE assets
           SET path = {prefix}subpath(path, nlevel(CAST(:old AS ltree)) - 1),
               parent_id = CASE WHEN path = CAST(:old AS ltree) THEN :parent_id ELSE parent_id END,
               sort_order = CASE WHEN path = CAST(:old AS ltree) THEN :sort_order
                                 ELSE sort_order END,
               sync_version = CASE WHEN path = CAST(:old AS ltree) THEN sync_version + 1
                                   ELSE sync_version END,
               updated_at = now()
         WHERE path <@ CAST(:old AS ltree)
        """
    ).bindparams(**params)
    return (await conn.execute(sql)).rowcount


async def soft_delete_asset(conn: AsyncConnection, asset_id: UUID) -> dict[str, Any]:
    """Soft-delete one live asset (``deleted_at`` set, ``sync_version`` bumped); return the row."""
    return await soft_delete(conn, assets, asset_id)


async def child_count(conn: AsyncConnection, asset_id: UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(assets)
        .where(assets.c.parent_id == asset_id, assets.c.deleted_at.is_(None))
    )
    return int((await conn.execute(stmt)).scalar_one())


async def max_sibling_sort_order(conn: AsyncConnection, parent_id: UUID | None) -> int:
    """The greatest ``sort_order`` among live siblings under ``parent_id`` (roots: ``parent_id`` is
    null), or ``-1`` when there are none, so ``max + 1`` numbers the first child ``0``."""
    sibling = assets.c.parent_id.is_(None) if parent_id is None else assets.c.parent_id == parent_id
    stmt = (
        select(func.coalesce(func.max(assets.c.sort_order), -1))
        .select_from(assets)
        .where(assets.c.deleted_at.is_(None), sibling)
    )
    return int((await conn.execute(stmt)).scalar_one())


async def find_live_by_tag_number(conn: AsyncConnection, normalised: str) -> dict[str, Any] | None:
    """A live asset whose Tag Number equals ``normalised`` ignoring case, or ``None``."""
    stmt = select(assets).where(
        assets.c.deleted_at.is_(None),
        text("upper(tag_number) = upper(:tn)").bindparams(tn=normalised),
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _where(
    *,
    parent_id: UUID | None,
    roots_only: bool,
    under_path: str | None,
    q: str | None,
    tag_number: str | None,
    item_type_ids: list[UUID] | None,
) -> tuple[list[str], dict[str, Any]]:
    """The WHERE terms and bind parameters shared by the list, the count and the export."""
    params: dict[str, Any] = {}
    where = ["a.deleted_at IS NULL"]
    if roots_only:
        where.append("a.parent_id IS NULL")
    elif parent_id is not None:
        where.append("a.parent_id = :parent_id")
        params["parent_id"] = parent_id
    if under_path is not None:
        where.append("a.path <@ CAST(:under AS ltree) AND a.path <> CAST(:under AS ltree)")
        params["under"] = under_path
    if q:
        where.append(
            "(a.name ILIKE :q ESCAPE '\\' OR a.tag_number ILIKE :q ESCAPE '\\'"
            " OR a.internal_tag ILIKE :q ESCAPE '\\')"
        )
        params["q"] = f"%{_escape_like(q)}%"
    if tag_number is not None:
        where.append("upper(a.tag_number) = upper(:tagnum)")
        params["tagnum"] = tag_number
    if item_type_ids is not None:
        where.append("a.item_type_id = ANY(CAST(:item_type_ids AS uuid[]))")
        params["item_type_ids"] = item_type_ids
    return where, params


async def count_assets(
    conn: AsyncConnection,
    *,
    parent_id: UUID | None = None,
    roots_only: bool = False,
    under_path: str | None = None,
    q: str | None = None,
    tag_number: str | None = None,
    item_type_ids: list[UUID] | None = None,
) -> int:
    """How many live rows the list filters keep (the CSV export's size check, ASSETS-03)."""
    where, params = _where(
        parent_id=parent_id,
        roots_only=roots_only,
        under_path=under_path,
        q=q,
        tag_number=tag_number,
        item_type_ids=item_type_ids,
    )
    sql = text(f"SELECT count(*) FROM assets a WHERE {' AND '.join(where)}").bindparams(**params)
    return int((await conn.execute(sql)).scalar_one())


async def list_assets(
    conn: AsyncConnection,
    page: Keyset,
    *,
    parent_id: UUID | None = None,
    roots_only: bool = False,
    under_path: str | None = None,
    q: str | None = None,
    tag_number: str | None = None,
    item_type_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """Up to ``page.limit + 1`` live rows (the extra means "more"), each with ``child_count`` and
    ``ancestor_names``: the live ancestors' names, root first (the register's breadcrumbs and the
    CSV export's ``path`` column, ASSETS-08).

    ``item_type_ids`` keeps assets typed with any of those item types (ASSETS-02).
    """
    columns = SORTS[page.sort]
    where, params = _where(
        parent_id=parent_id,
        roots_only=roots_only,
        under_path=under_path,
        q=q,
        tag_number=tag_number,
        item_type_ids=item_type_ids,
    )

    # Qualify bare column names with the alias; expressions (coalesce(...)) stay as written.
    sort_exprs = [c if "(" in c else f"a.{c}" for c in columns]
    key_exprs = [*sort_exprs, "a.id"]
    direction = "DESC" if page.descending else "ASC"
    order_by = ", ".join(f"{expr} {direction}" for expr in key_exprs)

    if page.after_values is not None and page.after_id is not None:
        comparator = "<" if page.descending else ">"
        placeholders = []
        for i, value in enumerate(page.after_values):
            params[f"k{i}"] = value
            placeholders.append(f":k{i}")
        params["kid"] = page.after_id
        placeholders.append(":kid")
        where.append(f"({', '.join(key_exprs)}) {comparator} ({', '.join(placeholders)})")

    params["lim"] = page.limit + 1
    sql = text(
        f"SELECT a.*, {_CHILD_COUNT_EXPR} AS child_count,"
        f" {_ANCESTOR_NAMES_EXPR} AS ancestor_names FROM assets a "
        f"WHERE {' AND '.join(where)} ORDER BY {order_by} LIMIT :lim"
    ).bindparams(**params)
    # Type the JSONB column so the driver's text result is decoded as it is for select(assets).
    typed = sql.columns(attributes=JSONB)
    return [dict(r) for r in (await conn.execute(typed)).mappings()]
