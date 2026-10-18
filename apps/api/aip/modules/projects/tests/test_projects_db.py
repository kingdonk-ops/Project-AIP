"""PROJECTS-01 integration tests: the API and the tables on real Postgres.

The app connects as ``aip_app`` (RLS on). Users come from the AUTH_TEST_STUB principal header;
permissions from the ``grants`` fixture.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.projects import service as service_module
from aip.modules.projects.schemas import ProjectCreate
from aip.modules.projects.service import ProjectService
from aip.platform.context import RequestContext, use_context

from .conftest import ALICE, BOB, GrantTable, su_execute, su_fetch

PROJECTS = "/api/v1/projects"
SITES = "/api/v1/sites"


async def create(client: httpx.AsyncClient, headers: dict[str, str], **body: Any) -> httpx.Response:
    return await client.post(PROJECTS, json={"name": "Ichthys", **body}, headers=headers)


async def events(db: TenantDb, name: str) -> list[tuple[Any, ...]]:
    """All tenants' ``name`` events as (tenant, actor, aggregate, payload), oldest first."""
    rows = await su_fetch(
        db,
        "SELECT tenant_id, actor_id, aggregate_id, payload FROM domain_events"
        " WHERE event_name = $1 ORDER BY occurred_at",
        name,
    )
    return [(*row[:3], json.loads(row[3])) for row in rows]  # asyncpg returns jsonb as text


# --- tenancy and uniqueness -------------------------------------------------------------------


