"""Pydantic request/response models for item_types (ITEMTYPES-01).

JSON is camelCase (``syncVersion``, ``contentTypeId``), bodies forbid unknown fields. Keys are
immutable after create, so no update model declares ``key``: sending it is a 422. ``value_schema``
never appears in the wire contract — only ``configSchema`` does.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

__all__ = [
    "CategoryCreate",
    "CategoryOut",
    "CategoryPage",
    "CategoryUpdate",
    "ContentTypeCreate",
    "ContentTypeOrder",
    "ContentTypeOut",
    "ContentTypePage",
    "ContentTypeUpdate",
    "FieldTypeOut",
    "FieldTypesOut",
    "ItemTypeCreate",
    "ItemTypeErrorBody",
    "ItemTypeOut",
    "ItemTypePage",
    "ItemTypeUpdate",
]

ApplicableFor = Literal["any", "item", "module"]

# Stable snake_case key (1-63 chars) and an @aip/ui icon name; the same patterns as the CHECKs.
KEY_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
ICON_PATTERN = r"^[a-z][a-z0-9-]{0,39}$"

Key = Annotated[str, Field(pattern=KEY_PATTERN)]
Icon = Annotated[str, Field(pattern=ICON_PATTERN)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Description = Annotated[str, Field(max_length=2000)]
SortOrder = Annotated[int, Field(ge=0, le=1_000_000)]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    """A response built from database rows: columns the API does not show are ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class _Patch(_Model):
    """A partial update: absent fields stay as they are; ``REQUIRED`` fields may not be null."""

    REQUIRED: ClassVar[tuple[str, ...]] = ()

    sync_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _required_not_null(self) -> Self:
        nulls = [
            f for f in self.REQUIRED if f in self.model_fields_set and getattr(self, f) is None
        ]
        if nulls:
            raise ValueError(f"{', '.join(nulls)} cannot be null")
        return self

    def changes(self, *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
        """The fields the client sent, by column name (``sync_version`` excluded by callers)."""
        return {f: getattr(self, f) for f in self.model_fields_set - exclude}


class ItemTypeErrorBody(_Out):
    """A domain error: a stable ``code`` (``CONTENT_TYPE_IN_USE``, ``LIMIT_REACHED``, ...)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")

    code: str


# --- content types ----------------------------------------------------------------------------


class ContentTypeCreate(_Model):
    key: Key
    name: Name
    icon: Icon = "folder"
    sort_order: SortOrder = 0
    show_in_nav: bool = True


class ContentTypeUpdate(_Patch):
    REQUIRED: ClassVar[tuple[str, ...]] = ("name", "icon", "sort_order", "show_in_nav")

    name: Name | None = None
    icon: Icon | None = None
    sort_order: SortOrder | None = None
    show_in_nav: bool | None = None


class ContentTypeOut(_Out):
    id: UUID
    key: str
    name: str
    icon: str
    sort_order: int
    show_in_nav: bool
    is_system: bool
    item_type_count: int
    sync_version: int
    created_at: datetime
    updated_at: datetime


class ContentTypePage(_Out):
    items: list[ContentTypeOut]


class ContentTypeOrder(_Model):
    ids: Annotated[list[UUID], Field(min_length=1, max_length=50)]


# --- item categories --------------------------------------------------------------------------


class CategoryCreate(_Model):
    content_type_id: UUID
    key: Key
    name: Name
    applicable_for: ApplicableFor = "any"
    sort_order: SortOrder = 0


class CategoryUpdate(_Patch):
    REQUIRED: ClassVar[tuple[str, ...]] = ("name", "applicable_for", "sort_order")

    name: Name | None = None
    applicable_for: ApplicableFor | None = None
    sort_order: SortOrder | None = None


class CategoryOut(_Out):
    id: UUID
    content_type_id: UUID
    key: str
    name: str
    applicable_for: ApplicableFor
    sort_order: int
    sync_version: int
    created_at: datetime
    updated_at: datetime


class CategoryPage(_Out):
    items: list[CategoryOut]


# --- item types -------------------------------------------------------------------------------


class ItemTypeCreate(_Model):
    category_id: UUID
    key: Key
    name: Name
    description: Description | None = None
    is_component: bool = False
    allows_components: bool = False


class ItemTypeUpdate(_Patch):
    REQUIRED: ClassVar[tuple[str, ...]] = ("name", "is_component", "allows_components")

    name: Name | None = None
    description: Description | None = None
    is_component: bool | None = None
    allows_components: bool | None = None


class ItemTypeOut(_Out):
    id: UUID
    category_id: UUID
    content_type_id: UUID
    key: str
    name: str
    description: str | None
    is_component: bool
    allows_components: bool
    sync_version: int
    created_at: datetime
    updated_at: datetime


class ItemTypePage(_Out):
    items: list[ItemTypeOut]


# --- field-type registry ----------------------------------------------------------------------


class FieldTypeOut(_Out):
    key: str
    term_key: str
    usable_in: list[str]
    config_schema: dict[str, Any]


class FieldTypesOut(_Out):
    version: int
    field_types: list[FieldTypeOut]
