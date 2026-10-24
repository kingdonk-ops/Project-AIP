"""ASSETS-01 integration tests: the API and the ``assets`` table on real Postgres.

The app connects as ``aip_app`` (RLS on). Users come from the AUTH_TEST_STUB principal header;
permissions from the ``grants`` fixture. Testcontainers (or ``AIP_TEST_DATABASE_URL``) provides the
database, migrated, with the two fixture tenants.
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
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.assets import service as service_module
from aip.modules.assets.api import AssetsApi
from aip.modules.assets.schemas import AssetCreate
from aip.modules.assets.service import AssetService
from aip.platform.context import RequestContext, use_context
from aip.platform.db.session import with_tenant

from .conftest import ALICE, BOB, GrantTable, su_execute, su_fetch

ASSETS = "/api/v1/assets"


async def create(client: httpx.AsyncClient, headers: dict[str, str], **body: Any) -> httpx.Response:
    return await client.post(ASSETS, json=body, headers=headers)


async def mk(
    client: httpx.AsyncClient, headers: dict[str, str], name: str, **body: Any
) -> dict[str, Any]:
    response = await create(client, headers, name=name, **body)
    assert response.status_code == 201, response.text
    return response.json()


async def events(db: TenantDb, name: str) -> list[tuple[Any, ...]]:
    rows = await su_fetch(
        db,
        "SELECT tenant_id, actor_id, aggregate_id, payload FROM domain_events"
        " WHERE event_name = $1 ORDER BY occurred_at",
        name,
    )
    return [(*row[:3], json.loads(row[3])) for row in rows]  # asyncpg returns jsonb as text


async def count_events(db: TenantDb, name: str) -> int:
    (row,) = await su_fetch(db, "SELECT count(*) FROM domain_events WHERE event_name = $1", name)
    return int(row[0])


# --- the tree -----------------------------------------------------------------------------------


async def test_building_a_three_level_tree_emits_one_created_event_each(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    site = await mk(client, ALICE, "Site A")
    unit = await mk(client, ALICE, "Unit 1", parentId=site["id"])
    pump = await mk(client, ALICE, "Pump", parentId=unit["id"], tagNumber="P-101")

    labels = pump["path"].split(".")
    assert len(labels) == 3
    assert labels[-1] == UUID(pump["id"]).hex
    assert labels[0] == UUID(site["id"]).hex
    assert pump["tagNumber"] == "P-101"
    assert pump["internalTag"].startswith("AT-")
    assert await count_events(db, "asset.created") == 3

    created = await events(db, "asset.created")
    assert created[0][:3] == (TENANT_A_ID, ALICE_ID, UUID(site["id"]))
    assert created[0][3]["parentId"] is None
    assert created[1][3]["parentId"] == unit["parentId"] == site["id"]


async def test_list_filters_by_parent_and_subtree(client: httpx.AsyncClient) -> None:
    site = await mk(client, ALICE, "Site A")
    await mk(client, ALICE, "Unit 1", parentId=site["id"])
    pump = await mk(client, ALICE, "Pump", parentId=(await _first_child(client, site["id"]))["id"])

    roots = (await client.get(ASSETS, params={"parentId": "root"}, headers=ALICE)).json()
    assert [i["name"] for i in roots["items"]] == ["Site A"]
    assert roots["items"][0]["childCount"] == 1

    under = (await client.get(ASSETS, params={"under": site["id"]}, headers=ALICE)).json()
    assert sorted(i["name"] for i in under["items"]) == ["Pump", "Unit 1"]
    assert pump["name"] == "Pump"


async def _first_child(client: httpx.AsyncClient, parent_id: str) -> dict[str, Any]:
    page = (await client.get(ASSETS, params={"parentId": parent_id}, headers=ALICE)).json()
    return page["items"][0]


# --- Tag Number ---------------------------------------------------------------------------------


async def test_tag_number_is_unique_among_live_assets_ignoring_case(
    client: httpx.AsyncClient,
) -> None:
    first = await mk(client, ALICE, "Pump", tagNumber="P-101")
    clash = await create(client, ALICE, name="Pump 2", tagNumber="p-101")
    assert clash.status_code == 409
    assert clash.json() == {
        "code": "TAG_NUMBER_IN_USE",
        "assetId": first["id"],
        "internalTag": first["internalTag"],
    }

    assert (
        await client.delete(f"{ASSETS}/{first['id']}", params={"syncVersion": 1}, headers=ALICE)
    ).status_code == 204
    # The Tag Number is free again at once (the unique index is partial on live rows).
    assert (await create(client, ALICE, name="Pump 2", tagNumber="p-101")).status_code == 201


# --- immutable internal tag ---------------------------------------------------------------------


async def test_internal_tag_is_immutable_in_the_api_and_the_database(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    pump = await mk(client, ALICE, "Pump")
    patch = {"syncVersion": 1, "internalTag": "AT-0000-0000-0000"}
    assert (
        await client.patch(f"{ASSETS}/{pump['id']}", json=patch, headers=ALICE)
    ).status_code == 422

    with pytest.raises(Exception, match="internal_tag is immutable"):
        await su_execute(db, f"UPDATE assets SET internal_tag = 'x' WHERE id = '{pump['id']}'")


# --- move ---------------------------------------------------------------------------------------


async def test_move_reparents_the_whole_subtree_in_one_event(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    site_a = await mk(client, ALICE, "Site A")
    unit = await mk(client, ALICE, "Unit 1", parentId=site_a["id"])
    await mk(client, ALICE, "Pump", parentId=unit["id"])
    site_b = await mk(client, ALICE, "Site B")

    move = {"syncVersion": unit["syncVersion"], "parentId": site_b["id"]}
    moved = await client.post(f"{ASSETS}/{unit['id']}/move", json=move, headers=ALICE)
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["parentId"] == site_b["id"]

    (event,) = await events(db, "asset.moved")
    assert event[3]["movedCount"] == 2
    assert event[3]["fromParentId"] == site_a["id"]
    assert event[3]["toParentId"] == site_b["id"]

    rows = await su_fetch(
        db, "SELECT name, path::text FROM assets WHERE tenant_id = $1 ORDER BY path", TENANT_A_ID
    )
    paths = {name: path for name, path in rows}
    b_label = UUID(site_b["id"]).hex
    assert paths["Unit 1"].startswith(b_label + ".")
    assert paths["Pump"].startswith(b_label + ".")


async def test_a_cycle_move_writes_nothing(client: httpx.AsyncClient, db: TenantDb) -> None:
    site_b = await mk(client, ALICE, "Site B")
    unit = await mk(client, ALICE, "Unit 1", parentId=site_b["id"])
    pump = await mk(client, ALICE, "Pump", parentId=unit["id"])
    before = await su_fetch(
        db, "SELECT id, path::text FROM assets WHERE tenant_id = $1", TENANT_A_ID
    )

    move = {"syncVersion": site_b["syncVersion"], "parentId": pump["id"]}
    cycle = await client.post(f"{ASSETS}/{site_b['id']}/move", json=move, headers=ALICE)
    assert (cycle.status_code, cycle.json()) == (422, {"code": "PATH_CYCLE"})

    after = await su_fetch(
        db, "SELECT id, path::text FROM assets WHERE tenant_id = $1", TENANT_A_ID
    )
    assert sorted(map(tuple, before)) == sorted(map(tuple, after))
    assert await count_events(db, "asset.moved") == 0


async def test_move_rejects_a_foreign_parent_and_a_stale_version(
    client: httpx.AsyncClient,
) -> None:
    tenant_b_asset = await mk(client, BOB, "B Root")
    node = await mk(client, ALICE, "Node")

    foreign = await client.post(
        f"{ASSETS}/{node['id']}/move",
        json={"syncVersion": 1, "parentId": tenant_b_asset["id"]},
        headers=ALICE,
    )
    assert (foreign.status_code, foreign.json()) == (
        422,
        {"code": "PARENT_NOT_FOUND", "field": "parentId"},
    )

    stale = await client.post(
        f"{ASSETS}/{node['id']}/move", json={"syncVersion": 9, "parentId": None}, headers=ALICE
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"


# --- depth --------------------------------------------------------------------------------------


async def _chain(client: httpx.AsyncClient, depth: int) -> list[dict[str, Any]]:
    nodes = [await mk(client, ALICE, "L1")]
    for level in range(2, depth + 1):
        nodes.append(await mk(client, ALICE, f"L{level}", parentId=nodes[-1]["id"]))
    return nodes


async def test_the_tree_cannot_exceed_fifteen_levels(client: httpx.AsyncClient) -> None:
    chain = await _chain(client, 15)
    too_deep = await create(client, ALICE, name="L16", parentId=chain[-1]["id"])
    assert (too_deep.status_code, too_deep.json()) == (422, {"code": "ASSET_TREE_TOO_DEEP"})

    # A 2-level subtree moved under the 14th level would land its leaf at level 16.
    root = await mk(client, ALICE, "R")
    await mk(client, ALICE, "RC", parentId=root["id"])
    move = {"syncVersion": root["syncVersion"], "parentId": chain[13]["id"]}
    moved = await client.post(f"{ASSETS}/{root['id']}/move", json=move, headers=ALICE)
    assert (moved.status_code, moved.json()) == (422, {"code": "ASSET_TREE_TOO_DEEP"})


# --- concurrency --------------------------------------------------------------------------------


async def test_two_opposing_moves_cannot_both_win(client: httpx.AsyncClient, db: TenantDb) -> None:
    x = await mk(client, ALICE, "X")
    y = await mk(client, ALICE, "Y")

    results = await asyncio.gather(
        client.post(
            f"{ASSETS}/{x['id']}/move", json={"syncVersion": 1, "parentId": y["id"]}, headers=ALICE
        ),
        client.post(
            f"{ASSETS}/{y['id']}/move", json={"syncVersion": 1, "parentId": x["id"]}, headers=ALICE
        ),
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 422]
    cycle = next(r for r in results if r.status_code == 422)
    assert cycle.json() == {"code": "PATH_CYCLE"}

    rows = await su_fetch(db, "SELECT path::text FROM assets WHERE tenant_id = $1", TENANT_A_ID)
    for (path,) in rows:
        labels = path.split(".")
        assert len(labels) == len(set(labels))  # no label appears twice


# --- delete -------------------------------------------------------------------------------------


async def test_delete_refuses_a_parent_with_live_children_and_aip_app_cannot_hard_delete(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    site_b = await mk(client, ALICE, "Site B")
    await mk(client, ALICE, "Unit 1", parentId=site_b["id"])

    blocked = await client.delete(
        f"{ASSETS}/{site_b['id']}", params={"syncVersion": 1}, headers=ALICE
    )
    assert (blocked.status_code, blocked.json()) == (
        409,
        {"code": "ASSET_HAS_CHILDREN", "childCount": 1},
    )

    with pytest.raises(DBAPIError) as caught:
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text("DELETE FROM assets"))
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"


async def test_soft_delete_assets_batch_rollback(client: httpx.AsyncClient, db: TenantDb) -> None:
    site = await mk(client, ALICE, "Site A")
    unit = await mk(client, ALICE, "Unit 1", parentId=site["id"])
    pump = await mk(client, ALICE, "Pump", parentId=unit["id"])
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id="test-batch", actor_id=ALICE_ID)

    with use_context(ctx):
        async with with_tenant(ctx) as conn:
            count = await AssetsApi().soft_delete_assets(
                conn, [UUID(unit["id"]), UUID(pump["id"])], reason="import rollback"
            )
    assert count == 2
    deleted = await events(db, "asset.deleted")
    assert len(deleted) == 2
    assert all(e[3]["reason"] == "import rollback" for e in deleted)

    # Deleting Unit 1 alone while Pump is live is refused: Pump is a live child outside the set.
    site2 = await mk(client, ALICE, "Site C")
    unit2 = await mk(client, ALICE, "Unit 2", parentId=site2["id"])
    await mk(client, ALICE, "Pump 2", parentId=unit2["id"])
    with use_context(ctx), pytest.raises(Exception, match="ASSET_HAS_CHILDREN"):
        async with with_tenant(ctx) as conn:
            await AssetsApi().soft_delete_assets(conn, [UUID(unit2["id"])], reason="x")


# --- idempotency --------------------------------------------------------------------------------


async def test_client_generated_id_replays_once(client: httpx.AsyncClient, db: TenantDb) -> None:
    cgid = "0192f3c4-0000-7000-8000-0000000000aa"
    first = await create(client, ALICE, name="Pump", clientGeneratedId=cgid)
    assert first.status_code == 201, first.text
    again = await create(client, ALICE, name="Pump (ignored)", clientGeneratedId=cgid)
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert await count_events(db, "asset.created") == 1


# --- the outbox shares the transaction ----------------------------------------------------------


async def test_a_rolled_back_create_leaves_no_asset_and_no_event(
    app: object, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_emit = service_module.emit

    class RollbackError(Exception):
        pass

    async def emit_then_fail(*args: Any, **kwargs: Any) -> UUID:
        await real_emit(*args, **kwargs)
        raise RollbackError

    monkeypatch.setattr(service_module, "emit", emit_then_fail)
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id="test-rollback", actor_id=ALICE_ID)
    with use_context(ctx), pytest.raises(RollbackError):
        await AssetService().create(AssetCreate(name="Site A"))
    assert await su_fetch(db, "SELECT count(*) FROM assets") == [(0,)]
    assert await su_fetch(db, "SELECT count(*) FROM domain_events") == [(0,)]


# --- tenancy ------------------------------------------------------------------------------------


async def test_another_tenants_asset_is_404_everywhere_and_never_listed(
    client: httpx.AsyncClient,
) -> None:
    asset_id = (await mk(client, ALICE, "Site A"))["id"]
    assert (await client.get(f"{ASSETS}/{asset_id}", headers=ALICE)).status_code == 200

    assert (await client.get(f"{ASSETS}/{asset_id}", headers=BOB)).status_code == 404
    patch = {"syncVersion": 1, "name": "Mine"}
    assert (await client.patch(f"{ASSETS}/{asset_id}", json=patch, headers=BOB)).status_code == 404
    move = {"syncVersion": 1, "parentId": None}
    assert (
        await client.post(f"{ASSETS}/{asset_id}/move", json=move, headers=BOB)
    ).status_code == 404
    assert (await client.get(ASSETS, headers=BOB)).json() == {"items": [], "nextCursor": None}


# --- permissions --------------------------------------------------------------------------------


async def test_without_asset_create_nothing_is_written(
    client: httpx.AsyncClient, db: TenantDb, grants: GrantTable
) -> None:
    grants.by_user[ALICE_ID].discard("asset.create")
    denied = await create(client, ALICE, name="Site A")
    assert denied.status_code == 403
    assert denied.json() == {"code": "FORBIDDEN", "permission": "asset.create"}
    assert await su_fetch(db, "SELECT count(*) FROM assets") == [(0,)]
    assert await su_fetch(db, "SELECT count(*) FROM domain_events") == [(0,)]


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    [
        ("GET", ASSETS, "asset.view"),
        ("GET", f"{ASSETS}/{TENANT_A_ID}", "asset.view"),
        ("POST", ASSETS, "asset.create"),
        ("PATCH", f"{ASSETS}/{TENANT_A_ID}", "asset.update"),
        ("POST", f"{ASSETS}/{TENANT_A_ID}/move", "asset.move"),
        ("DELETE", f"{ASSETS}/{TENANT_A_ID}?syncVersion=1", "asset.delete"),
    ],
)
async def test_every_route_is_denied_without_its_permission(
    client: httpx.AsyncClient, grants: GrantTable, method: str, path: str, permission: str
) -> None:
    grants.by_user[ALICE_ID] = set()
    body: dict[str, Any] | None
    if method == "POST" and path.endswith("/move"):
        body = {"syncVersion": 1, "parentId": None}
    elif method == "PATCH":
        body = {"syncVersion": 1, "name": "x"}
    elif method == "POST":
        body = {"name": "x"}
    else:
        body = None
    response = await client.request(method, path, json=body, headers=ALICE)
    assert response.status_code == 403
    assert response.json()["permission"] == permission
    assert (await client.request(method, path, json=body)).status_code == 401


# --- listing ------------------------------------------------------------------------------------


async def test_root_paging_has_no_gaps_and_rejects_a_tampered_cursor(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await su_execute(
        db,
        "INSERT INTO assets (id, tenant_id, path, internal_tag, name)"
        f" SELECT g.id, '{TENANT_A_ID}', replace(g.id::text, '-', '')::ltree,"
        " 'IT-' || lpad(n::text, 4, '0'), 'A' || lpad(n::text, 3, '0')"
        " FROM (SELECT gen_random_uuid() AS id, n FROM generate_series(1, 120) AS n) g",
    )
    seen: list[str] = []
    sizes: list[int] = []
    params: dict[str, Any] = {"limit": 50, "sort": "name", "parentId": "root"}
    while True:
        page = (await client.get(ASSETS, params=params, headers=ALICE)).json()
        sizes.append(len(page["items"]))
        seen += [a["name"] for a in page["items"]]
        if page["nextCursor"] is None:
            break
        params["cursor"] = page["nextCursor"]
    assert sizes == [50, 50, 20]
    assert seen == [f"A{n:03d}" for n in range(1, 121)]

    descending = (
        await client.get(
            ASSETS, params={"sort": "-name", "parentId": "root", "limit": 200}, headers=ALICE
        )
    ).json()
    assert [a["name"] for a in descending["items"]][:3] == ["A120", "A119", "A118"]

    tampered = await client.get(
        ASSETS, params={"cursor": "e30.AAAA", "parentId": "root"}, headers=ALICE
    )
    assert tampered.status_code == 422
    assert tampered.json() == {"code": "INVALID_CURSOR", "field": "cursor"}