async def test_codes_are_unique_per_tenant_ignoring_case(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    first = await create(client, ALICE, code="L592")
    assert first.status_code == 201, first.text
    project = first.json()
    assert (project["code"], project["status"], project["syncVersion"]) == ("L592", "draft", 1)

    again = await create(client, ALICE, code="l592")
    assert again.status_code == 409
    assert again.json() == {"code": "PROJECT_CODE_TAKEN"}

    assert (await create(client, BOB, code="L592")).status_code == 201

    event, _tenant_b = await events(db, "project.created")
    assert event[:3] == (TENANT_A_ID, ALICE_ID, UUID(project["id"]))
    assert event[3] == {
        "projectId": project["id"],
        "code": "L592",
        "status": "draft",
        "before": None,
        "after": None,
    }


async def test_another_tenants_project_is_404_and_never_listed(client: httpx.AsyncClient) -> None:
    project_id = (await create(client, ALICE, code="L592")).json()["id"]
    assert (await client.get(f"{PROJECTS}/{project_id}", headers=ALICE)).status_code == 200

    response = await client.get(f"{PROJECTS}/{project_id}", headers=BOB)
    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND"}
    patch = {"syncVersion": 1, "name": "Mine now"}
    assert (
        await client.patch(f"{PROJECTS}/{project_id}", json=patch, headers=BOB)
    ).status_code == 404

    listed = (await client.get(PROJECTS, headers=BOB)).json()
    assert listed == {"items": [], "nextCursor": None}


async def test_rls_fails_closed_without_a_tenant(client: httpx.AsyncClient, db: TenantDb) -> None:
    assert (await create(client, ALICE, code="L592")).status_code == 201
    async with db.no_tenant() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM projects"))).scalar() == 0
        assert (await conn.execute(text("SELECT count(*) FROM sites"))).scalar() == 0
    with pytest.raises(DBAPIError) as caught:
        async with db.no_tenant() as conn:
            await conn.execute(
                text(
                    "INSERT INTO projects (id, tenant_id, code, name) VALUES"
                    " (gen_random_uuid(), :t, 'X1', 'x')"
                ),
                {"t": TENANT_A_ID},
            )
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"


async def test_aip_app_cannot_hard_delete(db: TenantDb, client: httpx.AsyncClient) -> None:
    assert (await create(client, ALICE, code="L592")).status_code == 201
    for table in ("projects", "sites"):
        with pytest.raises(DBAPIError) as caught:
            async with db.with_tenant(TENANT_A_ID) as conn:
                await conn.execute(text(f"DELETE FROM {table}"))
        assert getattr(caught.value.orig, "sqlstate", None) == "42501"


# --- listing ----------------------------------------------------------------------------------


async def test_cursor_pages_have_no_gaps_or_duplicates(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await su_execute(
        db,
        "INSERT INTO projects (id, tenant_id, code, name)"
        f" SELECT gen_random_uuid(), '{TENANT_A_ID}', 'P' || lpad(n::text, 3, '0'), 'Project ' || n"
        " FROM generate_series(1, 120) AS n",
    )
    seen: list[str] = []
    sizes: list[int] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        page = (await client.get(PROJECTS, params=params, headers=ALICE)).json()
        sizes.append(len(page["items"]))
        seen += [p["code"] for p in page["items"]]
        cursor = page["nextCursor"]
        if cursor is None:
            break
    assert sizes == [50, 50, 20]
    assert seen == [f"P{n:03d}" for n in range(1, 121)]


async def seed_projects(
    db: TenantDb, count: int, *, status: str = "draft", prefix: str = "P"
) -> None:
    await su_execute(
        db,
        "INSERT INTO projects (id, tenant_id, code, name, status)"
        f" SELECT gen_random_uuid(), '{TENANT_A_ID}', '{prefix}' || lpad(n::text, 3, '0'),"
        f" 'Project ' || n, '{status}' FROM generate_series(1, {count}) AS n",
    )


async def test_descending_sort_pages_without_gaps_and_keeps_its_direction(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await seed_projects(db, 120)
    seen: list[str] = []
    sizes: list[int] = []
    params: dict[str, Any] = {"limit": 50, "sort": "-code"}
    while True:
        response = await client.get(PROJECTS, params=params, headers=ALICE)
        assert response.status_code == 200, response.text
        page = response.json()
        sizes.append(len(page["items"]))
        seen += [p["code"] for p in page["items"]]
        if page["nextCursor"] is None:
            break
        params["cursor"] = page["nextCursor"]
        # A cursor is bound to its direction: the same cursor with the opposite one is refused.
        flipped = await client.get(PROJECTS, params={**params, "sort": "code"}, headers=ALICE)
        assert flipped.status_code == 422
        assert flipped.json() == {"code": "INVALID_CURSOR", "field": "cursor"}
    assert sizes == [50, 50, 20]
    assert seen == [f"P{n:03d}" for n in range(120, 0, -1)]
    assert (await client.get(PROJECTS, params={"sort": "-site"}, headers=ALICE)).status_code == 422


# --- CSV export -------------------------------------------------------------------------------

EXPORT = f"{PROJECTS}/export.csv"
HEADER = "﻿code,name,status,siteId,region,updatedAt"


def csv_lines(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="projects.csv"'
    assert response.text.endswith("\r\n")
    return response.text.split("\r\n")[:-1]


async def test_export_has_the_filtered_rows_the_caller_sees(
    client: httpx.AsyncClient, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "_EXPORT_BATCH", 3)  # 7 rows over three batches
    await seed_projects(db, 7, status="active", prefix="A")
    await seed_projects(db, 3, status="draft", prefix="D")
    await create(client, BOB, code="A999", status="active")  # tenant B's: never exported to A

    lines = csv_lines(await client.get(EXPORT, params={"status": "active"}, headers=ALICE))
    assert len(lines) == 1 + 7
    assert lines[0] == HEADER
    assert [line.split(",")[0] for line in lines[1:]] == [f"A{n:03d}" for n in range(1, 8)]
    assert lines[1].split(",")[1:4] == ["Project 1", "active", ""]

    descending = csv_lines(
        await client.get(EXPORT, params={"status": "active", "sort": "-code"}, headers=ALICE)
    )
    assert [line.split(",")[0] for line in descending[1:]] == [f"A{n:03d}" for n in range(7, 0, -1)]
    searched = csv_lines(await client.get(EXPORT, params={"q": "d00"}, headers=ALICE))
    assert len(searched) == 1 + 3
    assert csv_lines(await client.get(EXPORT, params={"q": "A999"}, headers=ALICE)) == [HEADER]


async def test_export_neutralises_formulas(client: httpx.AsyncClient) -> None:
    await create(client, ALICE, code="F1", name='=HYPERLINK("x")')
    lines = csv_lines(await client.get(EXPORT, headers=ALICE))
    assert lines[1].startswith('F1,"\'=HYPERLINK(""x"")",draft,')


async def test_export_needs_project_view(client: httpx.AsyncClient, grants: GrantTable) -> None:
    grants.by_user[ALICE_ID] = {"project.create"}
    assert (await client.get(EXPORT, headers=ALICE)).status_code == 403


async def test_export_refuses_more_rows_than_the_cap(
    client: httpx.AsyncClient, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "EXPORT_MAX_ROWS", 5)
    await seed_projects(db, 6)
    refused = await client.get(EXPORT, headers=ALICE)
    assert refused.status_code == 422
    assert refused.json() == {"code": "EXPORT_TOO_LARGE", "limit": 5}
    assert len(csv_lines(await client.get(EXPORT, params={"q": "P001"}, headers=ALICE))) == 1 + 1


async def test_list_filters_sorts_and_rejects_bad_cursors(client: httpx.AsyncClient) -> None:
    site = (
        await client.post(SITES, json={"code": "KIPS", "name": "Ichthys"}, headers=ALICE)
    ).json()
    await create(client, ALICE, code="A1", name="Zulu", siteId=site["id"])
    await create(client, ALICE, code="B2", name="Alpha", status="active")
    await create(client, ALICE, code="C3", name="Mike")

    async def codes(**params: Any) -> list[str]:
        response = await client.get(PROJECTS, params=params, headers=ALICE)
        assert response.status_code == 200, response.text
        return [p["code"] for p in response.json()["items"]]

    assert await codes() == ["A1", "B2", "C3"]
    assert await codes(sort="name") == ["B2", "C3", "A1"]
    assert await codes(sort="-name") == ["A1", "C3", "B2"]
    assert await codes(sort="updated_at") == ["A1", "B2", "C3"]
    assert await codes(sort="-updated_at") == ["C3", "B2", "A1"]
    assert await codes(status="active") == ["B2"]
    assert await codes(status=["active", "draft"]) == ["A1", "B2", "C3"]
    assert await codes(siteId=site["id"]) == ["A1"]
    assert await codes(q="ik") == ["C3"]
    assert await codes(q="%") == []

    page = (await client.get(PROJECTS, params={"limit": 1}, headers=ALICE)).json()
    by_name = await client.get(
        PROJECTS, params={"cursor": page["nextCursor"], "sort": "name"}, headers=ALICE
    )
    assert by_name.status_code == 422
    assert by_name.json() == {"code": "INVALID_CURSOR", "field": "cursor"}
    forged = await client.get(PROJECTS, params={"cursor": "e30.AAAA"}, headers=ALICE)
    assert forged.status_code == 422
    assert (await client.get(PROJECTS, params={"limit": 201}, headers=ALICE)).status_code == 422


# --- updates ----------------------------------------------------------------------------------


async def test_a_stale_sync_version_is_409_with_the_current_row(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    project_id = (await create(client, ALICE, code="L592")).json()["id"]
    url = f"{PROJECTS}/{project_id}"
    renamed = await client.patch(
        url, json={"syncVersion": 1, "name": "Ichthys KIPS"}, headers=ALICE
    )
    assert renamed.status_code == 200
    assert renamed.json()["syncVersion"] == 2

    stale = await client.patch(url, json={"syncVersion": 1, "name": "Other"}, headers=ALICE)
    assert stale.status_code == 409
    body = stale.json()
    assert body["code"] == "VERSION_CONFLICT"
    assert (body["current"]["syncVersion"], body["current"]["name"]) == (2, "Ichthys KIPS")

    (updated,) = await events(db, "project.updated")
    assert updated[3]["before"] == {"name": "Ichthys"}
    assert updated[3]["after"] == {"name": "Ichthys KIPS"}


async def test_lifecycle_moves_forward_and_archive_needs_its_own_permission(
    client: httpx.AsyncClient, db: TenantDb, grants: GrantTable
) -> None:
    project_id = (await create(client, ALICE, code="L592")).json()["id"]
    url = f"{PROJECTS}/{project_id}"

    async def move(status: str, version: int) -> httpx.Response:
        return await client.patch(
            url, json={"syncVersion": version, "status": status}, headers=ALICE
        )

    skipped = await move("archived", 1)
    assert skipped.status_code == 409
    assert skipped.json()["code"] == "INVALID_STATUS_TRANSITION"
    assert (await move("active", 1)).status_code == 200
    assert (await move("closing", 2)).status_code == 200

    grants.by_user[ALICE_ID].discard("project.archive")
    denied = await move("archived", 3)
    assert denied.status_code == 403
    assert denied.json() == {"code": "FORBIDDEN", "permission": "project.archive"}

    grants.by_user[ALICE_ID].add("project.archive")
    archived = await move("archived", 3)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    assert archived.json()["closedAt"] is not None
    assert len(await events(db, "project.archived")) == 1
    assert (await move("active", 4)).status_code == 409  # archived is final


async def test_validation_errors_carry_field_paths(client: httpx.AsyncClient) -> None:
    response = await create(client, ALICE, code="ab cd", currency="XXX")
    assert response.status_code == 422
    locs = sorted(tuple(e["loc"]) for e in response.json()["detail"])
    assert locs == [("body", "code"), ("body", "currency")]

    region = await create(client, ALICE, code="L592", region="mars-1")
    assert region.status_code == 422
    assert region.json() == {"code": "REGION_UNKNOWN", "field": "region"}
    assert (await create(client, ALICE, code="L593", region="ap-southeast-2")).status_code == 201

    ghost_site = await create(client, ALICE, code="L594", siteId=str(TENANT_B_ID))
    assert ghost_site.json() == {"code": "SITE_NOT_FOUND", "field": "siteId"}


# --- permissions ------------------------------------------------------------------------------


async def test_without_project_create_nothing_is_written(
    client: httpx.AsyncClient, db: TenantDb, grants: GrantTable
) -> None:
    grants.by_user[ALICE_ID].discard("project.create")
    response = await create(client, ALICE, code="L592")
    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "permission": "project.create"}
    assert await su_fetch(db, "SELECT count(*) FROM projects") == [(0,)]
    assert await su_fetch(db, "SELECT count(*) FROM domain_events") == [(0,)]


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    [
        ("GET", PROJECTS, "project.view"),
        ("GET", f"{PROJECTS}/{TENANT_A_ID}", "project.view"),
        ("PATCH", f"{PROJECTS}/{TENANT_A_ID}", "project.update"),
        ("GET", SITES, "site.view"),
        ("GET", f"{SITES}/{TENANT_A_ID}", "site.view"),
        ("POST", SITES, "site.manage"),
        ("PATCH", f"{SITES}/{TENANT_A_ID}", "site.manage"),
        ("DELETE", f"{SITES}/{TENANT_A_ID}", "site.manage"),
    ],
)
async def test_every_route_is_denied_without_its_permission(
    client: httpx.AsyncClient, grants: GrantTable, method: str, path: str, permission: str
) -> None:
    grants.by_user[ALICE_ID] = set()
    body = {"syncVersion": 1} if method == "PATCH" else {"code": "S1", "name": "Site"}
    json_body = body if method in ("POST", "PATCH") else None
    response = await client.request(method, path, json=json_body, headers=ALICE)
    assert response.status_code == 403
    assert response.json()["permission"] == permission
    anonymous = await client.request(method, path, json=json_body)
    assert anonymous.status_code == 401


# --- the outbox shares the transaction --------------------------------------------------------


async def test_a_rolled_back_create_leaves_no_project_and_no_event(
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
        await ProjectService().create(ProjectCreate(code="L592", name="Ichthys"))
    assert await su_fetch(db, "SELECT count(*) FROM projects") == [(0,)]
    assert await su_fetch(db, "SELECT count(*) FROM domain_events") == [(0,)]


# --- sites ------------------------------------------------------------------------------------


async def test_sites_crud_and_a_site_in_use_cannot_be_deleted(client: httpx.AsyncClient) -> None:
    created = await client.post(
        SITES,
        json={
            "code": "kips",
            "name": "Ichthys",
            "lat": -12.5,
            "lng": 130.8,
            "timezone": "Australia/Darwin",
        },
        headers=ALICE,
    )
    assert created.status_code == 201, created.text
    site = created.json()
    assert (site["code"], site["isSystem"]) == ("KIPS", False)
    url = f"{SITES}/{site['id']}"

    dup = await client.post(SITES, json={"code": "KIPS", "name": "Again"}, headers=ALICE)
    assert (dup.status_code, dup.json()) == (409, {"code": "SITE_CODE_TAKEN"})
    renamed = await client.patch(url, json={"name": "Ichthys LNG"}, headers=ALICE)
    assert renamed.json()["name"] == "Ichthys LNG"
    assert (await client.get(url, headers=BOB)).status_code == 404

    project = (await create(client, ALICE, code="L592", siteId=site["id"], status="active")).json()
    in_use = await client.delete(url, headers=ALICE)
    assert (in_use.status_code, in_use.json()) == (409, {"code": "SITE_IN_USE"})

    move = {"syncVersion": project["syncVersion"], "siteId": None}
    assert (
        await client.patch(f"{PROJECTS}/{project['id']}", json=move, headers=ALICE)
    ).status_code == 200
    assert (await client.delete(url, headers=ALICE)).status_code == 204
    assert (await client.get(url, headers=ALICE)).status_code == 404
    assert (await client.delete(url, headers=ALICE)).status_code == 404
    listed = (await client.get(SITES, headers=ALICE)).json()
    assert listed["items"] == []


async def test_system_sites_are_hidden_and_cannot_be_changed(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    """PROJECTS-05: the hidden per-project hierarchy root is never shown, edited or deleted."""
    system_id = "00000000-0000-4000-8000-0000000005e1"
    await su_execute(
        db,
        "INSERT INTO sites (id, tenant_id, code, name, is_system) VALUES"
        f" ('{system_id}', '{TENANT_A_ID}', 'SYS-L592', 'L592 hierarchy root', true)",
    )
    assert (
        await client.post(SITES, json={"code": "KIPS", "name": "Ichthys"}, headers=ALICE)
    ).status_code == 201

    listed = (await client.get(SITES, headers=ALICE)).json()
    assert [s["code"] for s in listed["items"]] == ["KIPS"]
    assert (await client.get(SITES, params={"q": "SYS"}, headers=ALICE)).json()["items"] == []
    assert (await client.get(f"{SITES}/{system_id}", headers=ALICE)).status_code == 404

    for method, body in (("PATCH", {"name": "Renamed"}), ("PATCH", {}), ("DELETE", None)):
        response = await client.request(method, f"{SITES}/{system_id}", json=body, headers=ALICE)
        assert (response.status_code, response.json()) == (409, {"code": "SITE_IS_SYSTEM"})
    assert await su_fetch(db, f"SELECT name, deleted_at FROM sites WHERE id = '{system_id}'") == [
        ("L592 hierarchy root", None)
    ]
