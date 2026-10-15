"""ARCH-06: the event-catalogue API (integration + e2e, real Postgres).

The real app is built with ``AUTH_TEST_STUB`` and the real ``RoleGrantProvider``. A kaefer-demo
user (``alice``) is granted ``platform.events.manage`` through a tenant role; ``carol`` (same
tenant, no grant) and ``bob`` (tenant B, no grant) stand in for everyone else. Events, counts and
the deprecation flag are seeded straight into Postgres as the superuser (which bypasses RLS), so
the figures are exact and cross-tenant.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from aip.main import create_app
from aip.modules.access.api import sync_catalogue
from aip.platform.context import RequestContext, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    _fetch,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

CAROL_ID = UUID("00000000-0000-4000-8000-00000000ca01")  # kaefer-demo user with no grant
OPS_ROLE_ID = UUID("00000000-0000-4000-8000-00000000705e")
PROJECT_CREATED = "project.created"

SEED_TENANTS_USERS = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
    "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
    f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active'), "
    f"('{CAROL_ID}', '{TENANT_A_ID}', 'staff', 'carol@kaefer.test', 'Carol', 'active'), "
    f"('{BOB_ID}', '{TENANT_B_ID}', 'staff', 'bob@acme.test', 'Bob', 'active');"
)

# Run only after sync_catalogue: role_permission.permission_code has an FK to the permission table.
GRANT_SQL = (
    "INSERT INTO role (id, tenant_id, code, name, is_system) VALUES "
    f"('{OPS_ROLE_ID}', '{TENANT_A_ID}', 'platform_ops', 'Platform Ops', false);"
    "INSERT INTO role_permission (id, tenant_id, role_id, permission_code) VALUES "
    f"(gen_random_uuid(), '{TENANT_A_ID}', '{OPS_ROLE_ID}', 'platform.events.manage');"
    "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type) VALUES "
    f"(gen_random_uuid(), '{TENANT_A_ID}', '{ALICE_ID}', '{OPS_ROLE_ID}', 'tenant');"
)


def headers(tenant: UUID, user: UUID) -> dict[str, str]:
    principal = {
        "kind": "user",
        "tenantId": str(tenant),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": 2,
        "amr": ["fed"],
    }
    return {"x-test-principal": json.dumps(principal)}


OPERATOR = headers(TENANT_A_ID, ALICE_ID)
CAROL = headers(TENANT_A_ID, CAROL_ID)
BOB = headers(TENANT_B_ID, BOB_ID)


async def su_execute(db: TenantDb, sql: str) -> None:
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await _fetch(db.db.superuser_url, sql, *args)


async def insert_event(
    db: TenantDb,
    tenant: UUID,
    *,
    name: str = PROJECT_CREATED,
    version: int = 1,
    published: bool = False,
    dead_lettered: bool = False,
) -> None:
    """Insert one domain_events row as the superuser (bypassing RLS), aged inside the 24h window."""
    await su_execute(
        db,
        "INSERT INTO domain_events (id, tenant_id, event_name, event_version, aggregate_type,"
        " aggregate_id, payload, occurred_at, published_at, dead_lettered_at) VALUES ("
        f"'{uuid4()}', '{tenant}', '{name}', {version}, 'project', '{uuid4()}', '{{}}'::jsonb,"
        " now() - interval '1 hour',"
        f" {'now()' if published else 'NULL'}, {'now()' if dead_lettered else 'NULL'});",
    )


@pytest.fixture
async def app(tenant_db: TenantDb, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:  # noqa: F811
    await su_execute(tenant_db, SEED_TENANTS_USERS)
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", tenant_db.db.app_url)
    await dispose_engine()
    application = create_app(env="test", tracing=False)
    await sync_catalogue(application.state.access_catalogue)
    await su_execute(tenant_db, GRANT_SQL)  # after the permission exists in the catalogue
    yield application
    await dispose_engine()


@pytest.fixture
def db(app: FastAPI, tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    return tenant_db


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _row(body: dict[str, Any], name: str, version: int = 1) -> dict[str, Any]:
    return next(e for e in body["events"] if e["name"] == name and e["version"] == version)


# --- catalogue counts ---------------------------------------------------------------------------


async def test_catalogue_reports_24h_published_and_failed_across_tenants(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    # 5 rows for project.created v1 across both tenants: 3 published, 2 dead-lettered.
    await insert_event(db, TENANT_A_ID, published=True)
    await insert_event(db, TENANT_A_ID, published=True)
    await insert_event(db, TENANT_B_ID, published=True)
    await insert_event(db, TENANT_A_ID, dead_lettered=True)
    await insert_event(db, TENANT_B_ID, dead_lettered=True)

    response = await client.get("/api/v1/admin/platform/events", headers=OPERATOR)
    assert response.status_code == 200
    row = _row(response.json(), PROJECT_CREATED)
    assert row["published24h"] == 3
    assert row["failed24h"] == 2
    assert row["module"] == "projects"
    assert row["status"] == "active"


async def test_an_event_with_no_recent_rows_reports_zero(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/admin/platform/events", headers=OPERATOR)
    row = _row(response.json(), PROJECT_CREATED)
    assert (row["published24h"], row["failed24h"]) == (0, 0)


# --- filters ------------------------------------------------------------------------------------


async def test_module_filter_returns_only_that_modules_events(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/admin/platform/events", params={"module": "projects"}, headers=OPERATOR
    )
    assert response.status_code == 200
    events = response.json()["events"]
    assert events, "expected projects events"
    assert {e["module"] for e in events} == {"projects"}
    assert {e["name"] for e in events} == {"project.created", "project.updated", "project.archived"}


async def test_subscribers_come_from_the_manifests(client: httpx.AsyncClient) -> None:
    # Every row carries a subscribers list (empty until a module subscribes).
    response = await client.get("/api/v1/admin/platform/events", headers=OPERATOR)
    assert all(isinstance(e["subscribers"], list) for e in response.json()["events"])


# --- deprecate ----------------------------------------------------------------------------------


async def test_deprecate_flags_the_version_and_a_deprecated_event_still_emits(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    deprecate = await client.post(
        f"/api/v1/admin/platform/events/{PROJECT_CREATED}/versions/1/deprecate", headers=OPERATOR
    )
    assert deprecate.status_code == 200, deprecate.text
    assert deprecate.json()["status"] == "deprecated"
    assert deprecate.json()["deprecatedBy"] == str(ALICE_ID)

    # The catalogue now flags it deprecated.
    catalogue = await client.get("/api/v1/admin/platform/events", headers=OPERATOR)
    assert _row(catalogue.json(), PROJECT_CREATED)["status"] == "deprecated"

    # A deprecated event still validates and inserts (deprecation is a flag, not a block).
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id="test-emit", actor_id=ALICE_ID)
    with use_context(ctx):
        async with with_tenant(ctx) as conn:
            event_id = await emit(
                conn,
                PROJECT_CREATED,
                1,
                Aggregate("project", uuid4()),
                {"projectId": str(uuid4()), "code": "P-1", "status": "active"},
            )
    assert event_id is not None

    # The deprecate wrote the platform.event.deprecated audit event.
    rows = await su_fetch(
        db,
        "SELECT count(*) FROM domain_events WHERE event_name = 'platform.event.deprecated'",
    )
    assert rows[0][0] == 1


async def test_a_deprecate_of_an_unknown_event_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/admin/platform/events/nope.happened/versions/1/deprecate", headers=OPERATOR
    )
    assert response.status_code == 404


# --- detail -------------------------------------------------------------------------------------


async def test_event_detail_returns_schema_and_subscribers(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"/api/v1/admin/platform/events/{PROJECT_CREATED}", headers=OPERATOR
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == PROJECT_CREATED
    version = next(v for v in body["versions"] if v["version"] == 1)
    assert version["schema"]["type"] == "object"
    assert "projectId" in version["schema"]["properties"]
    assert isinstance(version["subscribers"], list)


async def test_event_detail_for_an_unknown_event_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/admin/platform/events/nope.happened", headers=OPERATOR)
    assert response.status_code == 404


# --- access (e2e) -------------------------------------------------------------------------------


async def test_a_plain_tenant_user_is_forbidden(client: httpx.AsyncClient) -> None:
    for who in (CAROL, BOB):
        listed = await client.get("/api/v1/admin/platform/events", headers=who)
        assert listed.status_code == 403, who
        deprecated = await client.post(
            f"/api/v1/admin/platform/events/{PROJECT_CREATED}/versions/1/deprecate", headers=who
        )
        assert deprecated.status_code == 403, who


async def test_the_operator_is_allowed(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/admin/platform/events", headers=OPERATOR)
    assert response.status_code == 200
    assert any(e["name"] == PROJECT_CREATED for e in response.json()["events"])
