"""Published interface of the assets module (ASSETS-01).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the asset work joins their transaction and RLS applies. Every event the
create and delete helpers emit lands in that same transaction.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.assets import repository as repo
from aip.modules.assets.policies import normalise_tag_number
from aip.modules.assets.schemas import AssetCreate, AssetOut
from aip.modules.assets.service import create_asset_on, soft_delete_assets_on
from aip.platform.db.errors import NotFoundError

__all__ = ["AssetCreate", "AssetOut", "AssetsApi"]


class AssetsApi:
    """The operations the assets module offers to other modules (ASSETS-01 step 10)."""

    async def get_asset(self, conn: AsyncConnection, asset_id: UUID) -> AssetOut | None:
        """The live asset ``asset_id`` in the connection's tenant, or ``None``."""
        row = await repo.get_asset(conn, asset_id)
        if row is None:
            return None
        count = await repo.child_count(conn, asset_id)
        return AssetOut.model_validate({**row, "child_count": count})

    async def assert_asset_exists(self, conn: AsyncConnection, asset_id: UUID) -> None:
        """Raise ``NotFoundError`` (HTTP 404) unless the asset is live in this tenant."""
        if await repo.get_asset(conn, asset_id) is None:
            raise NotFoundError(f"asset {asset_id} not found")

    async def create_asset(
        self, conn: AsyncConnection, actor_id: UUID, data: AssetCreate
    ) -> AssetOut:
        """Create one asset (ASSETS-01 step 6a) on the caller's connection; emits ``asset.created``.

        ``actor_id`` is stored in ``created_by``; used by DATAIO-02.
        """
        asset, _created = await create_asset_on(conn, actor_id, data)
        return asset

    async def find_by_tag_number(self, conn: AsyncConnection, tag_number: str) -> AssetOut | None:
        """The live asset whose Tag Number matches (case-insensitive, after normalisation)."""
        normalised = normalise_tag_number(tag_number)
        if normalised is None:
            return None
        row = await repo.find_live_by_tag_number(conn, normalised)
        if row is None:
            return None
        return AssetOut.model_validate(
            {**row, "child_count": await repo.child_count(conn, row["id"])}
        )

    async def subtree_ids(self, conn: AsyncConnection, asset_id: UUID) -> list[UUID]:
        """The node and its live descendants, root first; empty if the node is not live here."""
        row = await repo.get_asset(conn, asset_id)
        if row is None:
            return []
        return await repo.subtree_ids(conn, row["path"])

    async def soft_delete_assets(
        self, conn: AsyncConnection, asset_ids: list[UUID], *, reason: str
    ) -> int:
        """Soft-delete the assets deepest first, emitting ``asset.deleted`` with ``reason``.

        Refuses with ``DomainError(409, "ASSET_HAS_CHILDREN")`` if any listed asset has a live child
        that is not itself listed (DATAIO-02's batch rollback).
        """
        return await soft_delete_assets_on(conn, asset_ids, reason=reason)
