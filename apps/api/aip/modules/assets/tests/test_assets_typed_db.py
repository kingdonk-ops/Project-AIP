"""ASSETS-02 integration tests: typed assets, version pinning and attribute validation on Postgres.

The app connects as ``aip_app`` (RLS on). Item types are defined and published through the
item_types routes (ITEMTYPES-01/02), never by inserting into their tables. ``Pump`` v1 has
``diameter_mm`` (number, required) and ``service`` (dropdown: water, steam).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import pytest
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.assets.api import AssetsApi
from aip.modules.assets.schemas import AssetCreate
from aip.platform.context import RequestContext, use_context
from aip.platform.db.session import with_tenant

from .conftest import ALICE, BOB, su_execute, su_fetch

ASSETS = "/api/v1/assets"
ITEM_TYPES = "/api/v1/item-types"

DIAMETER: dict[str, Any] = {
    "key": "diameter_mm",
    "label": "Diameter",
    "fieldType": "number",
    "required": True,
}
SERVICE: dict[str, Any] = {
    "key": "service",
    "label": "Service",
    "fieldType": "dropdown",
    "config": {
        "options": [{"value": "water", "label": "Water"}, {"value": "steam", "label": "Steam"}]
    },
}
MATERIAL: dict[str, Any] = {
    "key": "material",
    "label": "Material",
    "fieldType": "text",
    "required": True,
}


async def _post(
    client: httpx.AsyncClient, url: str, body: dict[str, Any] | None, headers: dict[str, str]
) -> dict[str, Any]:
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


async def _item_type(client: httpx.AsyncClient, key: str, headers: dict[str, str] = ALICE) -> str:
    content_type = await _post(
        client, "/api/v1/content-types", {"key": f"ct_{key}", "name": "C"}, headers
    )
    category = await _post(
        client,
        "/api/v1/item-categories",
        {"contentTypeId": content_type["id"], "key": f"cat_{key}", "name": "Cat"},
        headers,
    )
    item_type = await _post(
        client, ITEM_TYPES, {"categoryId": category["id"], "key": key, "name": key}, headers
    )
    return item_type["id"]


async def _draft(
    client: httpx.AsyncClient,
    item_type_id: str,
    attributes: list[dict[str, Any]],
    headers: dict[str, str] = ALICE,
) -> dict[str, Any]:
    versions = f"{ITEM_TYPES}/{item_type_id}/versions"
    draft = await _post(client, versions, None, headers)
    patched = await client.patch(
        f"{versions}/{draft['id']}",
        json={"attributes": attributes, "syncVersion": draft["syncVersion"]},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    return patched.json()


async def _publish(
    client: httpx.AsyncClient,
    item_type_id: str,
    attributes: list[dict[str, Any]],
    headers: dict[str, str] = ALICE,
) -> str:
    draft = await _draft(client, item_type_id, attributes, headers)
    published = await _post(
        client,
        f"{ITEM_TYPES}/{item_type_id}/versions/{draft['id']}/publish",
        {"syncVersion": draft["syncVersion"]},
        headers,
    )
    return published["id"]


@pytest.fixture
async def pump(client: httpx.AsyncClient) -> tuple[str, str]:
    """(item type id, v1 id) for tenant A's published ``Pump``."""
    item_type_id = await _item_type(client, "pump")
    return item_type_id, await _publish(client, item_type_id, [DIAMETER, SERVICE])


async def _counts(db: TenantDb) -> tuple[int, int]:
    (assets,) = await su_fetch(db, "SELECT count(*) FROM assets")
    (events,) = await su_fetch(db, "SELECT count(*) FROM domain_events")
    return int(assets[0]), int(events[0])


async def _updated_events(db: TenantDb) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT payload FROM domain_events WHERE event_name = 'asset.updated'"
        " ORDER BY occurred_at",
    )
    return [json.loads(r[0]) for r in rows]  # asyncpg returns jsonb as text


async def test_a_typed_asset_is_pinned_to_the_published_version(
    client: httpx.AsyncClient, db: TenantDb, pump: tuple[str, str]
) -> None:
    pump_id, v1 = pump
    response = await client.post(
        ASSETS,
        json={
            "name": "P-101",
            "itemTypeId": pump_id,
            "attributes": {"diameter_mm": 150, "service": "steam"},
        },
        headers=ALICE,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["itemTypeId"], body["itemTypeVersionId"]) == (pump_id, v1)
    assert body["attributes"] == {"diameter_mm": 150, "service": "steam"}

    rows = await su_fetch(
        db, "SELECT payload FROM domain_events WHERE event_name = 'asset.created'"
    )
    after = json.loads(rows[0][0])["after"]
    assert (after["itemTypeId"], after["itemTypeVersionId"]) == (pump_id, v1)


