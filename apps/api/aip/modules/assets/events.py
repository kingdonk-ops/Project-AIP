"""Domain events the assets module publishes (via the outbox, ADR 0003).

``asset.created`` and ``asset.updated`` (v1) share :class:`AssetEvent`
``{assetId, internalTag, tagNumber, parentId, before, after}``; ``before`` and ``after`` hold the
changed fields in camelCase (both null on ``asset.created``) and are open dicts, so ASSETS-02 can
add attribute fields without changing the released v1 schema. ``asset.moved`` carries
:class:`AssetMovedEvent` and ``asset.deleted`` :class:`AssetDeletedEvent` (which adds ``reason``).
The models register with the platform event registry on import.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = [
    "ASSET_CREATED",
    "ASSET_DELETED",
    "ASSET_MOVED",
    "ASSET_UPDATED",
    "AssetDeletedEvent",
    "AssetEvent",
    "AssetMovedEvent",
]

ASSET_CREATED = "asset.created"
ASSET_UPDATED = "asset.updated"
ASSET_MOVED = "asset.moved"
ASSET_DELETED = "asset.deleted"

_CONFIG = ConfigDict(
    alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
)


class AssetEvent(BaseModel):
    model_config = _CONFIG

    asset_id: UUID
    internal_tag: str
    tag_number: str | None = None
    parent_id: UUID | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class AssetMovedEvent(BaseModel):
    model_config = _CONFIG

    asset_id: UUID
    from_parent_id: UUID | None = None
    to_parent_id: UUID | None = None
    from_path: str
    to_path: str
    moved_count: int


class AssetDeletedEvent(BaseModel):
    model_config = _CONFIG

    asset_id: UUID
    internal_tag: str
    tag_number: str | None = None
    parent_id: UUID | None = None
    reason: str | None = None


for _name in (ASSET_CREATED, ASSET_UPDATED):
    register_event(_name, 1, AssetEvent, "assets")
register_event(ASSET_MOVED, 1, AssetMovedEvent, "assets")
register_event(ASSET_DELETED, 1, AssetDeletedEvent, "assets")
