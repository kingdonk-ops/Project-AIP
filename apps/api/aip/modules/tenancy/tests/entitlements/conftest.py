"""ENT-01 integration fixtures: a migrated database, both fixture tenants and the real app.

Seeding runs as the superuser; every assertion goes through ``aip_app`` (RLS on) or the API.
Permissions come from a test grant provider: alice is tenant A's admin (``tenancy.plan.read``),
bob is tenant B's admin, and carol is a platform operator (``platform.tenants.manage``) whose own
tenant is B. The app's ``EntitlementService`` runs on a clock the tests move.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timedelta
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
from aip.modules.tenancy.entitlements.service import EntitlementService
from aip.platform.access import AccessPrincipal, Grant
from aip.platform.db.engine import dispose_engine

CAROL_ID = UUID("00000000-0000-4000-8000-0000000ca201")  # platform operator (own tenant: B)
START = datetime(2026, 10, 15, 2, 0, tzinfo=UTC)

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


ALICE = stub_headers(TENANT_A_ID, ALICE_ID)  # tenant A admin
BOB = stub_headers(TENANT_B_ID, BOB_ID)  # tenant B admin
CAROL = stub_headers(TENANT_B_ID, CAROL_ID)  # platform operator


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class GrantTable:
    def __init__(self) -> None:
        self.by_user: dict[UUID, set[str]] = {
            ALICE_ID: {"tenancy.plan.read"},
            BOB_ID: {"tenancy.plan.read"},
            CAROL_ID: {"platform.tenants.manage"},
        }

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        held = self.by_user.get(principal.actor_id, set()) if principal.actor_id else set()
        return [Grant(code) for code in sorted(held)]


async def su_execute(db: TenantDb, sql: str) -> None:
    """Seed as the superuser (bypasses RLS: never use it for an assertion on isolation)."""
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await _fetch(db.db.superuser_url, sql, *args)


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await su_execute(tenant_db, SEED_TENANTS_SQL)
    return tenant_db


@pytest.fixture
def grants() -> GrantTable:
    return GrantTable()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def app(
    db: TenantDb, grants: GrantTable, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", db.db.app_url)
    await dispose_engine()
    application = create_app(env="test", tracing=False)
    application.state.access_policy.register(grants)
    application.state.entitlements = EntitlementService(clock=clock)
    yield application
    await dispose_engine()


@pytest.fixture
def service(app: FastAPI) -> EntitlementService:
    return app.state.entitlements


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
