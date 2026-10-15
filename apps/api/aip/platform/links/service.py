"""``LinkService``: link records to each other and to an asset, and walk the links (ARCH-08).

Every method runs on the caller's ``with_tenant`` connection, so a link commits or rolls back with
the caller's own change, and RLS keeps each tenant to its own links. The row's ``tenant_id`` is the
connection's ``app.tenant_id`` and ``created_by`` is the request context's actor (``None`` outside
a request, e.g. in a job); neither comes from the caller.

- ``link`` is idempotent: linking the same pair with the same kind again returns the live row's id.
- ``unlink`` soft-deletes the live link; linking again afterwards creates a new row.
- ``traverse`` follows links outward from a record breadth-first, up to ``MAX_DEPTH`` hops, one
  query per depth over the whole frontier with a visited set. Each record is reported and expanded
  once, at its shortest depth (ordered by depth, then type, then id), so a cycle ends at the record
  that closes it (``a -> b -> c -> a`` from ``a`` is ``b, c, a``) and the cost grows with the
  records reached, not with the number of paths (a recursive CTE with a visited-*path* array, as
  first specified, expands every simple path: about fan-out^depth rows on a dense graph).

Contract for callers: a link stores ids only. ``link`` does not check that either record or the
asset exists or that the caller may see them (the platform cannot read module tables), so a module
must authorise both ends before linking, and must re-read every record ``traverse`` returns through
its own service (RLS and ``requires()``) before showing it. Linking an existing pair and kind again
returns the live link unchanged, including its original ``asset_id``.
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


# DO UPDATE (a no-op on updated_at) rather than DO NOTHING: it locks the live row and returns its
# id in the same statement, so a concurrent ``unlink`` cannot make the id vanish between two reads.
_INSERT = text("""
INSERT INTO record_links
  (id, tenant_id, from_type, from_id, to_type, to_id, asset_id, link_kind, created_by)
VALUES
  (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid, :from_type, :from_id,
   :to_type, :to_id, :asset_id, :kind, :created_by)
ON CONFLICT (tenant_id, from_type, from_id, to_type, to_id, link_kind) WHERE deleted_at IS NULL
DO UPDATE SET updated_at = record_links.updated_at
RETURNING id
""")

_UNLINK = text("""
UPDATE record_links SET deleted_at = now(), updated_at = now()
WHERE from_type = :from_type AND from_id = :from_id AND to_type = :to_type AND to_id = :to_id
  AND link_kind = :kind AND deleted_at IS NULL
RETURNING id
""")

# One hop from a whole frontier: the distinct live targets (any kind) of the given records.
_NEXT = text("""
SELECT DISTINCT l.to_type, l.to_id
FROM record_links l
JOIN unnest(CAST(:types AS text[]), CAST(:ids AS uuid[])) AS f (ref_type, ref_id)
  ON l.from_type = f.ref_type AND l.from_id = f.ref_id
WHERE l.deleted_at IS NULL
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
        return (
            await conn.execute(
                _INSERT,
                {
                    **params,
                    "id": UUID(new_request_id()),  # the platform's UUIDv7 generator
                    "asset_id": asset_id,
                    "created_by": _actor(),
                },
            )
        ).scalar_one()

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
        found: list[tuple[RecordRef, int]] = []
        seen: set[RecordRef] = set()  # the start is not in it: a cycle back to it is reported once
        frontier = [ref]
        for depth in range(1, max_depth + 1):
            rows = await conn.execute(
                _NEXT,
                {"types": [r.type for r in frontier], "ids": [r.id for r in frontier]},
            )
            level = sorted(
                {RecordRef(row.to_type, row.to_id) for row in rows} - seen,
                key=lambda r: (r.type, r.id),
            )
            if not level:
                break
            seen.update(level)
            found.extend((r, depth) for r in level)
            frontier = [r for r in level if r != ref]  # the start was already expanded
        return found
