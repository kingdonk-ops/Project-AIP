"""IDENTITY-11: the user's preferred IANA time zone, against real Postgres (ADR 0025).

``PATCH /api/v1/me`` sets the caller's own zone, ``GET /api/v1/me`` reads it back, and the published
``get_time_zones`` maps user ids of the bound tenant to their zone for other modules (PORTAL-12).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from tests.fixtures.postgres import TenantDb

from aip.main import create_app
from aip.modules.identity import api as identity_api
from aip.modules.identity import repository as repo
from aip.modules.identity.tables import auth_event
from aip.platform.db.engine import dispose_engine

from .conftest import TENANT_A_ID, TENANT_B_ID
from .test_me_db import ALICE, BOB, principal, seed_user


@pytest.fixture
async def app(idb: TenantDb, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", idb.db.app_url)
    await dispose_engine()
    yield create_app(env="test", tracing=False)
    await dispose_engine()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://app.example.test") as c:
        yield c


async def test_set_and_read_back_and_get_time_zones_returns_it(
    idb: TenantDb, client: httpx.AsyncClient
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    headers = principal(TENANT_A_ID, alice)

    r = await client.patch("/api/v1/me", json={"timeZone": "Australia/Sydney"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["timeZone"] == "Australia/Sydney"
    assert r.headers["cache-control"] == "no-store"

    r = await client.get("/api/v1/me", headers=headers)
    assert r.json()["user"]["timeZone"] == "Australia/Sydney"

    async with idb.with_tenant(TENANT_A_ID) as conn:
        assert await identity_api.get_time_zones(conn, [alice]) == {alice: "Australia/Sydney"}
        events = (
            await conn.execute(
                select(auth_event.c.event_type, auth_event.c.detail).where(
                    auth_event.c.user_id == alice
                )
            )
        ).all()
    assert [(e.event_type, e.detail) for e in events] == [
        ("profile.updated", {"fields": ["time_zone"]})
    ]


async def test_null_clears_and_an_omitted_field_changes_nothing(
    idb: TenantDb, client: httpx.AsyncClient
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    headers = principal(TENANT_A_ID, alice)
    await client.patch("/api/v1/me", json={"timeZone": "Australia/Perth"}, headers=headers)

    r = await client.patch("/api/v1/me", json={}, headers=headers)
    assert r.status_code == 200 and r.json()["user"]["timeZone"] == "Australia/Perth"

    r = await client.patch("/api/v1/me", json={"timeZone": None}, headers=headers)
    assert r.status_code == 200 and r.json()["user"]["timeZone"] is None
    async with idb.with_tenant(TENANT_A_ID) as conn:
        assert await identity_api.get_time_zones(conn, [alice]) == {alice: None}


@pytest.mark.parametrize("name", ["AWST", "australia/sydney", "Mars/Olympus", "", "+08:00"])
async def test_an_unknown_name_is_422_and_nothing_changes(
    idb: TenantDb, client: httpx.AsyncClient, name: str
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    headers = principal(TENANT_A_ID, alice)
    await client.patch("/api/v1/me", json={"timeZone": "Australia/Perth"}, headers=headers)

    r = await client.patch("/api/v1/me", json={"timeZone": name}, headers=headers)
    assert r.status_code == 422
    assert r.json() == {"detail": {"code": "INVALID_TIME_ZONE", "message": "unknown time zone"}}
    async with idb.with_tenant(TENANT_A_ID) as conn:
        assert await identity_api.get_time_zones(conn, [alice]) == {alice: "Australia/Perth"}


async def test_another_tenants_user_is_absent_from_get_time_zones(
    idb: TenantDb, client: httpx.AsyncClient
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    bob = await seed_user(idb, TENANT_B_ID, BOB)
    r = await client.patch(
        "/api/v1/me", json={"timeZone": "Pacific/Auckland"}, headers=principal(TENANT_B_ID, bob)
    )
    assert r.status_code == 200, r.text
    async with idb.with_tenant(TENANT_A_ID) as conn:
        assert await identity_api.get_time_zones(conn, [alice, bob, uuid4()]) == {alice: None}
        assert await identity_api.get_time_zones(conn, []) == {}
    async with idb.with_tenant(TENANT_B_ID) as conn:
        assert await identity_api.get_time_zones(conn, [alice, bob]) == {bob: "Pacific/Auckland"}


async def test_a_principal_naming_another_tenants_user_cannot_set_it(
    idb: TenantDb, client: httpx.AsyncClient
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    r = await client.patch(
        "/api/v1/me", json={"timeZone": "Asia/Tokyo"}, headers=principal(TENANT_B_ID, alice)
    )
    assert r.status_code == 401
    async with idb.with_tenant(TENANT_A_ID) as conn:
        assert await identity_api.get_time_zones(conn, [alice]) == {alice: None}


async def test_a_deactivated_user_cannot_set_it(idb: TenantDb, client: httpx.AsyncClient) -> None:
    gone = await seed_user(idb, TENANT_A_ID, "gone@kaefer.test")
    async with idb.with_tenant(TENANT_A_ID) as conn:
        await repo.set_user_status(conn, gone, "deactivated")
    r = await client.patch(
        "/api/v1/me", json={"timeZone": "Asia/Tokyo"}, headers=principal(TENANT_A_ID, gone)
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "NOT_AUTHENTICATED"


async def test_an_unknown_field_is_refused(idb: TenantDb, client: httpx.AsyncClient) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    r = await client.patch(
        "/api/v1/me", json={"displayName": "Mallory"}, headers=principal(TENANT_A_ID, alice)
    )
    assert r.status_code == 422


async def test_patch_me_is_in_the_openapi_document(app: FastAPI) -> None:
    op = app.openapi()["paths"]["/api/v1/me"]["patch"]
    assert op["operationId"] == "identity_update_me"
    assert op["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/MeUpdate")
