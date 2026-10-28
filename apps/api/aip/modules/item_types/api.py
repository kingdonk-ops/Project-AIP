"""Published interface of the item_types module (ITEMTYPES-01/02).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the read joins their transaction and RLS applies. The field-type registry
is re-exported here so forms (FORMS-01) and asset attributes (ASSETS-02/ITEMTYPES-02) share it.

Item-type versions (ITEMTYPES-02): only published versions are visible here, and a published
version never changes, so an asset that pins a version id keeps being validated against that
version's schema after newer versions are published.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.item_types import repository as repo
from aip.modules.item_types.field_types import FieldType, field_types, get_field_type
from aip.modules.item_types.schemas import ItemTypeOut, ItemTypeVersionOut
from aip.platform.db.errors import NotFoundError
from aip.platform.db.jsonb_schema import AttributeValidationError
from aip.platform.db.jsonb_schema import validate_attributes as _validate

__all__ = [
    "AttributeValidationError",
    "FieldType",
    "ItemTypeOut",
    "ItemTypeVersionOut",
    "ItemTypesApi",
    "field_types",
    "get_field_type",
]


def _published(row: dict[str, Any] | None) -> ItemTypeVersionOut | None:
    if row is None or row["status"] != "published":
        return None
    return ItemTypeVersionOut.model_validate(row)


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

    async def get_version(
        self, conn: AsyncConnection, version_id: UUID
    ) -> ItemTypeVersionOut | None:
        """A published version in this tenant, else ``None`` (a draft or another tenant's id)."""
        return _published(await repo.get_version(conn, version_id))

    async def get_published_version(
        self, conn: AsyncConnection, item_type_id: UUID
    ) -> ItemTypeVersionOut | None:
        """The item type's current published version, or ``None`` when none is published yet."""
        item_type = await repo.get_item_type(conn, item_type_id)
        if item_type is None or item_type["published_version_id"] is None:
            return None
        return _published(await repo.get_version(conn, item_type["published_version_id"]))

    async def validate_attributes(
        self, conn: AsyncConnection, version_id: UUID, attributes: dict[str, Any]
    ) -> list[AttributeValidationError]:
        """Every violation of published version ``version_id``'s schema by ``attributes``.

        Errors carry ``validation.attribute.<keyword>`` term keys. Raises ``NotFoundError`` when
        ``get_version`` would return ``None``.
        """
        version = await self.get_version(conn, version_id)
        if version is None or version.compiled_schema is None:
            raise NotFoundError(f"item type version {version_id} not found")
        return _validate(version.compiled_schema, attributes)
