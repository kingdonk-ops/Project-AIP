"""Fixtures for the PORTAL-01 tests: a migrated database, both fixture tenants, real roles and the
real app with the real ``RoleGrantProvider`` and ``PortalGrantProvider`` (no test grants).

- ``kaefer-demo``: Alice is ``tenant_admin``; ``PADMIN1``/``PADMIN2`` hold a custom
  ``portal_admin`` role (``portal.user.invite``, ``portal.grant.manage``, ``portal.user.view``,
  ``project.view``) on P1/P2 only. Projects P1, P2 (active), P_ARCHIVED; asset ``ROOT`` with
  children ``NODE`` and ``SIBLING``, and ``CHILD`` under ``NODE``.
- ``tenant-b``: Bob is ``tenant_admin``; project ``PB``.

Seeding runs as the superuser; every assertion goes through ``aip_app`` (RLS on) or the API.
Identity's Keycloak work is only queued as ops jobs (nothing runs them here).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    Outbox,
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    _fetch,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    outbox,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

from aip.main import create_app
from aip.modules.access.api import seed_default_roles, sync_catalogue
from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

PADMIN1_ID = UUID("00000000-0000-4000-8000-0000000ad0a1")
PADMIN2_ID = UUID("00000000-0000-4000-8000-0000000ad0a2")
P1 = UUID("00000000-0000-4000-8000-0000000000a1")
P2 = UUID("00000000-0000-4000-8000-0000000000a2")
P_ARCHIVED = UUID("00000000-0000-4000-8000-0000000000a3")
PB = UUID("00000000-0000-4000-8000-0000000000b1")
ROOT = UUID("0192f3c4-0000-7000-8000-000000000001")
NODE = UUID("0192f3c4-0000-7000-8000-000000000002")
SIBLING = UUID("0192f3c4-0000-7000-8000-000000000003")
CHILD = UUID("0192f3c4-0000-7000-8000-000000000004")
PORTAL_ADMIN_ROLE = UUID("00000000-0000-4000-8000-00000000e0a1")

USERS = "/api/v1/admin/portal/users"

SEED_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
    "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
    f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active'), "
    f"('{PADMIN1_ID}', '{TENANT_A_ID}', 'staff', 'pa1@kaefer.test', 'P1 Admin', 'active'), "
    f"('{PADMIN2_ID}', '{TENANT_A_ID}', 'staff', 'pa2@kaefer.test', 'P2 Admin', 'active'), "
    f"('{BOB_ID}', '{TENANT_B_ID}', 'staff', 'bob@acme.test', 'Bob', 'active');"
    "INSERT INTO projects (id, tenant_id, code, name, status) VALUES "
    f"('{P1}', '{TENANT_A_ID}', 'P1', 'Project one', 'active'), "
    f"('{P2}', '{TENANT_A_ID}', 'P2', 'Project two', 'active'), "
    f"('{P_ARCHIVED}', '{TENANT_A_ID}', 'P3', 'Closed project', 'archived'), "
    f"('{PB}', '{TENANT_B_ID}', 'PB', 'Tenant B project', 'active');"
    "INSERT INTO assets (id, tenant_id, parent_id, path, internal_tag, name) VALUES "
    f"('{ROOT}', '{TENANT_A_ID}', NULL, '{ROOT.hex}', 'A-1', 'Plant'), "
    f"('{NODE}', '{TENANT_A_ID}', '{ROOT}', '{ROOT.hex}.{NODE.hex}', 'A-2', 'Unit 1'), "
    f"('{SIBLING}', '{TENANT_A_ID}', '{ROOT}', '{ROOT.hex}.{SIBLING.hex}', 'A-3', 'Unit 2'), "
    f"('{CHILD}', '{TENANT_A_ID}', '{NODE}', '{ROOT.hex}.{NODE.hex}.{CHILD.hex}', 'A-4', 'Pump')"
)

PORTAL_ADMIN_CODES = (
    "portal.user.invite",
    "portal.grant.manage",
    "portal.user.view",
    "project.view",
)


class _PrincipalHeaders(Mapping[str, str]):
    """The test principal header, rebuilt on every read so a stepped-up (aal 2) caller always
    authenticated just now and passes IDENTITY-04's ``step_up()``."""

    def __init__(self, principal: dict[str, Any]) -> None:
        self._principal = principal

    def __getitem__(self, key: str) -> str:
        if key != "x-test-principal":
            raise KeyError(key)
        principal = dict(self._principal)
        if principal["aal"] == 2:
            principal["authenticatedAt"] = datetime.now(UTC).isoformat()
        return json.dumps(principal)

    def __iter__(self) -> Iterator[str]:
        return iter(("x-test-principal",))

    def __len__(self) -> int:
        return 1