async def test_invalid_attributes_list_every_field_and_write_nothing(
    client: httpx.AsyncClient, db: TenantDb, pump: tuple[str, str]
) -> None:
    pump_id, _ = pump
    before = await _counts(db)
    response = await client.post(
        ASSETS,
        json={"name": "P-101", "itemTypeId": pump_id, "attributes": {"service": "oil"}},
        headers=ALICE,
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "ATTRIBUTES_INVALID"
    assert {"path": "attributes.diameter_mm", "code": "required"} in body["errors"]
    assert "attributes.service" in {e["path"] for e in body["errors"]}
    assert await _counts(db) == before


async def test_edits_validate_against_the_pin_until_itemtypeid_re_pins(
    client: httpx.AsyncClient, db: TenantDb, pump: tuple[str, str]
) -> None:
    pump_id, v1 = pump
    created = await client.post(
        ASSETS,
        json={
            "name": "P-101",
            "itemTypeId": pump_id,
            "attributes": {"diameter_mm": 150, "service": "steam"},
        },
        headers=ALICE,
    )
    asset = created.json()
    url = f"{ASSETS}/{asset['id']}"
    v2 = await _publish(client, pump_id, [DIAMETER, SERVICE, MATERIAL])

    edited = await client.patch(
        url,
        json={"syncVersion": 1, "attributes": {"diameter_mm": 200, "service": "steam"}},
        headers=ALICE,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["itemTypeVersionId"] == v1  # a newer publish changes nothing

    re_pin = await client.patch(url, json={"syncVersion": 2, "itemTypeId": pump_id}, headers=ALICE)
    assert re_pin.status_code == 422, re_pin.text
    assert re_pin.json()["code"] == "ATTRIBUTES_INVALID"
    assert {"path": "attributes.material", "code": "required"} in re_pin.json()["errors"]

    pinned = await client.patch(
        url,
        json={
            "syncVersion": 2,
            "itemTypeId": pump_id,
            "attributes": {"diameter_mm": 200, "service": "steam", "material": "CS"},
        },
        headers=ALICE,
    )
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["itemTypeVersionId"] == v2
    last = (await _updated_events(db))[-1]
    assert last["before"]["itemTypeVersionId"] == v1
    assert last["after"]["itemTypeVersionId"] == v2

    cleared = await client.patch(
        url, json={"syncVersion": 3, "itemTypeId": None, "attributes": {}}, headers=ALICE
    )
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert (body["itemTypeId"], body["itemTypeVersionId"], body["attributes"]) == (None, None, {})


async def test_draft_only_and_other_tenant_types_are_not_published(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    draft_only = await _item_type(client, "valve")
    await _draft(client, draft_only, [DIAMETER])
    theirs = await _item_type(client, "pump_b", BOB)
    await _publish(client, theirs, [DIAMETER], BOB)

    for item_type_id in (draft_only, theirs):
        response = await client.post(
            ASSETS,
            json={"name": "P-1", "itemTypeId": item_type_id, "attributes": {"diameter_mm": 1}},
            headers=ALICE,
        )
        assert response.status_code == 422, response.text
        assert response.json() == {"code": "ITEM_TYPE_NOT_PUBLISHED", "field": "itemTypeId"}


async def test_untyped_assets_carry_no_attributes_enforced_by_the_database(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    refused = await client.post(
        ASSETS, json={"name": "Area 1", "attributes": {"x": 1}}, headers=ALICE
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "ATTRIBUTES_WITHOUT_TYPE"

    area = await client.post(ASSETS, json={"name": "Area 1"}, headers=ALICE)
    assert area.status_code == 201
    with pytest.raises(asyncpg.CheckViolationError, match="ck_assets_untyped_attributes"):
        await su_execute(db, """UPDATE assets SET attributes = '{"x":1}'""")


async def test_the_list_filters_by_item_type_within_the_tenant(
    client: httpx.AsyncClient, db: TenantDb, pump: tuple[str, str]
) -> None:
    pump_id, _ = pump
    for name in ("P-101", "P-102"):
        await client.post(
            ASSETS,
            json={"name": name, "itemTypeId": pump_id, "attributes": {"diameter_mm": 50}},
            headers=ALICE,
        )
    await client.post(ASSETS, json={"name": "Area 1"}, headers=ALICE)

    mine = await client.get(ASSETS, params={"itemTypeId": pump_id}, headers=ALICE)
    assert mine.status_code == 200, mine.text
    items = mine.json()["items"]
    assert sorted(i["name"] for i in items) == ["P-101", "P-102"]
    assert all(i["itemTypeId"] == pump_id and i["itemTypeVersionId"] for i in items)
    assert all(i["attributes"] == {"diameter_mm": 50} for i in items)

    theirs = await client.get(ASSETS, params={"itemTypeId": pump_id}, headers=BOB)
    assert theirs.json()["items"] == []


async def test_assets_api_creates_a_typed_asset_on_the_callers_connection(
    client: httpx.AsyncClient, db: TenantDb, pump: tuple[str, str]
) -> None:
    pump_id, _ = pump
    v2 = await _publish(client, pump_id, [DIAMETER, SERVICE, MATERIAL])
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id="test-typed", actor_id=ALICE_ID)
    data = AssetCreate(
        name="P-102",
        item_type_id=UUID(pump_id),
        attributes={"diameter_mm": 80, "material": "SS"},
    )
    with use_context(ctx):
        async with with_tenant(ctx) as conn:
            asset = await AssetsApi().create_asset(conn, ALICE_ID, data)
    assert asset.item_type_version_id == UUID(v2)
    assert asset.created_by == ALICE_ID
