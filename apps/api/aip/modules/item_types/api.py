"""Published interface of the item_types module (ITEMTYPES-01).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the read joins their transaction and RLS applies. The field-type registry
is re-exported here so forms (FORMS-01) and asset attributes (ASSETS-02/ITEMTYPES-02) share it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.item_types import repository as repo
from aip.modules.item_types.field_types import FieldType, field_types, get_field_type
from aip.modules.item_types.schemas import ItemTypeOut
from aip.platform.db.errors import NotFoundError

__all__ = ["FieldType", "ItemTypeOut", "ItemTypesApi", "field_types", "get_field_type"]


class ItemTypesApi:
    """The operations the item_types module offers to other modules."""

    async def get_item_type(self, conn: AsyncConnection, item_type_id: UUID) -> ItemTypeOut | None:
        """The live item type ``item_type_id`` in the connection's tenant, or ``None``."""
        row = await repo.get_item_type(conn, item_type_id)
        return None if row is None else ItemTypeOut.model_validate(row)

    async def assert_item_type_exists(self, conn: AsyncConnection, item_type_id: UUID) -> None:
        """Raise ``NotFoundError`` (HTTP 404) unless the item type is live in this tenant."""
        if await repo.get_item_type(conn, item_type_id) is None:
            raise NotFoundError(f"item type {item_type_id} not found")
