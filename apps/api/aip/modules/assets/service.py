"""Business logic for the asset tree (ASSETS-01).

Every operation runs in one ``with_tenant(get_context())`` transaction, so the outbox event commits
or rolls back with the change. Rows of another tenant are invisible under RLS and come back as 404,
never 403. Writes that read a parent's path (create-with-parent, move, delete) take a tenant-scoped
advisory lock first, so concurrent tree edits serialise.

Typed assets (ASSETS-02): an asset with an item type is pinned to the version of that type that was
published when it was typed, and its ``attributes`` are validated against that pinned version on
every create and edit. Item types are reached only through ``ItemTypesApi`` (ADR 0004), inside the
operation's transaction; the service never reads item_types tables or re-implements schema checks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.assets import repository as repo
from aip.modules.assets.events import (
    ASSET_CREATED,
    ASSET_DELETED,
    ASSET_MOVED,
    ASSET_UPDATED,
)
from aip.modules.assets.policies import internal_tag
from aip.modules.assets.schemas import (
    Ancestor,
    AssetCreate,
    AssetDetail,
    AssetMove,
    AssetOut,
    AssetPage,
    AssetSort,
    AssetUpdate,
)
from aip.modules.assets.settings import get_settings
from aip.modules.assets.tables import assets
from aip.modules.item_types.api import AttributeValidationError, ItemTypesApi
from aip.platform.context import RequestContext, get_context, new_request_id, use_context
from aip.platform.db.concurrency import update_with_version
from aip.platform.db.errors import ConflictError, CycleError, NotFoundError
from aip.platform.db.idempotency import create_idempotent
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError
from aip.platform.http.csv import CsvColumn, csv_header, csv_row
from aip.platform.http.cursor import CursorCodec, InvalidCursorError

__all__ = [
    "EXPORT_COLUMNS",
    "EXPORT_MAX_ROWS",
    "AssetService",
    "attribute_errors",
    "cursor_codec",
]

MAX_DEPTH: Final = 15

# The CSV export (ASSETS-03): at most this many rows, read this many per transaction. Headers are
# the API's field names, so a file reads the same in every tenant and locale (ADR 0033).
EXPORT_MAX_ROWS: Final = 10_000
_EXPORT_BATCH: Final = 500
EXPORT_COLUMNS: Final[tuple[CsvColumn, ...]] = tuple(
    {"id": name}
    for name in (
        "internalTag",
        "tagNumber",
        "name",
        "parentId",
        "path",
        "itemTypeId",
        "itemTypeVersionId",
        "updatedAt",
    )
)
_TAG_INDEX: Final = "uq_assets_tenant_id_upper_tag_number"
_COLLISION_INDEXES: Final = frozenset(
    {"uq_assets_tenant_id_internal_tag", "uq_assets_tenant_id_path"}
)

# The event ``before``/``after`` keys for the columns a PATCH can change (ASSETS-01 step 6b).
_CHANGE_ALIASES: Final = {
    "name": "name",
    "tag_number": "tagNumber",
    "item_type_id": "itemTypeId",
    "item_type_version_id": "itemTypeVersionId",
    "attributes": "attributes",
}

_item_types: Final = ItemTypesApi()


def cursor_codec() -> CursorCodec:
    return CursorCodec(get_settings().cursor_key.get_secret_value().encode())


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


def _level(path: str) -> int:
    return path.count(".") + 1


def _raise_tag_in_use(holder: dict[str, Any] | None) -> None:
    extra: dict[str, Any] = {}
    if holder is not None:
        extra = {"assetId": str(holder["id"]), "internalTag": holder["internal_tag"]}
    raise DomainError(409, "TAG_NUMBER_IN_USE", **extra)


async def _child_count(conn: AsyncConnection, asset_id: UUID) -> int:
    return await repo.child_count(conn, asset_id)


async def _out(conn: AsyncConnection, row: dict[str, Any]) -> AssetOut:
    return AssetOut.model_validate({**row, "child_count": await _child_count(conn, row["id"])})


async def _out_json(conn: AsyncConnection, row: dict[str, Any]) -> dict[str, Any]:
    out = await _out(conn, row)
    return out.model_dump(mode="json", by_alias=True)


def _changed(patch: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    return {field: value for field, value in patch.items() if current[field] != value}


def _camel(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        _CHANGE_ALIASES[field]: str(value) if isinstance(value, UUID) else value
        for field, value in fields.items()
    }


# --- typing (ASSETS-02) -----------------------------------------------------------------------


def attribute_errors(errors: list[AttributeValidationError]) -> list[dict[str, str]]:
    """The 422 ``errors`` list: ``$.diameter_mm`` → ``attributes.diameter_mm``; the code is the
    JSON Schema keyword at the end of the ``validation.attribute.<keyword>`` term key."""
    return [
        {
            "path": "attributes" + error.path.removeprefix("$"),
            "code": error.term_key.rsplit(".", 1)[-1],
        }
        for error in errors
    ]


def _require_type_for(attributes: dict[str, Any] | None) -> None:
    """An untyped asset carries no attributes (``ck_assets_untyped_attributes``)."""
    if attributes:
        raise DomainError(422, "ATTRIBUTES_WITHOUT_TYPE", field="attributes")


async def _pin(conn: AsyncConnection, item_type_id: UUID) -> UUID:
    """The id of the item type's current published version, or 422 ``ITEM_TYPE_NOT_PUBLISHED``
    (an unknown, another tenant's, archived or never-published type all look the same)."""
    version = await _item_types.get_published_version(conn, item_type_id)
    if version is None:
        raise DomainError(422, "ITEM_TYPE_NOT_PUBLISHED", field="itemTypeId")
    return version.id


async def _validate(conn: AsyncConnection, version_id: UUID, attributes: dict[str, Any]) -> None:
    errors = await _item_types.validate_attributes(conn, version_id, attributes)
    if errors:
        raise DomainError(
            422, "ATTRIBUTES_INVALID", field="attributes", errors=attribute_errors(errors)
        )


async def _typing_patch(
    conn: AsyncConnection, current: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """The ``item_type_id``/``item_type_version_id``/``attributes`` columns a PATCH sets.

    ``itemTypeId`` (same type or another) re-pins to that type's current published version and
    validates the body's attributes, or the stored ones when absent; ``itemTypeId: null`` clears
    the type and needs ``{}`` or no attributes. ``attributes`` alone is validated against the
    version the asset is already pinned to, never a newer one.
    """
    if "item_type_id" in patch:
        item_type_id: UUID | None = patch["item_type_id"]
        if item_type_id is None:
            _require_type_for(patch.get("attributes"))
            return {"item_type_id": None, "item_type_version_id": None, "attributes": {}}
        version_id = await _pin(conn, item_type_id)
        attributes = patch.get("attributes", current["attributes"])
        await _validate(conn, version_id, attributes)
        return {
            "item_type_id": item_type_id,
            "item_type_version_id": version_id,
            "attributes": attributes,
        }
    if "attributes" in patch:
        if current["item_type_version_id"] is None:
            _require_type_for(patch["attributes"])
            return {"attributes": {}}
        await _validate(conn, current["item_type_version_id"], patch["attributes"])
        return {"attributes": patch["attributes"]}
    return {}


# --- create (shared by the API router and the published interface) ----------------------------


async def create_asset_on(
    conn: AsyncConnection, actor_id: UUID | None, data: AssetCreate
) -> tuple[AssetOut, bool]:
    """Create one asset on ``conn`` and emit ``asset.created``; the ASSETS-01 step 6a rules.

    Returns ``(asset, created)``; a ``clientGeneratedId`` replay returns the first row with
    ``created=False`` and emits nothing. With ``itemTypeId`` the asset is pinned to the type's
    current published version and its attributes validated against it (ASSETS-02).
    """
    if data.item_type_id is None:
        _require_type_for(data.attributes)  # before any SQL
    version_id: UUID | None = None
    if data.item_type_id is not None:
        version_id = await _pin(conn, data.item_type_id)
        await _validate(conn, version_id, data.attributes)
    parent: dict[str, Any] | None = None
    if data.parent_id is not None:
        await repo.lock_tree(conn)
        parent = await repo.get_asset(conn, data.parent_id)
        if parent is None:
            raise DomainError(422, "PARENT_NOT_FOUND", field="parentId")
        if _level(parent["path"]) + 1 > MAX_DEPTH:
            raise DomainError(422, "ASSET_TREE_TOO_DEEP")
    if data.tag_number is not None:
        holder = await repo.find_live_by_tag_number(conn, data.tag_number)
        if holder is not None:
            _raise_tag_in_use(holder)

    sort_order = await repo.max_sibling_sort_order(conn, data.parent_id) + 1
    row, created = await _insert_with_retry(conn, actor_id, data, parent, sort_order, version_id)
    if created:
        typed = (
            _camel({f: row[f] for f in ("item_type_id", "item_type_version_id", "attributes")})
            if row["item_type_id"] is not None
            else None
        )
        await emit(
            conn,
            ASSET_CREATED,
            1,
            Aggregate("asset", row["id"]),
            _event_payload(row, after=typed),
            asset_id=row["id"],
        )
    return await _out(conn, row), created


async def _insert_with_retry(
    conn: AsyncConnection,
    actor_id: UUID | None,
    data: AssetCreate,
    parent: dict[str, Any] | None,
    sort_order: int,
    version_id: UUID | None,
) -> tuple[dict[str, Any], bool]:
    """Insert the row, regenerating the id once on the (astronomically unlikely) internal-tag or
    path collision; a Tag Number index race becomes a 409. Each attempt is its own savepoint, so a
    caught violation does not poison the caller's transaction."""
    for attempt in (0, 1):
        asset_id = _new_id()
        label = asset_id.hex
        values: dict[str, Any] = {
            "id": asset_id,
            "tenant_id": get_context().tenant_id,
            "parent_id": data.parent_id,
            "path": label if parent is None else f"{parent['path']}.{label}",
            "internal_tag": internal_tag(asset_id),
            "tag_number": data.tag_number,
            "name": data.name,
            "sort_order": sort_order,
            "created_by": actor_id,
            "item_type_id": data.item_type_id,
            "item_type_version_id": version_id,
            "attributes": data.attributes,
        }
        try:
            async with conn.begin_nested():
                if data.client_generated_id is not None:
                    result = await create_idempotent(
                        conn, assets, {**values, "client_generated_id": data.client_generated_id}
                    )
                    return result.row, result.created
                return await repo.insert_asset(conn, values), True
        except IntegrityError as exc:
            constraint = getattr(exc.orig, "constraint_name", "") or ""
            if constraint == _TAG_INDEX:
                holder = (
                    await repo.find_live_by_tag_number(conn, data.tag_number)
                    if data.tag_number is not None
                    else None
                )
                _raise_tag_in_use(holder)
            if constraint in _COLLISION_INDEXES and attempt == 0:
                continue
            raise
    raise AssertionError("unreachable")  # pragma: no cover


def _event_payload(
    row: dict[str, Any],
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "assetId": str(row["id"]),
        "internalTag": row["internal_tag"],
        "tagNumber": row["tag_number"],
        "parentId": str(row["parent_id"]) if row["parent_id"] is not None else None,
        "before": before,
        "after": after,
    }


def _deleted_payload(row: dict[str, Any], reason: str | None) -> dict[str, Any]:
    return {
        "assetId": str(row["id"]),
        "internalTag": row["internal_tag"],
        "tagNumber": row["tag_number"],
        "parentId": str(row["parent_id"]) if row["parent_id"] is not None else None,
        "reason": reason,
    }


# --- delete (shared) --------------------------------------------------------------------------


async def soft_delete_assets_on(
    conn: AsyncConnection, asset_ids: list[UUID], *, reason: str | None
) -> int:
    """Soft-delete ``asset_ids`` deepest first; refuse if any has a live child not in the set.

    Emits one ``asset.deleted`` per asset carrying ``reason``. Used by the single-asset delete
    (``reason=None``) and by DATAIO-02's batch rollback.
    """
    await repo.lock_tree(conn)
    requested = set(asset_ids)
    loaded: list[dict[str, Any]] = []
    for asset_id in asset_ids:
        row = await repo.lock_node(conn, asset_id)
        if row is None:
            raise NotFoundError(f"asset {asset_id} not found")
        loaded.append(row)
    for row in loaded:
        children = await repo.live_child_ids(conn, row["id"])
        outside = [cid for cid in children if cid not in requested]
        if outside:
            raise DomainError(409, "ASSET_HAS_CHILDREN", childCount=len(outside))
    # Delete deepest first so a parent never outlives a listed child mid-transaction.
    for row in sorted(loaded, key=lambda r: _level(r["path"]), reverse=True):
        deleted = await repo.soft_delete_asset(conn, row["id"])
        await emit(
            conn,
            ASSET_DELETED,
            1,
            Aggregate("asset", row["id"]),
            _deleted_payload(deleted, reason),
            asset_id=row["id"],
        )
    return len(loaded)


# --- the service ------------------------------------------------------------------------------


class AssetService:
    async def create(self, body: AssetCreate) -> tuple[AssetOut, bool]:
        async with _tx() as conn:
            return await create_asset_on(conn, get_context().actor_id, body)

    async def get(self, asset_id: UUID) -> AssetDetail:
        async with _tx() as conn:
            row = await repo.get_asset(conn, asset_id)
            if row is None:
                raise NotFoundError(f"asset {asset_id} not found")
            ancestry = await repo.ancestors(conn, row["path"])
            child_count = await repo.child_count(conn, asset_id)
        return AssetDetail.model_validate(
            {
                **row,
                "child_count": child_count,
                "ancestors": [Ancestor.model_validate(a) for a in ancestry],
            }
        )

    async def update(self, asset_id: UUID, body: AssetUpdate) -> AssetOut:
        patch = body.changes()
        async with _tx() as conn:
            current = await repo.lock_node(conn, asset_id)
            if current is None:
                raise NotFoundError(f"asset {asset_id} not found")
            if current["sync_version"] != body.sync_version:
                raise ConflictError(await _out_json(conn, current))
            if "tag_number" in patch and patch["tag_number"] is not None:
                holder = await repo.find_live_by_tag_number(conn, patch["tag_number"])
                if holder is not None and holder["id"] != asset_id:
                    _raise_tag_in_use(holder)
            typing = await _typing_patch(conn, current, patch)
            patch = {
                **{f: v for f, v in patch.items() if f not in ("item_type_id", "attributes")},
                **typing,
            }
            changed = _changed(patch, current)
            if not changed:
                return await _out(conn, current)
            try:
                async with conn.begin_nested():
                    row = await update_with_version(
                        conn, assets, asset_id, body.sync_version, changed
                    )
            except IntegrityError as exc:
                tag = patch.get("tag_number")
                if (getattr(exc.orig, "constraint_name", "") or "") == _TAG_INDEX and tag:
                    _raise_tag_in_use(await repo.find_live_by_tag_number(conn, tag))
                raise
            except ConflictError as exc:
                raise ConflictError(await _out_json(conn, dict(exc.current))) from None
            await emit(
                conn,
                ASSET_UPDATED,
                1,
                Aggregate("asset", asset_id),
                _event_payload(
                    row,
                    before=_camel({f: current[f] for f in changed}),
                    after=_camel({f: row[f] for f in changed}),
                ),
                asset_id=asset_id,
            )
            return await _out(conn, row)

    async def move(self, asset_id: UUID, body: AssetMove) -> AssetOut:
        async with _tx() as conn:
            await repo.lock_tree(conn)
            node = await repo.lock_node(conn, asset_id)
            if node is None:
                raise NotFoundError(f"asset {asset_id} not found")
            if node["sync_version"] != body.sync_version:
                raise ConflictError(await _out_json(conn, node))
            parent: dict[str, Any] | None = None
            if body.parent_id is not None:
                parent = await repo.get_asset(conn, body.parent_id)
                if parent is None:
                    raise DomainError(422, "PARENT_NOT_FOUND", field="parentId")
            if node["parent_id"] == body.parent_id:
                return await _out(conn, node)  # same parent: no change, no event

            old_path = node["path"]
            parent_path = parent["path"] if parent is not None else None
            if parent_path is not None and (
                parent_path == old_path or parent_path.startswith(old_path + ".")
            ):
                raise CycleError(f"cannot move {old_path} under {parent_path}")

            height = await repo.subtree_max_level(conn, old_path) - _level(old_path)
            new_level = 1 if parent_path is None else _level(parent_path) + 1
            if new_level + height > MAX_DEPTH:
                raise DomainError(422, "ASSET_TREE_TOO_DEEP")

            label = asset_id.hex
            new_path = label if parent_path is None else f"{parent_path}.{label}"
            sort_order = await repo.max_sibling_sort_order(conn, body.parent_id) + 1
            moved = await repo.move_node(
                conn,
                old_path=old_path,
                new_parent_path=parent_path,
                new_parent_id=body.parent_id,
                sort_order=sort_order,
            )
            await emit(
                conn,
                ASSET_MOVED,
                1,
                Aggregate("asset", asset_id),
                {
                    "assetId": str(asset_id),
                    "fromParentId": str(node["parent_id"]) if node["parent_id"] else None,
                    "toParentId": str(body.parent_id) if body.parent_id else None,
                    "fromPath": old_path,
                    "toPath": new_path,
                    "movedCount": moved,
                },
                asset_id=asset_id,
            )
            row = await repo.get_asset(conn, asset_id)
            assert row is not None
            return await _out(conn, row)

    async def delete(self, asset_id: UUID, sync_version: int) -> None:
        async with _tx() as conn:
            node = await repo.lock_node(conn, asset_id)
            if node is None:
                raise NotFoundError(f"asset {asset_id} not found")
            if node["sync_version"] != sync_version:
                raise ConflictError(await _out_json(conn, node))
            children = await repo.child_count(conn, asset_id)
            if children:
                raise DomainError(409, "ASSET_HAS_CHILDREN", childCount=children)
            deleted = await repo.soft_delete_asset(conn, asset_id)
            await emit(
                conn,
                ASSET_DELETED,
                1,
                Aggregate("asset", asset_id),
                _deleted_payload(deleted, None),
                asset_id=asset_id,
            )

    async def list(
        self,
        *,
        limit: int,
        cursor: str | None,
        sort: AssetSort | None,
        parent_id: str | None,
        under: UUID | None,
        q: str | None,
        tag_number: str | None,
        item_type_ids: list[UUID] | None = None,
    ) -> AssetPage:
        token = _sort_token(sort, parent_id)
        async with _tx() as conn:
            filters = await _filters(conn, parent_id, under, q, tag_number, item_type_ids)
            if filters is None:
                return AssetPage(items=[], next_cursor=None)
            page = self._keyset(cursor, token, limit)
            rows = await repo.list_assets(conn, page, **filters)
        items = [AssetOut.model_validate(r) for r in rows[:limit]]
        return AssetPage(items=items, next_cursor=_next_cursor(rows, token, limit))

    async def export_csv(
        self,
        *,
        sort: AssetSort | None,
        parent_id: str | None,
        under: UUID | None,
        q: str | None,
        tag_number: str | None,
        item_type_ids: list[UUID] | None = None,
    ) -> AsyncIterator[str]:
        """The rows ``list`` would page through, as CSV chunks (ASSETS-03, ADR 0033).

        Raises ``EXPORT_TOO_LARGE`` (422) up front when more than ``EXPORT_MAX_ROWS`` rows match,
        so a client never receives a silently truncated file. The chunks are read in keyset
        batches, each in its own tenant transaction, while the response streams. An unknown (or
        another tenant's) ``under`` exports the header only, as the list answers an empty page.
        """
        token = _sort_token(sort, parent_id)
        async with _tx() as conn:
            filters = await _filters(conn, parent_id, under, q, tag_number, item_type_ids)
            total = 0 if filters is None else await repo.count_assets(conn, **filters)
        if total > EXPORT_MAX_ROWS:
            raise DomainError(422, "EXPORT_TOO_LARGE", limit=EXPORT_MAX_ROWS)
        if filters is None:
            return _header_only()
        keyset = self._keyset(None, token, _EXPORT_BATCH)
        return _csv_chunks(get_context(), keyset, token, filters)

    @staticmethod
    def _keyset(cursor: str | None, token: str, limit: int) -> repo.Keyset:
        base = token.removeprefix("-")
        descending = token.startswith("-")
        if cursor is None:
            return repo.Keyset(sort=base, descending=descending, limit=limit)
        try:
            data = cursor_codec().decode(cursor)
            if data.get("sort") != token:
                raise InvalidCursorError("cursor was issued for another sort order")
            values = _decode_keys(base, data["keys"])
            after_id = UUID(data["id"])
        except (InvalidCursorError, KeyError, TypeError, ValueError, IndexError):
            raise DomainError(422, "INVALID_CURSOR", field="cursor") from None
        return repo.Keyset(
            sort=base,
            descending=descending,
            limit=limit,
            after_values=values,
            after_id=after_id,
        )


def _sort_token(sort: AssetSort | None, parent_id: str | None) -> str:
    """The sort to use: the caller's, else ``position`` for one parent's children, else ``name``."""
    return sort or ("position" if parent_id is not None else "name")


async def _filters(
    conn: AsyncConnection,
    parent_id: str | None,
    under: UUID | None,
    q: str | None,
    tag_number: str | None,
    item_type_ids: list[UUID] | None,
) -> dict[str, Any] | None:
    """The repository filters for the list and the export, or ``None`` when ``under`` names no
    live asset of this tenant (the answer is then empty, never a 404 that would leak existence)."""
    roots_only = parent_id == "root"
    parent_uuid = _parse_parent(parent_id) if parent_id is not None and not roots_only else None
    under_path: str | None = None
    if under is not None:
        under_row = await repo.get_asset(conn, under)
        if under_row is None:
            return None
        under_path = under_row["path"]
    return {
        "parent_id": parent_uuid,
        "roots_only": roots_only,
        "under_path": under_path,
        "q": q,
        "tag_number": tag_number,
        "item_type_ids": item_type_ids or None,
    }


def _export_row(row: dict[str, Any]) -> dict[str, Any]:
    out = AssetOut.model_validate(row).model_dump(mode="json", by_alias=True)
    return {**out, "path": row.get("path_names") or ""}


async def _header_only() -> AsyncIterator[str]:
    yield csv_header(EXPORT_COLUMNS)


async def _csv_chunks(
    ctx: RequestContext, keyset: repo.Keyset, token: str, filters: dict[str, Any]
) -> AsyncIterator[str]:
    """The header, then one chunk per keyset batch. The response streams after the route has
    returned, so each batch sets the request's context again for its tenant transaction."""
    yield csv_header(EXPORT_COLUMNS)
    sent = 0
    base = token.removeprefix("-")
    while sent < EXPORT_MAX_ROWS:
        with use_context(ctx):
            async with _tx() as conn:
                rows = await repo.list_assets(conn, keyset, with_path_names=True, **filters)
        batch = rows[: min(keyset.limit, EXPORT_MAX_ROWS - sent)]
        if not batch:
            return
        yield "".join(csv_row(EXPORT_COLUMNS, _export_row(row)) for row in batch)
        sent += len(batch)
        if len(rows) <= keyset.limit:
            return
        last = batch[-1]
        keyset = repo.Keyset(
            sort=base,
            descending=keyset.descending,
            limit=keyset.limit,
            after_values=_key_values(base, last),
            after_id=last["id"],
        )


def _parse_parent(parent_id: str) -> UUID:
    try:
        return UUID(parent_id)
    except ValueError:
        raise DomainError(422, "INVALID_PARENT_ID", field="parentId") from None


def _key_values(sort: str, row: dict[str, Any]) -> tuple[Any, ...]:
    if sort == "position":
        return (row["sort_order"], row["name"])
    if sort == "name":
        return (row["name"],)
    if sort == "tagNumber":
        return (row["tag_number"] or "",)
    return (row["updated_at"],)  # updatedAt


def _decode_keys(sort: str, keys: list[Any]) -> tuple[Any, ...]:
    if sort == "position":
        return (int(keys[0]), str(keys[1]))
    if sort == "updatedAt":
        return (datetime.fromisoformat(keys[0]),)
    return (keys[0],)


def _next_cursor(rows: list[dict[str, Any]], token: str, limit: int) -> str | None:
    if len(rows) <= limit:
        return None
    last = rows[limit - 1]
    base = token.removeprefix("-")
    values = _key_values(base, last)
    serial = [v.isoformat() if isinstance(v, datetime) else v for v in values]
    return cursor_codec().encode({"sort": token, "keys": serial, "id": str(last["id"])})
