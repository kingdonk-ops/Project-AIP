"""``tenants`` and ``deployment_regions`` on real Postgres (TENANCY-01). Never mocks the database.

Postgres comes from the DATABASE-08/02 fixtures (``AIP_TEST_DATABASE_URL``, else Testcontainers);
the cluster bootstrap creates ``aip_app`` (ADR 0012). Every test runs after ``seed.py``.
Cross-tenant checks use the shared fixtures: ``kaefer-demo`` (alice) and ``tenant-b`` (bob).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from tests.conftest import ALICE_ID, BOB_ID, FixturePrincipalResolver
from tests.platform.db.conftest import (  # noqa: F401 - re-exported pytest fixtures
    READONLY,
    FreshDb,
    empty_db,  # pyright: ignore[reportUnusedImport]
    execute,
    fetch,
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
)

from aip.main import create_app
from aip.modules.tenancy.api import TenantView, get_tenant, require_active_tenant
from aip.modules.tenancy.dependencies import get_tenant_service
from aip.modules.tenancy.seed import KAEFER_DEMO_ID, TENANT_B_ID, seed
from aip.modules.tenancy.service import TenantConnect, TenantService
from aip.platform.context import Principal
from aip.platform.db.engine import EngineSettings, create_app_engine, dispose_engine
from aip.platform.db.session import with_tenant

UNKNOWN_ID = UUID("00000000-0000-4000-8000-0000000000ff")


@pytest.fixture
def tenancy_db(empty_db: FreshDb) -> FreshDb:  # noqa: F811
    empty_db.migrate()
    assert asyncio.run(seed(empty_db.owner_url, env="test")) == 2
    return empty_db


@pytest.fixture
async def app_tx(tenancy_db: FreshDb) -> AsyncIterator[TenantConnect]:
    """``with_tenant`` as ``aip_app`` on the test database."""
    engine = create_app_engine(EngineSettings(url=tenancy_db.app_url, pool_size=2))
    try:
        yield lambda tenant: with_tenant(tenant, engine=engine)
    finally:
        await engine.dispose()


@pytest.fixture
def app(app_tx: TenantConnect) -> FastAPI:
    resolver = FixturePrincipalResolver(
        {
            "token-alice": Principal(tenant_id=KAEFER_DEMO_ID, actor_id=ALICE_ID),
            "token-bob": Principal(tenant_id=TENANT_B_ID, actor_id=BOB_ID),
            "token-unknown": Principal(tenant_id=UNKNOWN_ID),
        }
    )
    application = create_app(env="test", principal_resolver=resolver, tracing=False)
    service = TenantService(app_tx)
    application.dependency_overrides[get_tenant_service] = lambda: service

    async def guarded(
        tenant: Annotated[TenantView, Depends(require_active_tenant)],
    ) -> dict[str, Any]:
        return {"slug": tenant.slug}

    application.add_api_route("/api/v1/_test/guarded", guarded, methods=["GET"])
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _app_rows(tx: TenantConnect, tenant: UUID, sql: str) -> list[tuple[Any, ...]]:
    async with tx(tenant) as conn:
        return [tuple(r) for r in (await conn.execute(text(sql))).all()]


# --- RLS: each tenant sees only its own row ---------------------------------------------------


async def test_aip_app_sees_exactly_its_own_tenant(app_tx: TenantConnect) -> None:
    rows = await _app_rows(app_tx, KAEFER_DEMO_ID, "SELECT id, slug FROM tenants")
    assert rows == [(KAEFER_DEMO_ID, "kaefer-demo")]
    rows = await _app_rows(app_tx, TENANT_B_ID, "SELECT id, slug FROM tenants")
    assert rows == [(TENANT_B_ID, "tenant-b")]


async def test_other_tenant_row_is_invisible_even_by_id(app_tx: TenantConnect) -> None:
    sql_b = f"SELECT * FROM tenants WHERE id = '{TENANT_B_ID}' OR slug = 'tenant-b'"
    assert await _app_rows(app_tx, KAEFER_DEMO_ID, sql_b) == []
    sql_a = f"SELECT * FROM tenants WHERE id = '{KAEFER_DEMO_ID}' OR slug = 'kaefer-demo'"
    assert await _app_rows(app_tx, TENANT_B_ID, sql_a) == []
    assert await _app_rows(app_tx, UNKNOWN_ID, "SELECT * FROM tenants") == []


def test_no_tenant_context_sees_nothing(tenancy_db: FreshDb) -> None:
    assert fetch(tenancy_db.app_url, "SELECT * FROM tenants") == []
    assert fetch(tenancy_db.role_url(READONLY), "SELECT * FROM tenants") == []
    # FORCE RLS binds the owner too: no tenant set, no rows.
    assert fetch(tenancy_db.owner_url, "SELECT * FROM tenants") == []
    assert tenancy_db.fetch("SELECT count(*) FROM tenants") == [(2,)]  # superuser only


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE tenants SET status = 'active'",
        "DELETE FROM tenants",
        "INSERT INTO tenants (id, name, slug, region_code, status) "
        "VALUES ('00000000-0000-4000-8000-0000000000aa', 'X', 'x', 'ap-southeast-2', 'active')",
        "UPDATE deployment_regions SET in_country_only = true",
        "INSERT INTO deployment_regions (code, label_key) VALUES ('us-east-1', 'x.y')",
    ],
)
def test_aip_app_cannot_write_tenants_or_regions(tenancy_db: FreshDb, sql: str) -> None:
    for tenant in (KAEFER_DEMO_ID, TENANT_B_ID):
        scoped = f"SELECT set_config('app.tenant_id', '{tenant}', true); {sql}"
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            execute(tenancy_db.app_url, scoped)


def test_owner_cannot_write_another_tenant_row(tenancy_db: FreshDb) -> None:
    # Inside kaefer-demo's context even the owner cannot touch tenant-b (WITH CHECK / USING).
    scoped = f"SELECT set_config('app.tenant_id', '{KAEFER_DEMO_ID}', true); "
    execute(tenancy_db.owner_url, scoped + "UPDATE tenants SET name = 'pwned'")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        execute(
            tenancy_db.owner_url,
            scoped + "INSERT INTO tenants (id, name, slug, region_code) "
            f"VALUES ('{UNKNOWN_ID}', 'X', 'x', 'ap-southeast-2')",
        )
    names = tenancy_db.fetch("SELECT slug, name FROM tenants ORDER BY slug")
    assert names == [("kaefer-demo", "pwned"), ("tenant-b", "Tenant B")]


def test_rls_is_enabled_and_forced_with_the_fail_closed_policy(tenancy_db: FreshDb) -> None:
    rows = tenancy_db.fetch(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'tenants'"
    )
    assert rows == [(True, True)]
    policies = tenancy_db.fetch(
        "SELECT policyname, cmd, qual, with_check FROM pg_policies WHERE tablename = 'tenants'"
    )
    assert len(policies) == 1
    name, cmd, qual, with_check = policies[0]
    assert (name, cmd) == ("tenant_isolation", "ALL")
    for expr in (qual, with_check):
        assert "NULLIF(current_setting('app.tenant_id'::text, true), ''::text)" in expr
        assert expr.startswith("(id = ")


# --- reference data, seed, schema -------------------------------------------------------------


async def test_regions_are_readable_reference_data(app_tx: TenantConnect) -> None:
    for tenant in (KAEFER_DEMO_ID, TENANT_B_ID):
        rows = await _app_rows(
            app_tx, tenant, "SELECT code, label_key FROM deployment_regions ORDER BY code"
        )
        assert rows == [
            ("ap-southeast-1", "tenancy.region.ap_southeast_1"),
            ("ap-southeast-2", "tenancy.region.ap_southeast_2"),
            ("eu-west-2", "tenancy.region.eu_west_2"),
        ]


def test_seed_twice_keeps_two_tenants_and_three_regions(tenancy_db: FreshDb) -> None:
    tenancy_db.execute("UPDATE tenants SET status = 'suspended' WHERE slug = 'tenant-b'")
    assert asyncio.run(seed(tenancy_db.owner_url, env="test")) == 2
    assert tenancy_db.fetch("SELECT count(*) FROM tenants") == [(2,)]
    assert tenancy_db.fetch("SELECT count(*) FROM deployment_regions") == [(3,)]
    rows = tenancy_db.fetch(
        "SELECT id, slug, name, region_code, status, deployment_shape, kms_key_ref "
        "FROM tenants ORDER BY slug"
    )
    assert rows == [
        (KAEFER_DEMO_ID, "kaefer-demo", "Kaefer Demo", "ap-southeast-2", "active", "pooled", None),
        (TENANT_B_ID, "tenant-b", "Tenant B", "ap-southeast-2", "active", "pooled", None),
    ]


def test_login_directory_must_point_at_a_real_tenant(tenancy_db: FreshDb) -> None:
    tenancy_db.execute(
        "INSERT INTO login_directory (kind, key, tenant_id) "
        f"VALUES ('tenant_slug', 'kaefer-demo', '{KAEFER_DEMO_ID}')"
    )
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        tenancy_db.execute(
            "INSERT INTO login_directory (kind, key, tenant_id) "
            f"VALUES ('tenant_slug', 'ghost', '{UNKNOWN_ID}')"
        )
    rows = tenancy_db.fetch(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'login_directory'::regclass "
        "AND contype = 'f'"
    )
    assert rows == [("fk_login_directory_tenant_id_tenants",)]


@pytest.mark.parametrize(
    ("column", "value"),
    [("status", "deleted"), ("deployment_shape", "hybrid"), ("region_code", "us-east-1")],
)
def test_tenant_columns_are_constrained(tenancy_db: FreshDb, column: str, value: str) -> None:
    with pytest.raises((asyncpg.CheckViolationError, asyncpg.ForeignKeyViolationError)):
        tenancy_db.execute(f"UPDATE tenants SET {column} = '{value}' WHERE slug = 'tenant-b'")


def test_declared_tables_match_the_migration(tenancy_db: FreshDb) -> None:
    result = tenancy_db.aip_db("check-schema")
    assert result.returncode == 0, result.stdout + result.stderr


# --- the service and the HTTP dependency ------------------------------------------------------


async def test_get_tenant_reads_through_the_app_engine(
    tenancy_db: FreshDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The published get_tenant uses the process-wide aip_app engine (DATABASE_URL).
    monkeypatch.setenv("DATABASE_URL", tenancy_db.app_url)
    await dispose_engine()
    try:
        kaefer = await get_tenant(KAEFER_DEMO_ID)
        assert kaefer is not None
        assert (kaefer.slug, kaefer.region_code, kaefer.status) == (
            "kaefer-demo",
            "ap-southeast-2",
            "active",
        )
        tenant_b = await get_tenant(TENANT_B_ID)
        assert tenant_b is not None and tenant_b.slug == "tenant-b"
        assert await get_tenant(UNKNOWN_ID) is None
    finally:
        await dispose_engine()


async def test_me_tenant_returns_the_callers_tenant_only(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/me/tenant", headers=bearer("token-alice"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["id"], body["slug"], body["regionCode"]) == (
        str(KAEFER_DEMO_ID),
        "kaefer-demo",
        "ap-southeast-2",
    )
    assert "kmsKeyRef" not in body
    resp = await client.get("/api/v1/me/tenant", headers=bearer("token-bob"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["slug"] == "tenant-b"
    assert "kaefer" not in resp.text


async def test_suspended_tenant_gets_403_and_other_tenant_is_unaffected(
    tenancy_db: FreshDb, client: httpx.AsyncClient
) -> None:
    await asyncio.to_thread(
        tenancy_db.execute, "UPDATE tenants SET status = 'suspended' WHERE slug = 'tenant-b'"
    )
    for path in ("/api/v1/_test/guarded", "/api/v1/me/tenant"):
        resp = await client.get(path, headers=bearer("token-bob"))
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "TENANT_SUSPENDED"
    resp = await client.get("/api/v1/_test/guarded", headers=bearer("token-alice"))
    assert resp.status_code == 200
    assert resp.json() == {"slug": "kaefer-demo"}


async def test_soft_deleted_or_unknown_tenant_is_401(
    tenancy_db: FreshDb, client: httpx.AsyncClient
) -> None:
    resp = await client.get("/api/v1/me/tenant", headers=bearer("token-unknown"))
    assert resp.status_code == 401
    await asyncio.to_thread(
        tenancy_db.execute, "UPDATE tenants SET deleted_at = now() WHERE slug = 'tenant-b'"
    )
    resp = await client.get("/api/v1/me/tenant", headers=bearer("token-bob"))
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TENANT_UNKNOWN"


async def test_unauthenticated_is_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/me/tenant")
    assert resp.status_code == 401
