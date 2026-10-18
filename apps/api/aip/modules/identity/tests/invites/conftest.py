"""Fixtures for the IDENTITY-04 integration tests: a migrated database with both fixture tenants,
alice and bob, the login directory, the real app (test principal header, a grant table) and a
way to run identity's jobs as the real ``aip_jobs`` role against a fake Keycloak.

Seeding runs as the superuser or owner; assertions go through ``aip_app`` (RLS on) or the API.
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
from sqlalchemy import text
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
from tests.platform.db.conftest import JOBS

from aip.main import create_app
from aip.modules.identity import jobs as identity_jobs
from aip.modules.identity.keycloak_admin import KeycloakAdmin, KeycloakAdminSettings
from aip.modules.identity.seeds import seed as seed_identity
from aip.modules.ops import api as ops
from aip.platform.access import AccessPrincipal, Grant
from aip.platform.db.engine import EngineSettings, create_app_engine, dispose_engine
from aip.platform.db.session import with_tenant

from ..test_invites_unit import FakeKeycloak

IDENTITY_PERMISSIONS = (
    "identity.user.read",
    "identity.user.manage",
    "identity.signoff_policy.read",
    "identity.signoff_policy.manage",
)

SEED_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
    "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status, sso_managed,"
    " idp_alias) VALUES "
    f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active', true,"
    " 'kaefer-oidc'), "
    f"('{BOB_ID}', '{TENANT_B_ID}', 'staff', 'bob@acme.test', 'Bob', 'active', true, 'acme-oidc')"
)


def principal_headers(
    tenant: UUID, user: UUID, *, aal: int = 2, minutes_ago: float = 1
) -> dict[str, str]:
    """The test principal header: a session that authenticated ``minutes_ago`` at ``aal``."""
    principal = {
        "kind": "user",
        "tenantId": str(tenant),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": aal,
        "amr": ["fed", "mfa"] if aal == 2 else ["fed"],
        "authenticatedAt": (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat(),
    }
    return {"x-test-principal": json.dumps(principal)}


ALICE = principal_headers(TENANT_A_ID, ALICE_ID)
BOB = principal_headers(TENANT_B_ID, BOB_ID)


class GrantTable:
    """Tenant-wide grants per user; tests change ``by_user`` to take permissions away."""

    def __init__(self) -> None:
        self.by_user: dict[UUID, set[str]] = {
            ALICE_ID: set(IDENTITY_PERMISSIONS),
            BOB_ID: set(IDENTITY_PERMISSIONS),
        }

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        held = self.by_user.get(principal.actor_id, set()) if principal.actor_id else set()
        return [Grant(code) for code in sorted(held)]


async def su_execute(db: TenantDb, sql: str) -> None:
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await _fetch(db.db.superuser_url, sql, *args)


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await su_execute(tenant_db, SEED_SQL)
    await seed_identity(tenant_db.db.owner_url, env="test")
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
    monkeypatch.delenv("AIP_TEST_CLOCK_OFFSET", raising=False)
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
def kc() -> FakeKeycloak:
    return FakeKeycloak()


@pytest.fixture
async def kc_admin(kc: FakeKeycloak) -> AsyncIterator[KeycloakAdmin]:
    settings = KeycloakAdminSettings.model_validate(
        {"KEYCLOAK_URL": "https://kc.test", "KEYCLOAK_ADMIN_CLIENT_SECRET": "test_only"}
    )
    admin = KeycloakAdmin(
        settings, http=httpx.AsyncClient(transport=httpx.MockTransport(kc.handler))
    )
    yield admin
    await admin.aclose()


_JOBS = text("SELECT * FROM jobs WHERE job_type = :t AND status = 'queued' ORDER BY created_at, id")


class JobRunner:
    """Runs queued identity jobs the way the worker does: as ``aip_jobs`` inside the tenant."""

    def __init__(self, db: TenantDb, admin: KeycloakAdmin) -> None:
        self.engine = create_app_engine(EngineSettings(url=db.db.role_url(JOBS)))
        self.admin = admin

    async def queued(self, tenant: UUID, job_type: str) -> list[ops.JobView]:
        async with with_tenant(tenant, engine=self.engine) as conn:
            rows = (await conn.execute(_JOBS, {"t": job_type})).mappings().all()
        return [ops.JobView.model_validate(dict(r)) for r in rows]

    async def run(self, tenant: UUID, job: ops.JobView) -> str | None:
        handler = {
            "identity.send_invite": identity_jobs.send_invite,
            "identity.disable_keycloak_user": identity_jobs.disable_keycloak_user,
            "identity.reset_keycloak_mfa": identity_jobs.reset_keycloak_mfa,
        }[job.job_type]
        async with with_tenant(tenant, engine=self.engine) as conn:
            return await handler(conn, job, self.admin)

    async def run_all(self, tenant: UUID, job_type: str) -> int:
        jobs = await self.queued(tenant, job_type)
        for job in jobs:
            await self.run(tenant, job)
        return len(jobs)


@pytest.fixture
async def runner(db: TenantDb, kc_admin: KeycloakAdmin) -> AsyncIterator[JobRunner]:
    r = JobRunner(db, kc_admin)
    yield r
    await r.engine.dispose()
