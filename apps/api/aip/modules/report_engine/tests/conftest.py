"""Fixtures for the report_engine integration tests: a migrated database, the two fixture tenants
and the real app with a test grant table.

Seeding runs as the superuser; every assertion goes through ``aip_app`` (RLS on), the API or the
loader (which, like production, connects as ``aip_app`` through ``DATABASE_URL``; the ``app``
fixture points it at the test database). ``report_templates`` is tenant-scoped (plain tenant
isolation), so the only seed needed is the two active tenants. Permissions come from a test grant
provider, so these tests do not depend on role seeding.

REPORTS-02: render jobs read projects, which are project-scoped by RLS (ACCESS-03), so
``scope_users`` gives alice, carol, dave (tenant A) and bob (tenant B) a tenant-scope role
assignment; permissions still come from the grant table. ``render_env`` adds a real object store
(RustFS) and Gotenberg (the STACK-02 capability fixtures) and the ``aip_jobs`` URL the in-process
``pdf`` worker drains the queue with.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    JOBS,
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    _fetch,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)
from tests.platform.capabilities.conftest import (  # noqa: F401 - re-exported fixtures
    S3Backend,
    gotenberg_url,  # pyright: ignore[reportUnusedImport]
    rustfs,  # pyright: ignore[reportUnusedImport]
)

from aip.main import create_app
from aip.platform.access import AccessPrincipal, Grant
from aip.platform.context import RequestContext
from aip.platform.db.engine import dispose_engine

# Tenant-A users for the deny-by-default checks: Carol holds only report.template.view, Dave
# holds nothing.
CAROL_ID = UUID("00000000-0000-4000-8000-0000000ca201")
DAVE_ID = UUID("00000000-0000-4000-8000-0000000da7e1")

ALL_PERMISSIONS = ("report.template.view", "report.template.manage")

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
DAVE = stub_headers(TENANT_A_ID, DAVE_ID)  # tenant A, no report permissions


class GrantTable:
    """Tenant-wide grants per user; tests change ``by_user`` to take permissions away."""

    def __init__(self) -> None:
        self.by_user: dict[UUID, set[str]] = {
            ALICE_ID: set(ALL_PERMISSIONS),
            BOB_ID: set(ALL_PERMISSIONS),
            CAROL_ID: {"report.template.view"},
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


# --- REPORTS-02 ---------------------------------------------------------------------------------

ROLE_A_ID = UUID("00000000-0000-4000-8000-00000000e2a0")
ROLE_B_ID = UUID("00000000-0000-4000-8000-00000000e2b0")
SCOPED_USERS = (
    (TENANT_A_ID, ALICE_ID, "alice@kaefer.test", ROLE_A_ID),
    (TENANT_A_ID, CAROL_ID, "carol@kaefer.test", ROLE_A_ID),
    (TENANT_A_ID, DAVE_ID, "dave@kaefer.test", ROLE_A_ID),
    (TENANT_B_ID, BOB_ID, "bob@acme.test", ROLE_B_ID),
)
# What the render tests hold: alice and bob may render and view projects; carol may render but not
# view the project; dave holds nothing.
RENDER_PERMISSIONS = (*ALL_PERMISSIONS, "report.view", "report.create", "project.view")


@pytest.fixture
async def scope_users(db: TenantDb, grants: GrantTable) -> GrantTable:
    users = ", ".join(
        f"('{user}', '{tenant}', 'staff', '{email}', '{email}', 'active')"
        for tenant, user, email, _ in SCOPED_USERS
    )
    assignments = ", ".join(
        f"(gen_random_uuid(), '{tenant}', '{user}', '{role}', 'tenant')"
        for tenant, user, _, role in SCOPED_USERS
    )
    await su_execute(
        db,
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) "
        f"VALUES {users};"
        "INSERT INTO role (id, tenant_id, code, name) VALUES "
        f"('{ROLE_A_ID}', '{TENANT_A_ID}', 'member', 'Member'), "
        f"('{ROLE_B_ID}', '{TENANT_B_ID}', 'member', 'Member');"
        "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type) "
        f"VALUES {assignments}",
    )
    grants.by_user[ALICE_ID] = set(RENDER_PERMISSIONS)
    grants.by_user[BOB_ID] = set(RENDER_PERMISSIONS)
    grants.by_user[CAROL_ID] = {"report.create", "report.view"}
    grants.by_user.pop(DAVE_ID, None)
    return grants


@dataclass(frozen=True)
class RenderEnv:
    jobs_url: str
    store: S3Backend
    bucket: str


@pytest.fixture
def render_env(
    db: TenantDb,
    rustfs: S3Backend,  # noqa: F811
    gotenberg_url: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> RenderEnv:
    bucket = rustfs.create_bucket()
    for name, value in rustfs.env(bucket).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PDF_RENDERER", "gotenberg")
    monkeypatch.setenv("GOTENBERG_URL", gotenberg_url)
    jobs_url = db.db.role_url(JOBS)
    monkeypatch.setenv("DATABASE_JOBS_URL", jobs_url)
    return RenderEnv(jobs_url=jobs_url, store=rustfs, bucket=bucket)


async def add_project(
    db: TenantDb,
    *,
    tenant: UUID = TENANT_A_ID,
    code: str = "KF-01",
    name: str = "Karratha compressor station",
    timezone: str | None = "Australia/Perth",
) -> UUID:
    project_id = uuid.uuid4()
    zone = "NULL" if timezone is None else f"'{timezone}'"
    await su_execute(
        db,
        "INSERT INTO projects (id, tenant_id, code, name, status, timezone) VALUES "
        f"('{project_id}', '{tenant}', '{code}', '{name}', 'active', {zone})",
    )
    return project_id
