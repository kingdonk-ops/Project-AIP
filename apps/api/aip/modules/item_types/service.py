"""Business logic for content types, item categories, item types (ITEMTYPES-01) and item-type
attribute-schema versions (ITEMTYPES-02).

Every operation runs in one ``with_tenant(get_context())`` transaction. Rows of another tenant are
invisible under RLS, so they come back as 404 (``NOT_FOUND``), never 403. Keys are unique per
tenant among live rows; a clash is a 409 with the entity's ``*_KEY_TAKEN`` code. Updates use the
optimistic ``sync_version`` helper, so a stale write is a 409 ``VERSION_CONFLICT`` carrying the
stored row (camelCase, for a field diff).

Versions: at most one draft per item type, edited until it is published and frozen. Draft creation
and publish lock the item type ``FOR UPDATE``, so two publishes of one draft serialise and the
second sees it already published (409 ``VERSION_NOT_DRAFT``). Publish writes the version, the item
type's ``published_version_id`` and the ``item_type.version_published`` outbox event in the one
transaction, so a failed emit leaves all three untouched.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.item_types import repository as repo
from aip.modules.item_types.attribute_schema import compile_schema, lint_attributes
from aip.modules.item_types.events import ITEM_TYPE_VERSION_PUBLISHED, VersionPublished
from aip.modules.item_types.field_types import field_types
from aip.modules.item_types.policies import (
    MAX_CATEGORIES_PER_CONTENT_TYPE,
    MAX_CONTENT_TYPES,
    MAX_ITEM_TYPES,
)
from aip.modules.item_types.schemas import (
    CategoryCreate,
    CategoryOut,
    CategoryPage,
    CategoryUpdate,
    ContentTypeCreate,
    ContentTypeOut,
    ContentTypePage,
    ContentTypeUpdate,
    FieldTypeOut,
    FieldTypesOut,
    ItemTypeCreate,
    ItemTypeOut,
    ItemTypePage,
    ItemTypeUpdate,
    ItemTypeVersionListItem,
    ItemTypeVersionOut,
    ItemTypeVersionPage,
    VersionPublish,
    VersionUpdate,
    attribute_dicts,
)
from aip.modules.item_types.tables import (
    content_types,
    item_categories,
    item_type_versions,
    item_types,
)
from aip.platform.context import get_context, new_request_id
from aip.platform.db.errors import ConflictError, NotFoundError
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "FIELD_TYPES_VERSION",
    "CategoryService",
    "ContentTypeService",
    "ItemTypeService",
    "ItemTypeVersionService",
    "field_registry",
]

_UNIQUE_VIOLATION: Final = "23505"
FIELD_TYPES_VERSION: Final = 1

_SYNC: Final = frozenset({"sync_version"})


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


@asynccontextmanager
async def _unique(code: str) -> AsyncIterator[None]:
    """Turn a unique violation (the per-tenant live-key index) into a 409 with ``code``."""
    try:
        yield
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION:
            raise DomainError(409, code) from None
        raise


def _ct_out(row: dict[str, Any]) -> dict[str, Any]:
    return ContentTypeOut.model_validate(row).model_dump(mode="json", by_alias=True)


def _cat_out(row: dict[str, Any]) -> dict[str, Any]:
    return CategoryOut.model_validate(row).model_dump(mode="json", by_alias=True)


def _it_out(row: dict[str, Any]) -> dict[str, Any]:
    return ItemTypeOut.model_validate(row).model_dump(mode="json", by_alias=True)


def _version_out(row: dict[str, Any]) -> dict[str, Any]:
    return ItemTypeVersionOut.model_validate(row).model_dump(mode="json", by_alias=True)


def _lint_or_raise(attributes: list[dict[str, Any]]) -> None:
    issues = lint_attributes(attributes)
    if issues:
        raise DomainError(422, "ATTRIBUTES_INVALID", issues=[i.as_dict() for i in issues])


def field_registry() -> FieldTypesOut:
    """The field-type registry as the ``/field-types`` route and JSON contract return it."""
    return FieldTypesOut(
        version=FIELD_TYPES_VERSION,
        field_types=[
            FieldTypeOut(
                key=field.key,
                term_key=field.term_key,
                usable_in=sorted(field.usable_in),
                config_schema=field.config_schema,
            )
            for field in field_types()
        ],
    )


class ContentTypeService:
    async def list(self, *, show_in_nav: bool | None) -> ContentTypePage:
        async with _tx() as conn:
            rows = await repo.list_content_types(conn, show_in_nav=show_in_nav)
        return ContentTypePage(items=[ContentTypeOut.model_validate(r) for r in rows])

    async def get(self, content_type_id: UUID) -> ContentTypeOut:
        async with _tx() as conn:
            row = await repo.content_type_with_count(conn, content_type_id)
        if row is None:
            raise NotFoundError(f"content type {content_type_id} not found")
        return ContentTypeOut.model_validate(row)

    async def create(self, body: ContentTypeCreate) -> ContentTypeOut:
        async with _tx() as conn, _unique("CONTENT_TYPE_KEY_TAKEN"):
            if await repo.count_live(conn, content_types) >= MAX_CONTENT_TYPES:
                raise DomainError(409, "LIMIT_REACHED", limit=MAX_CONTENT_TYPES)
            values = {**body.model_dump(), "id": _new_id(), "tenant_id": get_context().tenant_id}
            row = await repo.insert_row(conn, content_types, values)
        return ContentTypeOut.model_validate({**row, "item_type_count": 0})

    async def update(self, content_type_id: UUID, body: ContentTypeUpdate) -> ContentTypeOut:
        patch = body.changes(exclude=_SYNC)
        async with _tx() as conn, _unique("CONTENT_TYPE_KEY_TAKEN"):
            current = await repo.get_content_type(conn, content_type_id)
            if current is None:
                raise NotFoundError(f"content type {content_type_id} not found")
            count = await repo.content_type_item_count(conn, content_type_id)
            if current["sync_version"] != body.sync_version:
                raise ConflictError(_ct_out({**current, "item_type_count": count}))
            changed = {f: v for f, v in patch.items() if current[f] != v}
            if not changed:
                return ContentTypeOut.model_validate({**current, "item_type_count": count})
            try:
                row = await repo.update_row(
                    conn, content_types, content_type_id, body.sync_version, changed
                )
            except ConflictError as exc:
                raise ConflictError(
                    _ct_out({**dict(exc.current), "item_type_count": count})
                ) from None
            return ContentTypeOut.model_validate({**row, "item_type_count": count})

    async def delete(self, content_type_id: UUID) -> None:
        async with _tx() as conn:
            current = await repo.get_content_type(conn, content_type_id)
            if current is None:
                raise NotFoundError(f"content type {content_type_id} not found")
            if current["is_system"]:
                raise DomainError(409, "CONTENT_TYPE_SYSTEM")
            categories = await repo.content_type_in_use(conn, content_type_id)
            if categories:
                raise DomainError(409, "CONTENT_TYPE_IN_USE", categories=categories)
            await repo.delete_row(conn, content_types, content_type_id)

    async def reorder(self, ids: list[UUID]) -> ContentTypePage:
        async with _tx() as conn:
            live = await repo.live_content_type_ids(conn)
            if len(ids) != len(set(ids)) or sorted(ids) != sorted(live):
                raise DomainError(422, "ORDER_MISMATCH")
            await repo.set_content_type_order(conn, ids)
            rows = await repo.list_content_types(conn, show_in_nav=None)
        return ContentTypePage(items=[ContentTypeOut.model_validate(r) for r in rows])


class CategoryService:
    async def list(self, *, content_type_id: UUID) -> CategoryPage:
        async with _tx() as conn:
            rows = await repo.list_categories(conn, content_type_id)
        return CategoryPage(items=[CategoryOut.model_validate(r) for r in rows])

    async def get(self, category_id: UUID) -> CategoryOut:
        async with _tx() as conn:
            row = await repo.get_category(conn, category_id)
        if row is None:
            raise NotFoundError(f"item category {category_id} not found")
        return CategoryOut.model_validate(row)

    async def create(self, body: CategoryCreate) -> CategoryOut:
        async with _tx() as conn, _unique("CATEGORY_KEY_TAKEN"):
            if await repo.get_content_type(conn, body.content_type_id) is None:
                raise NotFoundError(f"content type {body.content_type_id} not found")
            if (
                await repo.count_live_categories(conn, body.content_type_id)
                >= MAX_CATEGORIES_PER_CONTENT_TYPE
            ):
                raise DomainError(409, "LIMIT_REACHED", limit=MAX_CATEGORIES_PER_CONTENT_TYPE)
            values = {**body.model_dump(), "id": _new_id(), "tenant_id": get_context().tenant_id}
            row = await repo.insert_row(conn, item_categories, values)
        return CategoryOut.model_validate(row)

    async def update(self, category_id: UUID, body: CategoryUpdate) -> CategoryOut:
        patch = body.changes(exclude=_SYNC)
        async with _tx() as conn:
            current = await repo.get_category(conn, category_id)
            if current is None:
                raise NotFoundError(f"item category {category_id} not found")
            if current["sync_version"] != body.sync_version:
                raise ConflictError(_cat_out(current))
            changed = {f: v for f, v in patch.items() if current[f] != v}
            if not changed:
                return CategoryOut.model_validate(current)
            try:
                row = await repo.update_row(
                    conn, item_categories, category_id, body.sync_version, changed
                )
            except ConflictError as exc:
                raise ConflictError(_cat_out(dict(exc.current))) from None
            return CategoryOut.model_validate(row)

    async def delete(self, category_id: UUID) -> None:
        async with _tx() as conn:
            current = await repo.get_category(conn, category_id)
            if current is None:
                raise NotFoundError(f"item category {category_id} not found")
            item_count = await repo.category_in_use(conn, category_id)
            if item_count:
                raise DomainError(409, "CATEGORY_IN_USE", **{"itemTypes": item_count})
            await repo.delete_row(conn, item_categories, category_id)


class ItemTypeService:
    async def list(
        self, *, content_type_id: UUID | None, category_id: UUID | None, q: str | None
    ) -> ItemTypePage:
        async with _tx() as conn:
            rows = await repo.list_item_types(
                conn, content_type_id=content_type_id, category_id=category_id, q=q
            )
        return ItemTypePage(items=[ItemTypeOut.model_validate(r) for r in rows])

    async def get(self, item_type_id: UUID) -> ItemTypeOut:
        async with _tx() as conn:
            row = await repo.get_item_type(conn, item_type_id)
        if row is None:
            raise NotFoundError(f"item type {item_type_id} not found")
        return ItemTypeOut.model_validate(row)

    async def create(self, body: ItemTypeCreate) -> ItemTypeOut:
        async with _tx() as conn, _unique("ITEM_TYPE_KEY_TAKEN"):
            category = await repo.get_category(conn, body.category_id)
            if category is None:
                raise NotFoundError(f"item category {body.category_id} not found")
            if await repo.count_live(conn, item_types) >= MAX_ITEM_TYPES:
                raise DomainError(409, "LIMIT_REACHED", limit=MAX_ITEM_TYPES)
            values = {**body.model_dump(), "id": _new_id(), "tenant_id": get_context().tenant_id}
            row = await repo.insert_row(conn, item_types, values)
            row["content_type_id"] = category["content_type_id"]
        return ItemTypeOut.model_validate(row)

    async def update(self, item_type_id: UUID, body: ItemTypeUpdate) -> ItemTypeOut:
        patch = body.changes(exclude=_SYNC)
        async with _tx() as conn:
            current = await repo.get_item_type(conn, item_type_id)
            if current is None:
                raise NotFoundError(f"item type {item_type_id} not found")
            if current["sync_version"] != body.sync_version:
                raise ConflictError(_it_out(current))
            changed = {f: v for f, v in patch.items() if current[f] != v}
            if not changed:
                return ItemTypeOut.model_validate(current)
            try:
                updated = await repo.update_row(
                    conn, item_types, item_type_id, body.sync_version, changed
                )
            except ConflictError as exc:
                raise ConflictError(_it_out({**current, **dict(exc.current)})) from None
            # The joined columns (content type, version pointers) come from the read above.
            return ItemTypeOut.model_validate({**current, **updated})

    async def delete(self, item_type_id: UUID) -> None:
        async with _tx() as conn:
            if await repo.get_item_type(conn, item_type_id) is None:
                raise NotFoundError(f"item type {item_type_id} not found")
            if await repo.any_published_version(conn, item_type_id):
                raise DomainError(409, "ITEM_TYPE_PUBLISHED")
            await repo.delete_row(conn, item_types, item_type_id)


async def _version_of(
    conn: AsyncConnection, item_type_id: UUID, version_id: UUID
) -> dict[str, Any]:
    """The live version ``version_id`` of item type ``item_type_id``; 404 otherwise."""
    row = await repo.get_version(conn, version_id)
    if row is None or row["item_type_id"] != item_type_id:
        raise NotFoundError(f"item type version {version_id} not found")
    return row


def _draft(row: dict[str, Any]) -> dict[str, Any]:
    if row["status"] != "draft":
        raise DomainError(409, "VERSION_NOT_DRAFT")
    return row


class ItemTypeVersionService:
    async def list(self, item_type_id: UUID) -> ItemTypeVersionPage:
        async with _tx() as conn:
            if await repo.get_item_type(conn, item_type_id) is None:
                raise NotFoundError(f"item type {item_type_id} not found")
            rows = await repo.list_versions(conn, item_type_id)
        return ItemTypeVersionPage(items=[ItemTypeVersionListItem.model_validate(r) for r in rows])

    async def get(self, item_type_id: UUID, version_id: UUID) -> ItemTypeVersionOut:
        async with _tx() as conn:
            row = await _version_of(conn, item_type_id, version_id)
        return ItemTypeVersionOut.model_validate(row)

    async def create_draft(self, item_type_id: UUID) -> ItemTypeVersionOut:
        ctx = get_context()
        async with _tx() as conn:
            item_type = await repo.lock_item_type(conn, item_type_id)
            if item_type is None:
                raise NotFoundError(f"item type {item_type_id} not found")
            draft = await repo.live_draft(conn, item_type_id)
            if draft is not None:
                raise DomainError(409, "DRAFT_EXISTS", draftId=str(draft["id"]))
            attributes: list[dict[str, Any]] = []
            if item_type["published_version_id"] is not None:
                published = await repo.get_version(conn, item_type["published_version_id"])
                attributes = [] if published is None else published["attributes"]
            row = await repo.insert_row(
                conn,
                item_type_versions,
                {
                    "id": _new_id(),
                    "tenant_id": ctx.tenant_id,
                    "item_type_id": item_type_id,
                    "version": await repo.max_live_version(conn, item_type_id) + 1,
                    "status": "draft",
                    "attributes": attributes,
                    "created_by": ctx.actor_id,
                },
            )
        return ItemTypeVersionOut.model_validate(row)

    async def update_draft(
        self, item_type_id: UUID, version_id: UUID, body: VersionUpdate
    ) -> ItemTypeVersionOut:
        patch: dict[str, Any] = {}
        if body.attributes is not None:
            patch["attributes"] = attribute_dicts(body.attributes)
        if "change_summary" in body.model_fields_set:
            patch["change_summary"] = body.change_summary
        async with _tx() as conn:
            current = _draft(await _version_of(conn, item_type_id, version_id))
            if "attributes" in patch:
                _lint_or_raise(patch["attributes"])
            if current["sync_version"] != body.sync_version:
                raise ConflictError(_version_out(current))
            if not patch:
                return ItemTypeVersionOut.model_validate(current)
            try:
                row = await repo.update_row(
                    conn, item_type_versions, version_id, body.sync_version, patch
                )
            except ConflictError as exc:
                raise ConflictError(_version_out(dict(exc.current))) from None
        return ItemTypeVersionOut.model_validate(row)

    async def discard_draft(self, item_type_id: UUID, version_id: UUID) -> None:
        async with _tx() as conn:
            _draft(await _version_of(conn, item_type_id, version_id))
            await repo.delete_row(conn, item_type_versions, version_id)

    async def publish(
        self, item_type_id: UUID, version_id: UUID, body: VersionPublish
    ) -> ItemTypeVersionOut:
        actor = get_context().actor_id
        async with _tx() as conn:
            item_type = await repo.lock_item_type(conn, item_type_id)
            if item_type is None:
                raise NotFoundError(f"item type {item_type_id} not found")
            # Read under the item-type lock: a concurrent publish may already have frozen it.
            current = _draft(await _version_of(conn, item_type_id, version_id))
            _lint_or_raise(current["attributes"])
            if current["sync_version"] != body.sync_version:
                raise ConflictError(_version_out(current))
            patch: dict[str, Any] = {
                "status": "published",
                "compiled_schema": compile_schema(current["attributes"]),
                "published_at": func.now(),
                "published_by": actor,
            }
            if "change_summary" in body.model_fields_set:
                patch["change_summary"] = body.change_summary
            try:
                row = await repo.update_row(
                    conn, item_type_versions, version_id, body.sync_version, patch
                )
            except ConflictError as exc:
                raise ConflictError(_version_out(dict(exc.current))) from None
            await repo.set_published_version(conn, item_type_id, version_id)
            payload = VersionPublished(
                item_type_id=item_type_id,
                item_type_key=item_type["key"],
                version_id=version_id,
                version=row["version"],
                previous_version_id=item_type["published_version_id"],
            ).model_dump(mode="json")
            await emit(
                conn,
                ITEM_TYPE_VERSION_PUBLISHED,
                1,
                Aggregate("item_type", item_type_id),
                payload,
            )
        return ItemTypeVersionOut.model_validate(row)
