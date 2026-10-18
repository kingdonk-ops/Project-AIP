"""Fixtures for the APPROVALS-02 API tests: a migrated database, the two fixture tenants, the real
app with a test grant table, and the ``demo`` definition published in ``kaefer-demo``.

Seeding runs as the superuser or through ``aip_app`` with a request context; every assertion goes
through the API or ``aip_app`` (RLS on), except counts the API cannot show (``su_fetch``). The
``approvals.demo.*`` codes exist only in these tests: they are added to the app's catalogue here,
not to the manifest.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterable, Iterator
from datetime import UTC, datetime
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
from aip.modules.approvals.api import (
    RecordRef,
    register_record_resolver,
    unregister_record_resolver,
)
from aip.modules.approvals.service import DefinitionsService
from aip.modules.approvals.tests.fixtures import demo_spec
from aip.platform.access import AccessPrincipal, Catalogue, Grant, PermissionDef
from aip.platform.context import RequestContext, use_context
from aip.platform.db.engine import dispose_engine

CAROL_ID = UUID("00000000-0000-4000-8000-0000000ca201")  # tenant A viewer
DAVE_ID = UUID("00000000-0000-4000-8000-0000000da7e0")  # tenant A supervisor

DEMO_PERMISSIONS = tuple(
    f"approvals.demo.{action}" for action in ("submit", "approve", "reject", "resubmit")
)
SUBMITTER = {"approvals.view", "approvals.start", *DEMO_PERMISSIONS}

SEED_TENANTS_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active')"
)


def principal_headers(
    tenant: UUID,
    user: UUID,
    *,
    aal: int = 1,
    amr: list[str] | None = None,
    authenticated_at: datetime | None = None,
) -> dict[str, str]:
    principal: dict[str, Any] = {
        "kind": "user",
        "tenantId": str(tenant),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": aal,
        "amr": ["fed"] if amr is None else amr,
    }
    if authenticated_at is not None:
        principal["authenticatedAt"] = authenticated_at.isoformat()
    return {"x-test-principal": json.dumps(principal)}


def signed(tenant: UUID, user: UUID) -> dict[str, str]:
    """A fresh aal2 (TOTP) session: passes the default sign-off policy (aal 2 within 10 min)."""
    return principal_headers(
        tenant, user, aal=2, amr=["pwd", "otp"], authenticated_at=datetime.now(UTC)
    )


ALICE = principal_headers(TENANT_A_ID, ALICE_ID)  # tenant A submitter
CAROL = principal_headers(TENANT_A_ID, CAROL_ID)  # tenant A viewer
DAVE = principal_headers(TENANT_A_ID, DAVE_ID)  # tenant A supervisor
BOB = principal_headers(TENANT_B_ID, BOB_ID)  # tenant B, with every permission


class GrantTable:
    """Tenant-wide grants per user; tests change ``by_user`` to take permissions away."""

    def __init__(self) -> None:
        self.by_user: dict[UUID, set[str]] = {
            ALICE_ID: set(SUBMITTER),
            CAROL_ID: {"approvals.view"},
            DAVE_ID: set(SUBMITTER),
            BOB_ID: set(SUBMITTER),
        }

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        held = self.by_user.get(principal.actor_id, set()) if principal.actor_id else set()
        return [Grant(code) for code in sorted(held)]


def ctx(tenant: UUID = TENANT_A_ID, actor: UUID | None = ALICE_ID) -> RequestContext:
    return RequestContext(tenant_id=tenant, request_id=f"test-{uuid.uuid4().hex}", actor_id=actor)


async def su_execute(db: TenantDb, sql: str) -> None:
    """Seed or tamper as the superuser (bypasses RLS and grants: never for an isolation check)."""
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await _fetch(db.db.superuser_url, sql, *args)


async def publish(
    db: TenantDb, spec: dict[str, Any], *, tenant: UUID = TENANT_A_ID, key: str = "demo"
) -> UUID:
    """Create and publish a version of ``key`` for record type ``demo``; return its id."""
    definitions = DefinitionsService()
    with use_context(ctx(tenant)):
        async with db.with_tenant(tenant) as conn:
            draft = await definitions.create_draft(conn, key, "demo", spec)
            await definitions.publish(conn, draft.id)
    return draft.id


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await su_execute(tenant_db, SEED_TENANTS_SQL)
    return tenant_db


@pytest.fixture
async def demo(db: TenantDb) -> UUID:
    """The ``demo`` definition (v1) active in both tenants; returns tenant A's id."""
    await publish(db, demo_spec(), tenant=TENANT_B_ID)
    return await publish(db, demo_spec())


class DemoRecords:
    """The test host module's ``demo`` records: every id exists, tenant-wide unless listed."""

    def __init__(self) -> None:
        self.projects: dict[UUID, UUID | None] = {}
        self.missing: set[UUID] = set()

    async def __call__(self, conn: object, record_id: UUID) -> RecordRef | None:
        if record_id in self.missing:
            return None
        return RecordRef(project_id=self.projects.get(record_id))


@pytest.fixture(autouse=True)
def demo_records() -> Iterator[DemoRecords]:
    records = DemoRecords()
    register_record_resolver("demo", records)  # pyright: ignore[reportArgumentType]
    try:
        yield records
    finally:
        unregister_record_resolver("demo")


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
    policy = application.state.access_policy
    extra = [
        PermissionDef(code, "approvals", "test-only demo transition") for code in DEMO_PERMISSIONS
    ]
    policy.catalogue = Catalogue([*policy.catalogue.values(), *extra])
    policy.register(grants)
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


async def start(
    client: httpx.AsyncClient, headers: dict[str, str] | None = None, record_id: UUID | None = None
) -> dict[str, Any]:
    """Start a ``demo`` workflow in tenant A (or the headers' tenant); return the instance."""
    body = {"recordType": "demo", "recordId": str(record_id or uuid.uuid4())}
    response = await client.post("/api/v1/approvals/instances", json=body, headers=headers or ALICE)
    assert response.status_code == 201, response.text
    return response.json()


async def act(
    client: httpx.AsyncClient,
    instance_id: str,
    action: str,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> httpx.Response:
    return await client.post(
        f"/api/v1/approvals/instances/{instance_id}/transition",
        json={"action": action, **extra},
        headers=headers or ALICE,
    )


async def history(
    client: httpx.AsyncClient, instance_id: str, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    response = await client.get(
        f"/api/v1/approvals/instances/{instance_id}/history", headers=headers or ALICE
    )
    assert response.status_code == 200, response.text
    return response.json()
