"""ITEMTYPES-01 integration tests: the API and the three tables on real Postgres.

The app connects as ``aip_app`` (RLS on). Users come from the AUTH_TEST_STUB principal header;
permissions from the ``grants`` fixture. The two fixture tenants are kaefer-demo (A) and tenant-b
(B); A never sees B's rows and the reverse.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from .conftest import ALICE, BOB, GrantTable, su_fetch

CONTENT_TYPES = "/api/v1/content-types"
CATEGORIES = "/api/v1/item-categories"
ITEM_TYPES = "/api/v1/item-types"
FIELD_TYPES = "/api/v1/field-types"


async def _content_type(client: httpx.AsyncClient, headers: dict[str, str], **body: Any) -> dict:
    response = await client.post(CONTENT_TYPES, json={"icon": "folder", **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _category(client: httpx.AsyncClient, content_type_id: str, **body: Any) -> dict:
    response = await client.post(
        CATEGORIES, json={"contentTypeId": content_type_id, **body}, headers=ALICE
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _item_type(client: httpx.AsyncClient, category_id: str, **body: Any) -> dict:
    response = await client.post(
        ITEM_TYPES, json={"categoryId": category_id, **body}, headers=ALICE
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- field-type registry ----------------------------------------------------------------------


async def test_field_types_route_returns_the_registry(client: httpx.AsyncClient) -> None:
    body = (await client.get(FIELD_TYPES, headers=ALICE)).json()
    assert body["version"] == 1
    keys = [f["key"] for f in body["fieldTypes"]]
    assert keys[0] == "text" and keys[-1] == "user_ref" and len(keys) == 12
    measurement = next(f for f in body["fieldTypes"] if f["key"] == "measurement")
    assert measurement["configSchema"]["properties"]["unit"]["enum"] == ["mm", "bar", "degC"]


async def test_field_types_requires_view(client: httpx.AsyncClient, grants: GrantTable) -> None:
    grants.by_user[next(iter(grants.by_user))].clear()
    assert (await client.get(FIELD_TYPES, headers=ALICE)).status_code == 403


# --- content types ----------------------------------------------------------------------------


async def test_create_read_and_key_uniqueness(client: httpx.AsyncClient) -> None:
    created = await _content_type(client, ALICE, key="asset", name="Asset")
    assert (created["syncVersion"], created["isSystem"], created["itemTypeCount"]) == (1, False, 0)

    dup = await client.post(CONTENT_TYPES, json={"key": "asset", "name": "Asset 2"}, headers=ALICE)
    assert dup.status_code == 409
    assert dup.json() == {"code": "CONTENT_TYPE_KEY_TAKEN"}

    bad = await client.post(CONTENT_TYPES, json={"key": "Asset Type", "name": "x"}, headers=ALICE)
    assert bad.status_code == 422

    fetched = (await client.get(f"{CONTENT_TYPES}/{created['id']}", headers=ALICE)).json()
    assert fetched == created


async def test_category_and_item_type_create_and_search(client: httpx.AsyncClient) -> None:
    asset = await _content_type(client, ALICE, key="asset", name="Asset")
    piping = await _category(client, asset["id"], key="piping", name="Piping", applicableFor="item")
    assert piping["applicableFor"] == "item"

    bad = await client.post(
        CATEGORIES,
        json={"contentTypeId": asset["id"], "key": "bad", "name": "Bad", "applicableFor": "widget"},
        headers=ALICE,
    )
    assert bad.status_code == 422

    spool = await _item_type(client, piping["id"], key="pipe_spool", name="Pipe spool")
    assert spool["contentTypeId"] == asset["id"]

    by_type = await client.get(ITEM_TYPES, params={"contentTypeId": asset["id"]}, headers=ALICE)
    assert [it["id"] for it in by_type.json()["items"]] == [spool["id"]]
    assert (await client.get(ITEM_TYPES, params={"q": "SPOOL"}, headers=ALICE)).json()["items"]
    miss = await client.get(ITEM_TYPES, params={"q": "valve"}, headers=ALICE)
    assert miss.json()["items"] == []


async def test_delete_content_type_in_use_is_refused(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    asset = await _content_type(client, ALICE, key="asset", name="Asset")
    await _category(client, asset["id"], key="piping", name="Piping")

    response = await client.delete(f"{CONTENT_TYPES}/{asset['id']}", headers=ALICE)
    assert response.status_code == 409
    assert response.json() == {"code": "CONTENT_TYPE_IN_USE", "categories": 1}

    [(deleted_at,)] = await su_fetch(
        db, "SELECT deleted_at FROM content_types WHERE id = $1", asset["id"]
    )
    assert deleted_at is None


async def test_delete_category_in_use_is_refused(client: httpx.AsyncClient) -> None:
    asset = await _content_type(client, ALICE, key="asset", name="Asset")
    piping = await _category(client, asset["id"], key="piping", name="Piping")
    await _item_type(client, piping["id"], key="pipe_spool", name="Pipe spool")

    response = await client.delete(f"{CATEGORIES}/{piping['id']}", headers=ALICE)
    assert response.status_code == 409
    assert response.json() == {"code": "CATEGORY_IN_USE", "itemTypes": 1}


async def test_optimistic_version_on_update(client: httpx.AsyncClient) -> None:
    asset = await _content_type(client, ALICE, key="asset", name="Asset")
    piping = await _category(client, asset["id"], key="piping", name="Piping")
    spool = await _item_type(client, piping["id"], key="pipe_spool", name="Pipe spool")

    first = await client.patch(
        f"{ITEM_TYPES}/{spool['id']}", json={"name": "Spool", "syncVersion": 1}, headers=ALICE
    )
    assert first.status_code == 200
    assert first.json()["syncVersion"] == 2

    stale = await client.patch(
        f"{ITEM_TYPES}/{spool['id']}", json={"name": "Spool", "syncVersion": 1}, headers=ALICE
    )
    assert stale.status_code == 409
    body = stale.json()
    assert body["code"] == "VERSION_CONFLICT"
    assert body["current"]["name"] == "Spool"


async def test_reorder_content_types(client: httpx.AsyncClient) -> None:
    asset = await _content_type(client, ALICE, key="asset", name="Asset")
    staff = await _content_type(client, ALICE, key="staff", name="Staff")
    vehicle = await _content_type(client, ALICE, key="vehicle", name="Vehicle")

    reversed_ids = [vehicle["id"], staff["id"], asset["id"]]
    ordered = await client.put(f"{CONTENT_TYPES}/order", json={"ids": reversed_ids}, headers=ALICE)
    assert ordered.status_code == 200

    listed = (await client.get(CONTENT_TYPES, headers=ALICE)).json()["items"]
    assert [ct["id"] for ct in listed] == reversed_ids
    assert [ct["sortOrder"] for ct in listed] == [10, 20, 30]

    short = await client.put(
        f"{CONTENT_TYPES}/order", json={"ids": [vehicle["id"], staff["id"]]}, headers=ALICE
    )
    assert short.status_code == 422
    assert short.json()["code"] == "ORDER_MISMATCH"


# --- isolation and permissions ----------------------------------------------------------------


async def test_cross_tenant_is_404_and_never_listed(client: httpx.AsyncClient) -> None:
    asset = await _content_type(client, ALICE, key="asset", name="Asset")
    piping = await _category(client, asset["id"], key="piping", name="Piping")
    spool = await _item_type(client, piping["id"], key="pipe_spool", name="Pipe spool")

    assert (await client.get(f"{ITEM_TYPES}/{spool['id']}", headers=BOB)).status_code == 404

    stolen = await client.post(
        ITEM_TYPES, json={"categoryId": piping["id"], "key": "x", "name": "X"}, headers=BOB
    )
    assert stolen.status_code == 404

    assert (await client.get(CONTENT_TYPES, headers=BOB)).json() == {"items": []}


async def test_permissions_deny_by_level(
    client: httpx.AsyncClient, db: TenantDb, grants: GrantTable
) -> None:
    asset = await _content_type(client, ALICE, key="asset", name="Asset")
    piping = await _category(client, asset["id"], key="piping", name="Piping")

    from tests.conftest import ALICE_ID

    grants.by_user[ALICE_ID] = {"item_type.view"}
    before = (await su_fetch(db, "SELECT count(*) FROM item_types"))[0][0]
    denied = await client.post(
        ITEM_TYPES, json={"categoryId": piping["id"], "key": "x", "name": "X"}, headers=ALICE
    )
    assert denied.status_code == 403
    after = (await su_fetch(db, "SELECT count(*) FROM item_types"))[0][0]
    assert before == after

    grants.by_user[ALICE_ID] = {"item_type.view", "item_type.edit"}
    forbidden = await client.post(
        CONTENT_TYPES, json={"key": "staff", "name": "Staff"}, headers=ALICE
    )
    assert forbidden.status_code == 403


async def test_rls_and_grants_for_aip_app(client: httpx.AsyncClient, db: TenantDb) -> None:
    asset = await _content_type(client, ALICE, key="asset", name="Asset")
    await _category(client, asset["id"], key="piping", name="Piping")

    async with db.no_tenant() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM item_categories"))).scalar() == 0
    with pytest.raises(DBAPIError) as insert_denied:
        async with db.no_tenant() as conn:
            await conn.execute(
                text(
                    "INSERT INTO item_types (id, tenant_id, category_id, key, name) VALUES"
                    " (gen_random_uuid(), :t, gen_random_uuid(), 'x', 'x')"
                ),
                {"t": TENANT_A_ID},
            )
    assert getattr(insert_denied.value.orig, "sqlstate", None) == "42501"

    with pytest.raises(DBAPIError) as delete_denied:
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text("DELETE FROM content_types"))
    assert getattr(delete_denied.value.orig, "sqlstate", None) == "42501"


async def test_content_type_cap(client: httpx.AsyncClient, db: TenantDb) -> None:
    from .conftest import su_execute

    await su_execute(
        db,
        "INSERT INTO content_types (id, tenant_id, key, name)"
        f" SELECT gen_random_uuid(), '{TENANT_A_ID}', 'ct' || lpad(n::text, 3, '0'), 'CT ' || n"
        " FROM generate_series(1, 50) AS n",
    )
    response = await client.post(
        CONTENT_TYPES, json={"key": "one_more", "name": "One more"}, headers=ALICE
    )
    assert response.status_code == 409
    assert response.json() == {"code": "LIMIT_REACHED", "limit": 50}
