"""``LinkService``: link records to each other and to an asset, and walk the links (ARCH-08).

Every method runs on the caller's ``with_tenant`` connection, so a link commits or rolls back with
the caller's own change, and RLS keeps each tenant to its own links. The row's ``tenant_id`` is the
connection's ``app.tenant_id`` and ``created_by`` is the request context's actor (``None`` outside
a request, e.g. in a job); neither comes from the caller.

- ``link`` is idempotent: linking the same pair with the same kind again returns the live row's id.
- ``unlink`` soft-deletes the live link; linking again afterwards creates a new row.
- ``traverse`` follows links outward from a record, breadth by depth, up to ``MAX_DEPTH`` hops.
  A recursive CTE carries the visited path, so a cycle ends at the record that closes it: for
  ``a -> b -> c -> a`` the walk from ``a`` is ``b, c, a`` and stops. Each record is reported once,
  at its shortest depth, ordered by depth, then type, then id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.context import ContextMissingError, get_context, new_request_id

__all__ = ["MAX_DEPTH", "LinkService", "RecordRef"]

MAX_DEPTH: Final = 5
_CODE = re.compile(r"[a-z][a-z0-9_]{0,62}")


@dataclass(frozen=True, slots=True)
class RecordRef:
    """A record anywhere in the product: its stable type code and id, e.g. ``("ncr", id)``."""

    type: str
    id: UUID

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.type):
            raise ValueError(f"record type must be a snake_case code: {self.type!r}")


def _actor() -> UUID | None:
    try:
        return get_context().actor_id
    except ContextMissingError:
        return None


_INSERT = text("""
INSERT INTO record_links
  (id, tenant_id, from_type, from_id, to_type, to_id, asset_id, link_kind, created_by)
VALUES
  (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid, :from_type, :from_id,
   :to_type, :to_id, :asset_id, :kind, :created_by)
ON CONFLICT (tenant_id, from_type, from_id, to_type, to_id, link_kind) WHERE deleted_at IS NULL
DO NOTHING
RETURNING id
""")

_EXISTING = text("""
SELECT id FROM record_links
WHERE from_type = :from_type AND from_id = :from_id AND to_type = :to_type AND to_id = :to_id
  AND link_kind = :kind AND deleted_at IS NULL
""")

_UNLINK = text("""
UPDATE record_links SET deleted_at = now(), updated_at = now()
WHERE from_type = :from_type AND from_id = :from_id AND to_type = :to_type AND to_id = :to_id
  AND link_kind = :kind AND deleted_at IS NULL
RETURNING id
""")

# ``path`` holds "type:id" keys of every record on the way here, the start included. An edge back
# to a record on the path is still reported (``closes``) but never followed.
_TRAVERSE = text("""
WITH RECURSIVE walk (ref_type, ref_id, depth, path, closes) AS (
  SELECT l.to_type, l.to_id, 1,
         ARRAY[CAST(:start_key AS text), l.to_type || ':' || l.to_id::text],
         (l.to_type || ':' || l.to_id::text) = CAST(:start_key AS text)
  FROM record_links l
  WHERE l.from_type = :from_type AND l.from_id = :from_id AND l.deleted_at IS NULL
  UNION ALL
  SELECT l.to_type, l.to_id, w.depth + 1,
         w.path || (l.to_type || ':' || l.to_id::text),
         (l.to_type || ':' || l.to_id::text) = ANY (w.path)
  FROM walk w
  JOIN record_links l
    ON l.from_type = w.ref_type AND l.from_id = w.ref_id AND l.deleted_at IS NULL
  WHERE NOT w.closes AND w.depth < :max_depth
)
SELECT ref_type, ref_id, min(depth) AS depth
FROM walk
GROUP BY ref_type, ref_id
ORDER BY depth, ref_type, ref_id
""")


def _check_kind(kind: str) -> None:
    if not _CODE.fullmatch(kind):
        raise ValueError(f"link kind must be a snake_case code: {kind!r}")


def _pair(from_ref: RecordRef, to_ref: RecordRef, kind: str) -> dict[str, object]:
    return {
        "from_type": from_ref.type,
        "from_id": from_ref.id,
        "to_type": to_ref.type,
        "to_id": to_ref.id,
        "kind": kind,
    }


class LinkService:
    """Stateless; the connection carries the tenant."""

    async def link(
        self,
        conn: AsyncConnection,
        from_ref: RecordRef,
        to_ref: RecordRef,
        kind: str,
        asset_id: UUID | None = None,
    ) -> UUID:
        """Link ``from_ref -> to_ref`` with ``kind``; return the new or already-live link's id."""
        _check_kind(kind)
        if from_ref == to_ref:
            raise ValueError("a record cannot link to itself")
        params = _pair(from_ref, to_ref, kind)
        inserted = (
            await conn.execute(
                _INSERT,
                {
                    **params,
                    "id": UUID(new_request_id()),  # the platform's UUIDv7 generator
                    "asset_id": asset_id,
                    "created_by": _actor(),
                },
            )
        ).scalar_one_or_none()
        if inserted is not None:
            return inserted
        return (await conn.execute(_EXISTING, params)).scalar_one()

    async def unlink(
        self, conn: AsyncConnection, from_ref: RecordRef, to_ref: RecordRef, kind: str
    ) -> bool:
        """Soft-delete the live link; ``False`` when there is none (in this tenant)."""
        _check_kind(kind)
        removed = await conn.execute(_UNLINK, _pair(from_ref, to_ref, kind))
        return removed.first() is not None

    async def traverse(
        self, conn: AsyncConnection, ref: RecordRef, max_depth: int = MAX_DEPTH
    ) -> list[tuple[RecordRef, int]]:
        """Every record reachable from ``ref`` within ``max_depth`` hops, as ``(ref, depth)``."""
        if not 1 <= max_depth <= MAX_DEPTH:
            raise ValueError(f"max_depth must be between 1 and {MAX_DEPTH}, got {max_depth}")
        rows = await conn.execute(
            _TRAVERSE,
            {
                "from_type": ref.type,
                "from_id": ref.id,
                "start_key": f"{ref.type}:{ref.id}",
                "max_depth": max_depth,
            },
        )
        return [(RecordRef(row.ref_type, row.ref_id), row.depth) for row in rows]
