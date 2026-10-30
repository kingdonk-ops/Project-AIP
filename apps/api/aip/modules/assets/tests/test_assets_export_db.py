"""ASSETS-03 integration tests: ``GET /api/v1/assets/export.csv`` on real Postgres.

The export takes the list's filters and sort and streams the API's field names as headers
(ADR 0033), in keyset batches, refusing above the row cap with 422 ``EXPORT_TOO_LARGE``. The app
connects as ``aip_app`` (RLS on): tenant B's export never holds tenant A's rows.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.assets import service as service_module

from .conftest import ALICE, BOB, GrantTable, su_execute

ASSETS = "/api/v1/assets"
EXPORT = f"{ASSETS}/export.csv"
HEADER = "﻿internalTag,tagNumber,name,parentId,path,itemTypeId,itemTypeVersionId,updatedAt"


async def mk(
    client: httpx.AsyncClient, headers: dict[str, str], name: str, **body: Any
) -> dict[str, Any]:
    response = await client.post(ASSETS, json={"name": name, **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def csv_lines(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="assets.csv"'
    assert response.text.endswith("\r\n")
    return response.text.split("\r\n")[:-1]


async def seed_tree(client: httpx.AsyncClient) -> dict[str, Any]:
    """``Site A`` with 7 descendants (``Unit 1`` holding 3 pumps, 3 more units) and 3 elsewhere."""
    site = await mk(client, ALICE, "Site A")
    unit = await mk(client, ALICE, "Unit 1", parentId=site["id"])
    for n in range(1, 4):
        await mk(client, ALICE, f"Pump {n}", parentId=unit["id"], tagNumber=f"P-10{n}")
    for n in range(2, 5):
        await mk(client, ALICE, f"Unit {n}", parentId=site["id"])
    other = await mk(client, ALICE, "Site B")
    await mk(client, ALICE, "Unit 9", parentId=other["id"])
    await mk(client, ALICE, "Site C")
    return {"site": site, "unit": unit}


async def test_export_under_a_subtree_holds_its_rows_with_ancestor_paths(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "_EXPORT_BATCH", 3)  # 7 rows over three batches
    tree = await seed_tree(client)

    lines = csv_lines(await client.get(EXPORT, params={"under": tree["site"]["id"]}, headers=ALICE))
    assert lines[0] == HEADER
    assert len(lines) == 1 + 7
    rows = [line.split(",") for line in lines[1:]]
    names = [row[2] for row in rows]
    assert names == sorted(names)  # the list's default sort (name), across batches
    pump = next(row for row in rows if row[2] == "Pump 1")
    assert pump[0].startswith("AT-")
    assert pump[1] == "P-101"
    assert pump[3] == tree["unit"]["id"]
    assert pump[4] == "Site A > Unit 1"
    assert pump[5] == pump[6] == ""  # untyped
    assert pump[7].endswith("Z")  # UTC ISO 8601
    unit = next(row for row in rows if row[2] == "Unit 1")
    assert unit[4] == "Site A"

    # The same query as the list: the list's rows are exactly the file's rows.
    listed = (
        await client.get(
            ASSETS, params={"under": tree["site"]["id"], "sort": "-name"}, headers=ALICE
        )
    ).json()
    exported = csv_lines(
        await client.get(
            EXPORT, params={"under": tree["site"]["id"], "sort": "-name"}, headers=ALICE
        )
    )
    assert [line.split(",")[2] for line in exported[1:]] == [i["name"] for i in listed["items"]]

    everything = csv_lines(await client.get(EXPORT, headers=ALICE))
    assert len(everything) == 1 + 11
    searched = csv_lines(await client.get(EXPORT, params={"q": "pump"}, headers=ALICE))
    assert len(searched) == 1 + 3
    roots = csv_lines(await client.get(EXPORT, params={"parentId": "root"}, headers=ALICE))
    assert [line.split(",")[2] for line in roots[1:]] == ["Site A", "Site B", "Site C"]


async def test_export_neutralises_formulas(client: httpx.AsyncClient) -> None:
    await mk(client, ALICE, '=HYPERLINK("x")')
    lines = csv_lines(await client.get(EXPORT, headers=ALICE))
    assert lines[1].split(",", 2)[2].startswith('"\'=HYPERLINK(""x"")",')


async def test_export_needs_asset_view(client: httpx.AsyncClient, grants: GrantTable) -> None:
    grants.by_user[ALICE_ID] = {"asset.create"}
    assert (await client.get(EXPORT, headers=ALICE)).status_code == 403


async def test_another_tenant_exports_the_header_only(client: httpx.AsyncClient) -> None:
    tree = await seed_tree(client)
    assert csv_lines(await client.get(EXPORT, headers=BOB)) == [HEADER]
    under = await client.get(EXPORT, params={"under": tree["site"]["id"]}, headers=BOB)
    assert csv_lines(under) == [HEADER]


async def test_export_refuses_more_rows_than_the_cap(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    # 10,001 root assets, seeded as the superuser: each path is its id's hex (ck_assets_path_leaf).
    await su_execute(
        db,
        "INSERT INTO assets (id, tenant_id, path, internal_tag, name, sort_order)"
        f" SELECT u, '{TENANT_A_ID}', text2ltree(replace(u::text, '-', '')),"
        " 'AT-' || upper(replace(u::text, '-', '')), 'Bulk ' || n, n"
        " FROM (SELECT gen_random_uuid() AS u, n FROM generate_series(1, 10001) AS n) AS s",
    )
    refused = await client.get(EXPORT, headers=ALICE)
    assert refused.status_code == 422
    assert refused.json() == {"code": "EXPORT_TOO_LARGE", "limit": 10_000}
    narrowed = csv_lines(await client.get(EXPORT, params={"q": "Bulk 10001"}, headers=ALICE))
    assert len(narrowed) == 1 + 1
