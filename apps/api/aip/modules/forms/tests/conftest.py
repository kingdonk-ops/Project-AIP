"""Fixtures for the forms integration tests: a migrated database, the two fixture tenants and the
real app with a test grant table.

Seeding runs as the superuser; every assertion goes through ``aip_app`` (RLS on) or the API. The
forms tables are tenant-scoped (plain tenant isolation, no project scope), so the only seed needed
is the two active tenants. Permissions come from a test grant provider, so these tests do not
depend on role seeding. ``ctx``/``db.with_tenant`` let a test call the published interface
(``FormsApi``) directly.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterable
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
from aip.platform.access import AccessPrincipal, Grant
from aip.platform.context import RequestContext
from aip.platform.db.engine import dispose_engine

# A tenant-A user who only ever holds form.view, for the deny-by-default checks.
CAROL_ID = UUID("00000000-0000-4000-8000-0000000ca201")

ALL_PERMISSIONS = ("form.view", "form.manage", "form.publish")

SEED_TENANTS_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active')"
)


def stub_headers(tenant: UUID, user: UUID) -> dict[str, str]:
    principal = {
        "kind": "user",
        "tenantId": str(tenant),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": 1,
        "amr": ["fed"],
    }
    return {"x-test-principal": json.dumps(principal)}


ALICE = stub_headers(TENANT_A_ID, ALICE_ID)  # tenant A (kaefer-demo), all permissions
BOB = stub_headers(TENANT_B_ID, BOB_ID)  # tenant B, all permissions
CAROL = stub_headers(TENANT_A_ID, CAROL_ID)  # tenant A, view only


class GrantTable:
    """Tenant-wide grants per user; tests change ``by_user`` to take permissions away."""

    def __init__(self) -> None:
        self.by_user: dict[UUID, set[str]] = {
            ALICE_ID: set(ALL_PERMISSIONS),
            BOB_ID: set(ALL_PERMISSIONS),
            CAROL_ID: {"form.view"},
        }

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        held = self.by_user.get(principal.actor_id, set()) if principal.actor_id else set()
        return [Grant(code) for code in sorted(held)]


def ctx(tenant: UUID = TENANT_A_ID, actor: UUID | None = ALICE_ID) -> RequestContext:
    return RequestContext(tenant_id=tenant, request_id=f"test-{uuid.uuid4().hex}", actor_id=actor)


async def su_execute(db: TenantDb, sql: str) -> None:
    """Seed as the superuser (bypasses RLS: never use it for an assertion on isolation)."""
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    """Read every tenant's rows as the superuser (for counts the API cannot show)."""
    return await _fetch(db.db.superuser_url, sql, *args)


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await su_execute(tenant_db, SEED_TENANTS_SQL)
    return tenant_db


@pytest.fixture
def grants() -> GrantTable:
    return GrantTable()


@pytest.fixture
async def app(
    db: TenantDb, grants: GrantTable, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", db.db.app_url)
    await dispose_engine()
    application = create_app(env="test", tracing=False)
    application.state.access_policy.register(grants)
    yield application
    await dispose_engine()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def lenient_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Turns an unhandled server error into a 500 response instead of raising it."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
