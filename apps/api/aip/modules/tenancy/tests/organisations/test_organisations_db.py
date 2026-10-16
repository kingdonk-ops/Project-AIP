"""TENANCY-03 integration tests: the organisations API and table on real Postgres.

The app connects as ``aip_app`` (RLS on). Users come from the AUTH_TEST_STUB principal header;
permissions from the ``grants`` fixture.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from .conftest import ALICE, BOB, READ, GrantTable, su_fetch

ORGS = "/api/v1/settings/organisations"


async def create(client: httpx.AsyncClient, headers: dict[str, str], **body: Any) -> httpx.Response:
    payload = {"name": "Rio Tinto", "type": "client", **body}
    return await client.post(ORGS, json=payload, headers=headers)


async def events(db: TenantDb, name: str) -> list[tuple[Any, ...]]:
    """All tenants' ``name`` events as (tenant, actor, aggregate, payload), oldest first."""
    rows = await su_fetch(
        db,
        "SELECT tenant_id, actor_id, aggregate_id, payload FROM domain_events"
        " WHERE event_name = $1 ORDER BY occurred_at",
        name,
    )
    return [(*row[:3], json.loads(row[3])) for row in rows]  # asyncpg returns jsonb as text


async def test_a_client_organisation_is_created_and_listed(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await create(client, ALICE, registrationNumber="96 004 458 404")
    assert created.status_code == 201, created.text
    org = created.json()
    assert (org["name"], org["type"], org["status"], org["syncVersion"]) == (
        "Rio Tinto",
        "client",
        "active",
        1,
    )
    assert org["registrationNumber"] == "96 004 458 404"

    listed = (await client.get(ORGS, headers=ALICE)).json()["items"]
    assert [(o["name"], o["type"]) for o in listed] == [("Rio Tinto", "client")]

    clients = (await client.get(f"{ORGS}?type=client", headers=ALICE)).json()["items"]
    owners = (await client.get(f"{ORGS}?type=owner", headers=ALICE)).json()["items"]
    assert (len(clients), owners) == (1, [])

    [event] = await events(db, "tenancy.organisation_created")
    assert event[:3] == (TENANT_A_ID, ALICE_ID, UUID(org["id"]))
    assert event[3] == {
        "organisationId": org["id"],
        "name": "Rio Tinto",
        "type": "client",
        "status": "active",
        "before": None,
        "after": None,
    }


async def test_names_are_unique_per_tenant_ignoring_case(client: httpx.AsyncClient) -> None:
    assert (await create(client, ALICE)).status_code == 201
    again = await create(client, ALICE, name="rio tinto", type="subcontractor")
    assert (again.status_code, again.json()) == (409, {"code": "ORGANISATION_NAME_TAKEN"})
    assert (await create(client, BOB)).status_code == 201  # another tenant may use the name


async def test_another_tenants_organisation_is_404_and_never_listed(
    client: httpx.AsyncClient,
) -> None:
    org_id = (await create(client, ALICE)).json()["id"]
    assert (await client.get(f"{ORGS}/{org_id}", headers=ALICE)).status_code == 200

    response = await client.get(f"{ORGS}/{org_id}", headers=BOB)
    assert (response.status_code, response.json()) == (404, {"code": "NOT_FOUND"})
    patch = {"syncVersion": 1, "name": "Mine now"}
    assert (await client.patch(f"{ORGS}/{org_id}", json=patch, headers=BOB)).status_code == 404
    assert (await client.get(ORGS, headers=BOB)).json() == {"items": []}


async def test_update_and_deactivate_with_version_check(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    org = (await create(client, ALICE, type="subcontractor", name="Acme Scaffolding")).json()
    url = f"{ORGS}/{org['id']}"

    renamed = await client.patch(url, json={"syncVersion": 1, "name": "Acme Access"}, headers=ALICE)
    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["name"], renamed.json()["syncVersion"]) == ("Acme Access", 2)

    stale = await client.patch(url, json={"syncVersion": 1, "status": "inactive"}, headers=ALICE)
    assert stale.status_code == 409
    assert stale.json()["current"]["name"] == "Acme Access"

    off = await client.patch(url, json={"syncVersion": 2, "status": "inactive"}, headers=ALICE)
    assert (off.status_code, off.json()["status"]) == (200, "inactive")
    inactive = (await client.get(f"{ORGS}?status=inactive", headers=ALICE)).json()["items"]
    assert [o["id"] for o in inactive] == [org["id"]]

    updates = await events(db, "tenancy.organisation_updated")
    assert [e[3]["after"] for e in updates] == [{"name": "Acme Access"}, {"status": "inactive"}]
    assert updates[0][3]["before"] == {"name": "Acme Scaffolding"}


async def test_unknown_type_and_blank_name_are_rejected(client: httpx.AsyncClient) -> None:
    assert (await create(client, ALICE, type="other")).status_code == 422
    assert (await create(client, ALICE, name="")).status_code == 422
    org_id = (await create(client, ALICE)).json()["id"]
    patch = {"syncVersion": 1, "type": "other"}
    assert (await client.patch(f"{ORGS}/{org_id}", json=patch, headers=ALICE)).status_code == 422


async def test_routes_deny_without_the_permission(
    client: httpx.AsyncClient, grants: GrantTable
) -> None:
    org_id = (await create(client, ALICE)).json()["id"]

    grants.by_user[ALICE_ID] = {READ}
    assert (await client.get(ORGS, headers=ALICE)).status_code == 200
    assert (await create(client, ALICE, name="Other")).status_code == 403
    patch = {"syncVersion": 1, "name": "Renamed"}
    assert (await client.patch(f"{ORGS}/{org_id}", json=patch, headers=ALICE)).status_code == 403

    grants.by_user[ALICE_ID] = set()
    assert (await client.get(ORGS, headers=ALICE)).status_code == 403
    assert (await client.get(f"{ORGS}/{org_id}", headers=ALICE)).status_code == 403


async def test_the_table_forces_rls_and_aip_app_cannot_delete(db: TenantDb) -> None:
    [(forced, enabled)] = await su_fetch(
        db,
        "SELECT relforcerowsecurity, relrowsecurity FROM pg_class WHERE relname = 'organisations'",
    )
    assert forced and enabled
    [(can_delete,)] = await su_fetch(
        db, "SELECT has_table_privilege('aip_app', 'organisations', 'DELETE')"
    )
    assert can_delete is False


async def test_renaming_onto_a_taken_name_is_409(client: httpx.AsyncClient) -> None:
    assert (await create(client, ALICE)).status_code == 201
    other = (await create(client, ALICE, name="BHP")).json()
    patch = {"syncVersion": 1, "name": "RIO TINTO"}
    response = await client.patch(f"{ORGS}/{other['id']}", json=patch, headers=ALICE)
    assert (response.status_code, response.json()) == (409, {"code": "ORGANISATION_NAME_TAKEN"})


async def test_a_patch_cannot_set_protected_fields(client: httpx.AsyncClient) -> None:
    org_id = (await create(client, ALICE)).json()["id"]
    for field, value in (
        ("tenantId", str(UUID(int=1))),
        ("id", str(UUID(int=2))),
        ("deletedAt", "2026-01-01T00:00:00Z"),
    ):
        patch = {"syncVersion": 1, field: value}
        response = await client.patch(f"{ORGS}/{org_id}", json=patch, headers=ALICE)
        assert response.status_code == 422, field


async def test_an_unknown_id_is_404(client: httpx.AsyncClient) -> None:
    missing = str(UUID(int=7))
    assert (await client.get(f"{ORGS}/{missing}", headers=ALICE)).status_code == 404
    patch = {"syncVersion": 1, "name": "Ghost"}
    assert (await client.patch(f"{ORGS}/{missing}", json=patch, headers=ALICE)).status_code == 404
