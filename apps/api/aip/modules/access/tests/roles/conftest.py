"""Fixtures for the ACCESS-02 tests: a migrated database, both fixture tenants with users and
their system roles, and the real app with the real ``RoleGrantProvider`` (no test grants).

Seeding runs as the superuser (users, the first tenant_admin assignment); every assertion goes
through ``aip_app`` (RLS on) or the API.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
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

from aip.main import create_app
from aip.modules.access.api import seed_default_roles, sync_catalogue
from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

ADMIN2_ID = UUID("00000000-0000-4000-8000-0000000ad002")  # a second kaefer-demo user
CAROL_ID = UUID("00000000-0000-4000-8000-00000000ca01")  # a kaefer-demo user with no role yet
DAVE_ID = UUID("00000000-0000-4000-8000-00000000da01")  # a deactivated kaefer-demo user

SEED_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
    "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status,"
    " deactivated_at) VALUES "
    f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active', NULL), "
    f"('{ADMIN2_ID}', '{TENANT_A_ID}', 'staff', 'admin2@kaefer.test', 'Admin 2', 'active', NULL),"
    f"('{CAROL_ID}', '{TENANT_A_ID}', 'staff', 'carol@kaefer.test', 'Carol', 'active', NULL), "
    f"('{DAVE_ID}', '{TENANT_A_ID}', 'staff', 'dave@kaefer.test', 'Dave', 'deactivated', now()),"
    f"('{BOB_ID}', '{TENANT_B_ID}', 'staff', 'bob@acme.test', 'Bob', 'active', NULL)"
)


def headers(tenant: UUID, user: UUID, *, aal: int = 2) -> dict[str, str]:
    principal = {
        "kind": "user",
        "tenantId": str(tenant),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": aal,
        "amr": ["fed"],
    }
    return {"x-test-principal": json.dumps(principal)}


ALICE = headers(TENANT_A_ID, ALICE_ID)  # kaefer-demo tenant_admin, stepped up
ALICE_AAL1 = headers(TENANT_A_ID, ALICE_ID, aal=1)
ADMIN2 = headers(TENANT_A_ID, ADMIN2_ID)
CAROL = headers(TENANT_A_ID, CAROL_ID)
BOB = headers(TENANT_B_ID, BOB_ID)  # tenant-b tenant_admin


async def su_execute(db: TenantDb, sql: str) -> None:
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await _fetch(db.db.superuser_url, sql, *args)


async def su_assign(
    db: TenantDb, tenant: UUID, user: UUID, role_code: str, project: UUID | None = None
) -> UUID:
    """Bootstrap an assignment as the superuser (as provisioning would for the first admin)."""
    scope, project_sql = ("project", f"'{project}'") if project else ("tenant", "NULL")
    rows = await su_fetch(
        db,
        "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type, project_id)"
        f" SELECT gen_random_uuid(), '{tenant}', '{user}', r.id, '{scope}', {project_sql}"
        f" FROM role r WHERE r.tenant_id = '{tenant}' AND r.code = '{role_code}'"
        " AND r.deleted_at IS NULL RETURNING id",
    )
    return rows[0][0]


async def seed_roles(tenant: UUID) -> Any:
    ctx = RequestContext(tenant_id=tenant, request_id=new_request_id())
    with use_context(ctx):
        async with with_tenant(ctx) as conn:
            return await seed_default_roles(conn)


@pytest.fixture
async def app(tenant_db: TenantDb, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:  # noqa: F811
    await su_execute(tenant_db, SEED_SQL)
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", tenant_db.db.app_url)
    await dispose_engine()
    application = create_app(env="test", tracing=False)
    await sync_catalogue(application.state.access_catalogue)
    for tenant in (TENANT_A_ID, TENANT_B_ID):
        await seed_roles(tenant)
    await su_assign(tenant_db, TENANT_A_ID, ALICE_ID, "tenant_admin")
    await su_assign(tenant_db, TENANT_B_ID, BOB_ID, "tenant_admin")
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
