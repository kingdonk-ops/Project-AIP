"""Fixtures for the uploads integration tests: a migrated database, a real object store and the app.

Postgres comes from the shared ``tenant_db`` stack; the object store is the STACK-02 RustFS
container (driven by the ``minio`` adapter), reused from the capability conformance fixtures so the
presigned POST hits a real S3-compatible server. Seeding runs as the superuser; every assertion
goes through the API (``aip_app``, RLS on). Permissions come from a project-scoped test grant
provider until ACCESS-02 seeds real roles.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import ALICE_ID, BOB_ID, PROJECT_A1_ID, TENANT_A_ID, TENANT_B_ID
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
from tests.platform.capabilities.conftest import (  # noqa: F401 - re-exported object-store fixture
    S3Backend,
    rustfs,  # pyright: ignore[reportUnusedImport]
)

from aip.main import create_app
from aip.platform.access import AccessPrincipal, Grant, ProjectScope
from aip.platform.db.engine import dispose_engine

# A second project in tenant A (no grant), and a second tenant-A user who is an uploads admin on P1.
PROJECT_A2_ID = UUID("00000000-0000-4000-8000-0000000000a2")
CAROL_ID = UUID("00000000-0000-4000-8000-0000000ca401")

SEED_TENANTS_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status, created_at, updated_at) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active', now(), now()), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active', now(), now())"
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


ALICE = stub_headers(TENANT_A_ID, ALICE_ID)  # tenant A, uploads.create/view on P1
CAROL = stub_headers(TENANT_A_ID, CAROL_ID)  # tenant A, uploads.admin on P1
BOB = stub_headers(TENANT_B_ID, BOB_ID)  # tenant B, no grants


class GrantTable:
    """Project-scoped grants per user, so the P2 case genuinely lacks ``uploads.create``."""

    def __init__(self) -> None:
        self.by_user: dict[UUID, list[Grant]] = {
            ALICE_ID: [
                Grant("uploads.create", ProjectScope(PROJECT_A1_ID)),
                Grant("uploads.view", ProjectScope(PROJECT_A1_ID)),
            ],
            CAROL_ID: [Grant("uploads.admin", ProjectScope(PROJECT_A1_ID))],
        }

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        return list(self.by_user.get(principal.actor_id, [])) if principal.actor_id else []


@dataclass(frozen=True)
class StoreCtx:
    backend: S3Backend
    bucket: str


async def su_execute(db: TenantDb, sql: str) -> None:
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[object, ...]]:
    return await _fetch(db.db.superuser_url, sql, *args)


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await su_execute(tenant_db, SEED_TENANTS_SQL)
    return tenant_db


@pytest.fixture
def grants() -> GrantTable:
    return GrantTable()


@pytest.fixture
def store(rustfs: S3Backend) -> StoreCtx:  # noqa: F811
    return StoreCtx(backend=rustfs, bucket=rustfs.create_bucket())


@pytest.fixture
async def app(
    db: TenantDb, grants: GrantTable, store: StoreCtx, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", db.db.app_url)
    for name, value in store.backend.env(store.bucket).items():
        monkeypatch.setenv(name, value)
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