def headers(
    tenant: UUID, user: UUID, *, aal: int = 2, user_class: str = "staff"
) -> Mapping[str, str]:
    return _PrincipalHeaders(
        {
            "kind": "user",
            "tenantId": str(tenant),
            "userId": str(user),
            "userClass": user_class,
            "sessionId": None,
            "aal": aal,
            "amr": ["fed"],
        }
    )


ALICE = headers(TENANT_A_ID, ALICE_ID)
ALICE_AAL1 = headers(TENANT_A_ID, ALICE_ID, aal=1)
PADMIN1 = headers(TENANT_A_ID, PADMIN1_ID)
PADMIN2 = headers(TENANT_A_ID, PADMIN2_ID)
BOB = headers(TENANT_B_ID, BOB_ID)


async def su_execute(db: TenantDb, sql: str) -> None:
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await _fetch(db.db.superuser_url, sql, *args)


async def su_count(db: TenantDb, sql: str, *args: object) -> int:
    return int((await su_fetch(db, sql, *args))[0][0])


async def su_assign(
    db: TenantDb, tenant: UUID, user: UUID, role_code: str, project: UUID | None = None
) -> None:
    scope, project_sql = ("project", f"'{project}'") if project else ("tenant", "NULL")
    await su_execute(
        db,
        "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type, project_id)"
        f" SELECT gen_random_uuid(), '{tenant}', '{user}', r.id, '{scope}', {project_sql}"
        f" FROM role r WHERE r.tenant_id = '{tenant}' AND r.code = '{role_code}'"
        " AND r.deleted_at IS NULL",
    )


@asynccontextmanager
async def tenant_tx(tenant: UUID = TENANT_A_ID) -> AsyncIterator[AsyncConnection]:
    """A tenant transaction on the app's engine with a request context (for ``emit``)."""
    ctx = RequestContext(tenant_id=tenant, request_id=new_request_id(), actor_id=ALICE_ID)
    with use_context(ctx):
        async with with_tenant(ctx) as conn:
            yield conn


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
        ctx = RequestContext(tenant_id=tenant, request_id=new_request_id())
        with use_context(ctx):
            async with with_tenant(ctx) as conn:
                await seed_default_roles(conn)
    await su_assign(tenant_db, TENANT_A_ID, ALICE_ID, "tenant_admin")
    await su_assign(tenant_db, TENANT_B_ID, BOB_ID, "tenant_admin")
    values = ", ".join(
        f"(gen_random_uuid(), '{TENANT_A_ID}', '{PORTAL_ADMIN_ROLE}', '{code}')"
        for code in PORTAL_ADMIN_CODES
    )
    await su_execute(
        tenant_db,
        "INSERT INTO role (id, tenant_id, code, name) VALUES "
        f"('{PORTAL_ADMIN_ROLE}', '{TENANT_A_ID}', 'portal_admin', 'Portal admin');"
        f"INSERT INTO role_permission (id, tenant_id, role_id, permission_code) VALUES {values}",
    )
    await su_assign(tenant_db, TENANT_A_ID, PADMIN1_ID, "portal_admin", P1)
    await su_assign(tenant_db, TENANT_A_ID, PADMIN2_ID, "portal_admin", P2)
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


def invite_body(email: str = "client.a@rio.example", **changes: Any) -> dict[str, Any]:
    return {
        "email": email,
        "firstName": "Client",
        "lastName": "A",
        "companyName": "Rio Example Pty Ltd",
        "grants": [{"projectId": str(P1), "actions": ["view", "sign_off"]}],
        **changes,
    }


def new_id() -> UUID:
    return uuid4()
