"""Pydantic request/response models for the asset tree (ASSETS-01).

JSON is camelCase (``syncVersion``, ``parentId``, ``tagNumber``). Requests forbid unknown keys, so
an attempt to set ``internalTag`` or ``path`` is a 422. Tag Numbers are normalised (trim, collapse
inner whitespace) before they reach the service; an empty Tag Number becomes ``null``.

ASSETS-02: an asset may carry an ``itemTypeId`` and JSONB ``attributes``. ``itemTypeVersionId`` is
response-only: the server pins the version, so a request that sends it is a 422.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from aip.modules.assets.policies import normalise_tag_number

__all__ = [
    "Ancestor",
    "AssetCreate",
    "AssetDetail",
    "AssetErrorBody",
    "AssetListItem",
    "AssetMove",
    "AssetOut",
    "AssetPage",
    "AssetSort",
    "AssetUpdate",
]

# A leading "-" sorts descending. ``position`` is sort_order then name; it is the default when a
# ``parentId`` filter is given (siblings in their stored order).
AssetSort = Literal[
    "position",
    "-position",
    "name",
    "-name",
    "tagNumber",
    "-tagNumber",
    "updatedAt",
    "-updatedAt",
]

Name = Annotated[str, Field(min_length=1, max_length=200)]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    """A response: built from database rows, so columns the API does not show are ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class AssetErrorBody(_Out):
    """A domain error: a stable ``code`` (``TAG_NUMBER_IN_USE``, ``PARENT_NOT_FOUND``, ...)."""

    code: str


class AssetCreate(_Model):
    name: Name
    parent_id: UUID | None = None
    tag_number: Annotated[str | None, Field(max_length=200)] = None
    client_generated_id: UUID | None = None
    item_type_id: UUID | None = None
    attributes: dict[str, Any] = Field(default_factory=lambda: {})

    @model_validator(mode="after")
    def _normalise(self) -> Self:
        object.__setattr__(self, "tag_number", normalise_tag_number(self.tag_number))
        return self


class AssetUpdate(_Model):
    """Only the fields sent change; ``syncVersion`` is the version the client last read.

    ``name`` may not be set to null; ``internalTag``, ``path`` and ``parentId`` are rejected
    (extra=forbid), so a rename can never move a node or rewrite its identity.

    ``itemTypeId`` re-pins the asset to that type's current published version (``null`` clears the
    type); ``attributes`` alone is validated against the version the asset is already pinned to.
    """

    REQUIRED: ClassVar[tuple[str, ...]] = ("name", "attributes")

    sync_version: int = Field(ge=1)
    name: Name | None = None
    tag_number: Annotated[str | None, Field(max_length=200)] = None
    item_type_id: UUID | None = None
    attributes: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _required_not_null_and_normalise(self) -> Self:
        sent = self.model_fields_set
        nulls = [f for f in self.REQUIRED if f in sent and getattr(self, f) is None]
        if nulls:
            raise ValueError(f"{', '.join(nulls)} cannot be null")
        if "tag_number" in self.model_fields_set:
            object.__setattr__(self, "tag_number", normalise_tag_number(self.tag_number))
        return self

    def changes(self) -> dict[str, Any]:
        """The fields the client sent (by column name), excluding ``sync_version``."""
        return {f: getattr(self, f) for f in self.model_fields_set - {"sync_version"}}


class AssetMove(_Model):
    sync_version: int = Field(ge=1)
    parent_id: UUID | None = None


class AssetOut(_Out):
    id: UUID
    parent_id: UUID | None
    path: str
    internal_tag: str
    tag_number: str | None
    name: str
    sort_order: int
    item_type_id: UUID | None
    item_type_version_id: UUID | None
    attributes: dict[str, Any]
    created_by: UUID | None
    sync_version: int
    created_at: datetime
    updated_at: datetime
    child_count: int = 0


class Ancestor(_Out):
    id: UUID
    name: str
    internal_tag: str
    tag_number: str | None


class AssetDetail(AssetOut):
    ancestors: list[Ancestor]


class AssetListItem(AssetOut):
    """A list row: also the live ancestors' names, root first, the asset itself excluded, so the
    register and the parent picker draw breadcrumbs without fetching each parent (ASSETS-08)."""

    ancestor_names: list[str]


class AssetPage(_Out):
    items: list[AssetListItem]
    next_cursor: str | None
