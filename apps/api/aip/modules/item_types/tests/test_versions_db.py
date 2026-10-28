"""ITEMTYPES-02 integration tests: item-type versions, the freeze trigger and pinning on Postgres.

The app connects as ``aip_app`` (RLS on). Users come from the AUTH_TEST_STUB principal header;
permissions from the ``grants`` fixture. The two fixture tenants are kaefer-demo (A) and tenant-b
(B). ``pipe_spool`` is tenant A's item type, created through the ITEMTYPES-01 API.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.item_types.api import ItemTypesApi
from aip.platform.db.errors import NotFoundError

from .conftest import ALICE, BOB, GrantTable, su_fetch

ITEM_TYPES = "/api/v1/item-types"
EVENT = "item_type.version_published"
api = ItemTypesApi()

WALL_THICKNESS: dict[str, Any] = {
    "key": "wall_thickness",
    "label": "Wall thickness",
    "fieldType": "measurement",
    "required": True,
    "config": {"unit": "mm", "min": 0, "max": 100},
}


async def _post(client: httpx.AsyncClient, url: str, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(url, json=body, headers=ALICE)
    assert response.status_code == 201, response.text
    return response.json()


async def _item_type(client: httpx.AsyncClient, key: str) -> str:
    content_type = await _post(client, "/api/v1/content-types", {"key": f"ct_{key}", "name": "C"})
    category = await _post(
        client,
        "/api/v1/item-categories",
        {"contentTypeId": content_type["id"], "key": f"cat_{key}", "name": "Cat"},
    )
    item_type = await _post(
        client, ITEM_TYPES, {"categoryId": category["id"], "key": key, "name": key}
    )
    return item_type["id"]


@pytest.fixture
async def pipe_spool(client: httpx.AsyncClient) -> str:
    return await _item_type(client, "pipe_spool")


def _versions(item_type_id: str) -> str:
    return f"{ITEM_TYPES}/{item_type_id}/versions"


async def _draft(client: httpx.AsyncClient, item_type_id: str) -> dict[str, Any]:
    response = await client.post(_versions(item_type_id), headers=ALICE)
    assert response.status_code == 201, response.text
    return response.json()


async def _patch(
    client: httpx.AsyncClient, item_type_id: str, version: dict[str, Any], attributes: list[Any]
) -> httpx.Response:
    return await client.patch(
        f"{_versions(item_type_id)}/{version['id']}",
        json={"attributes": attributes, "syncVersion": version["syncVersion"]},
        headers=ALICE,
    )


async def _publish(
    client: httpx.AsyncClient, item_type_id: str, version_id: str, sync_version: int
) -> httpx.Response:
    return await client.post(
        f"{_versions(item_type_id)}/{version_id}/publish",
        json={"syncVersion": sync_version},
        headers=ALICE,
    )


async def _published_v1(client: httpx.AsyncClient, item_type_id: str) -> dict[str, Any]:
    draft = await _draft(client, item_type_id)
    patched = await _patch(client, item_type_id, draft, [WALL_THICKNESS])
    assert patched.status_code == 200, patched.text
    published = await _publish(client, item_type_id, draft["id"], patched.json()["syncVersion"])
    assert published.status_code == 200, published.text
    return published.json()


async def _events(db: TenantDb) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT payload FROM domain_events WHERE event_name = $1 ORDER BY occurred_at",
        EVENT,
    )
    return [json.loads(r[0]) for r in rows]  # asyncpg returns jsonb as text


async def test_one_draft_at_a_time_starting_at_version_one(
    client: httpx.AsyncClient, pipe_spool: str
) -> None:
    draft = await _draft(client, pipe_spool)
    assert (draft["version"], draft["status"], draft["attributes"]) == (1, "draft", [])

    again = await client.post(_versions(pipe_spool), headers=ALICE)
    assert again.status_code == 409
    assert again.json() == {"code": "DRAFT_EXISTS", "draftId": draft["id"]}


async def test_patch_lints_and_a_bad_attribute_writes_nothing(
    client: httpx.AsyncClient, pipe_spool: str
) -> None:
    draft = await _draft(client, pipe_spool)
    ok = await _patch(client, pipe_spool, draft, [WALL_THICKNESS])
    assert ok.status_code == 200, ok.text
    assert ok.json()["syncVersion"] == 2

    photo = {"key": "picture", "label": "Picture", "fieldType": "photo"}
    bad = await _patch(client, pipe_spool, ok.json(), [photo])
    assert bad.status_code == 422
    body = bad.json()
    assert body["code"] == "ATTRIBUTES_INVALID"
    assert body["issues"][0] == {
        "path": "attributes[0].fieldType",
        "code": "ATTRIBUTE_FIELD_TYPE_NOT_ALLOWED",
    }

    stored = (await client.get(f"{_versions(pipe_spool)}/{draft['id']}", headers=ALICE)).json()
    assert stored["attributes"] == [WALL_THICKNESS] and stored["syncVersion"] == 2


async def test_a_stale_sync_version_is_a_conflict(
    client: httpx.AsyncClient, pipe_spool: str
) -> None:
    draft = await _draft(client, pipe_spool)
    assert (await _patch(client, pipe_spool, draft, [WALL_THICKNESS])).status_code == 200
    stale = await _patch(client, pipe_spool, draft, [])
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"


async def test_publish_needs_the_publish_permission(
    client: httpx.AsyncClient, db: TenantDb, grants: GrantTable, pipe_spool: str
) -> None:
    draft = await _draft(client, pipe_spool)
    grants.by_user[ALICE_ID].discard("item_type.publish")

    denied = await _publish(client, pipe_spool, draft["id"], draft["syncVersion"])
    assert denied.status_code == 403
    assert await _events(db) == []


async def test_publish_freezes_the_version_points_the_item_type_and_emits_once(
    client: httpx.AsyncClient, db: TenantDb, pipe_spool: str
) -> None:
    v1 = await _published_v1(client, pipe_spool)
    assert v1["status"] == "published"
    assert v1["publishedAt"].endswith(("Z", "+00:00"))
    assert v1["compiledSchema"]["properties"]["wall_thickness"]["maximum"] == 100

    item_type = (await client.get(f"{ITEM_TYPES}/{pipe_spool}", headers=ALICE)).json()
    assert item_type["publishedVersion"] == 1
    assert item_type["publishedVersionId"] == v1["id"]
    assert item_type["draftVersionId"] is None

    events = await _events(db)
    assert len(events) == 1
    assert events[0]["version"] == 1 and events[0]["previousVersionId"] is None
    assert events[0]["itemTypeKey"] == "pipe_spool" and events[0]["versionId"] == v1["id"]

    listed = (await client.get(_versions(pipe_spool), headers=ALICE)).json()["items"]
    assert [v["version"] for v in listed] == [1] and "compiledSchema" not in listed[0]


async def test_a_published_version_cannot_change_through_the_api_or_the_database(
    client: httpx.AsyncClient, db: TenantDb, pipe_spool: str
) -> None:
    v1 = await _published_v1(client, pipe_spool)

    frozen = await _patch(client, pipe_spool, v1, [])
    assert frozen.status_code == 409 and frozen.json()["code"] == "VERSION_NOT_DRAFT"
    discard = await client.delete(f"{_versions(pipe_spool)}/{v1['id']}", headers=ALICE)
    assert discard.status_code == 409 and discard.json()["code"] == "VERSION_NOT_DRAFT"

    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(DBAPIError, match="published item type version is immutable") as exc:
            await conn.execute(
                text("UPDATE item_type_versions SET attributes = '[]' WHERE id = :id"),
                {"id": v1["id"]},
            )
        assert getattr(exc.value.orig, "sqlstate", None) == "55000"
    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(
                text("DELETE FROM item_type_versions WHERE id = :id"), {"id": v1["id"]}
            )


async def test_a_newer_version_does_not_move_assets_pinned_to_the_older_one(
    client: httpx.AsyncClient, db: TenantDb, pipe_spool: str
) -> None:
    v1 = await _published_v1(client, pipe_spool)

    v2 = await _draft(client, pipe_spool)
    assert v2["version"] == 2 and v2["attributes"] == [WALL_THICKNESS]
    narrower = {**WALL_THICKNESS, "config": {"unit": "mm", "min": 0, "max": 50}}
    patched = await _patch(client, pipe_spool, v2, [narrower])
    published = await _publish(client, pipe_spool, v2["id"], patched.json()["syncVersion"])
    assert published.status_code == 200, published.text

    item_type = (await client.get(f"{ITEM_TYPES}/{pipe_spool}", headers=ALICE)).json()
    assert item_type["publishedVersion"] == 2
    events = await _events(db)
    assert [e["previousVersionId"] for e in events] == [None, v1["id"]]

    async with db.with_tenant(TENANT_A_ID) as conn:
        assert await api.validate_attributes(conn, UUID(v1["id"]), {"wall_thickness": 80}) == []
        errors = await api.validate_attributes(conn, UUID(v2["id"]), {"wall_thickness": 80})
        assert [e.term_key for e in errors] == ["validation.attribute.maximum"]
        current = await api.get_published_version(conn, UUID(pipe_spool))
        assert current is not None and current.version == 2


async def test_the_api_sees_published_versions_only(
    client: httpx.AsyncClient, db: TenantDb, pipe_spool: str
) -> None:
    draft = await _draft(client, pipe_spool)
    empty_type = await _item_type(client, "flange")

    async with db.with_tenant(TENANT_A_ID) as conn:
        assert await api.get_version(conn, UUID(draft["id"])) is None
        with pytest.raises(NotFoundError):
            await api.validate_attributes(conn, UUID(draft["id"]), {})
        assert await api.get_published_version(conn, UUID(empty_type)) is None


async def test_the_validate_route_checks_a_sample_against_a_published_version(
    client: httpx.AsyncClient, pipe_spool: str
) -> None:
    v1 = await _published_v1(client, pipe_spool)
    response = await client.post(
        f"{_versions(pipe_spool)}/{v1['id']}/validate",
        json={"attributes": {"wall_thickness": "thick"}},
        headers=ALICE,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is False
    assert body["errors"][0]["path"] == "$.wall_thickness"
    assert body["errors"][0]["termKey"] == "validation.attribute.type"

    fine = await client.post(
        f"{_versions(pipe_spool)}/{v1['id']}/validate",
        json={"attributes": {"wall_thickness": 12.5}},
        headers=ALICE,
    )
    assert fine.json() == {"valid": True, "errors": []}


async def test_two_concurrent_publishes_yield_one_success_and_one_conflict(
    client: httpx.AsyncClient, db: TenantDb, pipe_spool: str
) -> None:
    draft = await _draft(client, pipe_spool)
    first, second = await asyncio.gather(
        _publish(client, pipe_spool, draft["id"], draft["syncVersion"]),
        _publish(client, pipe_spool, draft["id"], draft["syncVersion"]),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]

    rows = await su_fetch(
        db,
        "SELECT count(*) FROM item_type_versions WHERE item_type_id = $1::uuid "
        "AND version = 1 AND status = 'published'",
        pipe_spool,
    )
    assert rows[0][0] == 1
    assert len(await _events(db)) == 1


async def test_a_failed_emit_rolls_back_the_whole_publish(
    lenient_client: httpx.AsyncClient, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    item_type_id = await _item_type(lenient_client, "pipe_spool")
    draft = await _draft(lenient_client, item_type_id)

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("outbox down")

    monkeypatch.setattr("aip.modules.item_types.service.emit", boom)
    failed = await _publish(lenient_client, item_type_id, draft["id"], draft["syncVersion"])
    assert failed.status_code == 500

    rows = await su_fetch(
        db, "SELECT status FROM item_type_versions WHERE id = $1::uuid", draft["id"]
    )
    assert rows[0][0] == "draft"
    pointer = await su_fetch(
        db, "SELECT published_version_id FROM item_types WHERE id = $1::uuid", item_type_id
    )
    assert pointer[0][0] is None


async def test_an_item_type_with_a_published_version_cannot_be_deleted(
    client: httpx.AsyncClient, pipe_spool: str
) -> None:
    await _published_v1(client, pipe_spool)
    response = await client.delete(f"{ITEM_TYPES}/{pipe_spool}", headers=ALICE)
    assert response.status_code == 409 and response.json() == {"code": "ITEM_TYPE_PUBLISHED"}


async def test_a_discarded_draft_frees_its_version_number(
    client: httpx.AsyncClient, pipe_spool: str
) -> None:
    draft = await _draft(client, pipe_spool)
    gone = await client.delete(f"{_versions(pipe_spool)}/{draft['id']}", headers=ALICE)
    assert gone.status_code == 204
    again = await _draft(client, pipe_spool)
    assert again["version"] == 1 and again["id"] != draft["id"]


async def test_another_tenant_sees_nothing(
    client: httpx.AsyncClient, db: TenantDb, pipe_spool: str
) -> None:
    v1 = await _published_v1(client, pipe_spool)

    response = await client.get(f"{_versions(pipe_spool)}/{v1['id']}", headers=BOB)
    assert response.status_code == 404
    assert (await client.get(_versions(pipe_spool), headers=BOB)).status_code == 404
    async with db.with_tenant(TENANT_B_ID) as conn:
        assert await api.get_version(conn, UUID(v1["id"])) is None
