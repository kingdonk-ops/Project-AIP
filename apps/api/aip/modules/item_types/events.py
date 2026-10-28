"""Domain events item_types publishes (via the outbox, ADR 0003).

- ``item_type.version_published`` v1: an item-type attribute-schema version was published and is
  now the item type's current version (ITEMTYPES-02). Payload ``{itemTypeId, itemTypeKey,
  versionId, version, previousVersionId}``; ``previousVersionId`` is ``null`` for version 1. Assets
  keep the version id they pinned, so this event never moves existing records.

The model is registered with the platform's event schemas when this module loads.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = ["ITEM_TYPE_VERSION_PUBLISHED", "VersionPublished"]

ITEM_TYPE_VERSION_PUBLISHED: Final = "item_type.version_published"


class _Event(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class VersionPublished(_Event):
    item_type_id: UUID
    item_type_key: str
    version_id: UUID
    version: int
    previous_version_id: UUID | None


register_event(ITEM_TYPE_VERSION_PUBLISHED, 1, VersionPublished, "item_types")
