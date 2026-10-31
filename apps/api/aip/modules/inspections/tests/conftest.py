"""Fixtures for the inspections tests: a migrated database, the two fixture tenants, the real app,
and the things an inspection needs in ``kaefer-demo``.

``setup`` installs the APPROVALS-09 ``inspection_standard`` preset (through ``ApprovalsApi``),
creates asset ``TK-101`` (``AssetsApi.create_asset``), projects ``KF-01`` and ``KF-02``, and uploads
and publishes one coating template through the FORMS-01 routes. Grants come from a test grant
provider, as in ``projects/tests/conftest.py``, playing the roles: supervisor, inspector, lead
inspector and viewer. Everyone also holds ``approvals.view``, which the approvals transition service
checks before any lifecycle read or move. Every user has a tenant-scope role assignment, so the
ACCESS-03 project-scope RLS shows them every project's inspections.

Seeding runs as the superuser or through ``aip_app`` with a request context; every assertion goes
through the API or ``aip_app`` (RLS on), except counts the API cannot show (``su_fetch``).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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
    outbox,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

from aip.main import create_app
from aip.modules.approvals.api import ApprovalsApi
from aip.modules.assets.api import AssetCreate, AssetsApi
from aip.modules.inspections import workflow
from aip.platform.access import AccessPrincipal, Grant
from aip.platform.context import RequestContext, use_context
from aip.platform.db.engine import dispose_engine

SUPERVISOR_ID = UUID("00000000-0000-4000-8000-0000000005e1")
INSPECTOR_ID = UUID("00000000-0000-4000-8000-0000000005e2")
LEAD_ID = UUID("00000000-0000-4000-8000-0000000005e3")
VIEWER_ID = UUID("00000000-0000-4000-8000-0000000005e4")
KF_01 = UUID("00000000-0000-4000-8000-00000000af01")
KF_02 = UUID("00000000-0000-4000-8000-00000000af02")
KB_01 = UUID("00000000-0000-4000-8000-00000000bf01")  # tenant B's project

FORMS = {"form.view", "form.manage", "form.publish"}
ASSETS = {"asset.view", "asset.create"}
INSPECTIONS = {"inspection.view", "inspection.create"}
APPROVALS = {"approvals.view", "approvals.start"}
LIFECYCLE = {
    f"approvals.inspection.{verb}"
    for verb in ("assign", "execute", "review", "approve", "client_approve", "retire")
}

SUPERVISOR_GRANTS = {
    *INSPECTIONS,
    "approvals.view",
    "approvals.inspection.assign",
    "approvals.inspection.approve",
}
INSPECTOR_GRANTS = {"inspection.view", "approvals.view", "approvals.inspection.execute"}
LEAD_GRANTS = {"inspection.view", "approvals.view", "approvals.inspection.review"}
VIEWER_GRANTS = {"inspection.view", "approvals.view"}
EVERYTHING = {*FORMS, *ASSETS, *INSPECTIONS, *APPROVALS, *LIFECYCLE}

COATING = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "forms"
        / "tests"
        / "fixtures"
        / "coating-itr-min.json"
    ).read_text("utf-8")
)

SEED_TENANTS_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active')"
)

_USERS_A = (ALICE_ID, SUPERVISOR_ID, INSPECTOR_ID, LEAD_ID, VIEWER_ID)
ROLE_A_ID = UUID("00000000-0000-4000-8000-00000000d0a0")
ROLE_B_ID = UUID("00000000-0000-4000-8000-00000000d0b0")


def _seed_users_sql() -> str:
    users = ", ".join(
        f"('{u}', '{TENANT_A_ID}', 'staff', 'u{i}@kaefer.test', 'User {i}', 'active')"
        for i, u in enumerate(_USERS_A)
    )
    assignments = ", ".join(
        f"(gen_random_uuid(), '{TENANT_A_ID}', '{u}', '{ROLE_A_ID}', 'tenant')" for u in _USERS_A
    )
    return (
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
        f"{users}, ('{BOB_ID}', '{TENANT_B_ID}', 'staff', 'bob@acme.test', 'Bob', 'active');"
        # The supervisor has MFA enrolled, so an aal 1 session must step up (not countersign).
        f"UPDATE app_user SET mfa_enrolled_at = now() WHERE id = '{SUPERVISOR_ID}';"
        "INSERT INTO role (id, tenant_id, code, name) VALUES "
        f"('{ROLE_A_ID}', '{TENANT_A_ID}', 'member', 'Member'), "
        f"('{ROLE_B_ID}', '{TENANT_B_ID}', 'member', 'Member');"
        "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type) VALUES "
        f"{assignments}, (gen_random_uuid(), '{TENANT_B_ID}', '{BOB_ID}', '{ROLE_B_ID}', 'tenant');"
        "INSERT INTO projects (id, tenant_id, code, name, status) VALUES "
        f"('{KF_01}', '{TENANT_A_ID}', 'KF-01', 'Kaefer one', 'active'), "
        f"('{KF_02}', '{TENANT_A_ID}', 'KF-02', 'Kaefer two', 'active'), "
        f"('{KB_01}', '{TENANT_B_ID}', 'KB-01', 'Acme one', 'active')"
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


def signed(user: UUID, tenant: UUID = TENANT_A_ID) -> dict[str, str]:
    """A fresh aal2 (TOTP) session: passes the default sign-off policy (aal 2 within 10 min)."""
    return principal_headers(
        tenant, user, aal=2, amr=["pwd", "otp"], authenticated_at=datetime.now(UTC)
    )


ALICE = principal_headers(TENANT_A_ID, ALICE_ID)  # tenant A, every permission (sets things up)
SUPERVISOR = principal_headers(TENANT_A_ID, SUPERVISOR_ID)
INSPECTOR = principal_headers(TENANT_A_ID, INSPECTOR_ID)
LEAD = principal_headers(TENANT_A_ID, LEAD_ID)
VIEWER = principal_headers(TENANT_A_ID, VIEWER_ID)
BOB = principal_headers(TENANT_B_ID, BOB_ID)  # tenant B, every permission


class GrantTable:
    """Tenant-wide grants per user; tests change ``by_user`` to take permissions away."""

    def __init__(self) -> None:
        self.by_user: dict[UUID, set[str]] = {
            ALICE_ID: set(EVERYTHING),
            SUPERVISOR_ID: set(SUPERVISOR_GRANTS),
            INSPECTOR_ID: set(INSPECTOR_GRANTS),
            LEAD_ID: set(LEAD_GRANTS),
            VIEWER_ID: set(VIEWER_GRANTS),
            BOB_ID: set(EVERYTHING),
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


async def count(db: TenantDb, sql: str, *args: object) -> int:
    return int((await su_fetch(db, sql, *args))[0][0])


@pytest.fixture(autouse=True)
def inspection_hooks() -> Iterator[None]:
    """The real resolver and facts provider (another module's test may have swapped them)."""
    workflow.install()
    yield
    workflow.install()


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await su_execute(tenant_db, SEED_TENANTS_SQL)
    await su_execute(tenant_db, _seed_users_sql())
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


# --- what an inspection needs ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Setup:
    asset_id: UUID
    template_id: UUID
    revision_id: UUID


async def install_preset(db: TenantDb, tenant: UUID = TENANT_A_ID) -> None:
    actor = ALICE_ID if tenant == TENANT_A_ID else BOB_ID
    with use_context(ctx(tenant, actor)):
        async with db.with_tenant(tenant) as conn:
            await ApprovalsApi().install_preset(conn, "inspection_standard")


async def create_asset(db: TenantDb, tag: str = "TK-101", tenant: UUID = TENANT_A_ID) -> UUID:
    actor = ALICE_ID if tenant == TENANT_A_ID else BOB_ID
    with use_context(ctx(tenant, actor)):
        async with db.with_tenant(tenant) as conn:
            asset = await AssetsApi().create_asset(
                conn, actor, AssetCreate(name=f"Tank {tag}", tag_number=tag)
            )
    return asset.id


async def upload_template(
    client: httpx.AsyncClient, code: str = "coating-itr", headers: dict[str, str] = ALICE
) -> tuple[UUID, UUID]:
    """A new template with a draft revision 1; returns (template id, revision id)."""
    body = {"code": code, "name": "Coating ITR", "kind": "inspection", "schema": COATING}
    response = await client.post("/api/v1/forms/templates", json=body, headers=headers)
    assert response.status_code == 201, response.text
    result = response.json()
    return UUID(result["template"]["id"]), UUID(result["revision"]["id"])


async def publish(
    client: httpx.AsyncClient, revision_id: UUID, headers: dict[str, str] = ALICE
) -> None:
    response = await client.post(
        f"/api/v1/forms/revisions/{revision_id}/publish", json={}, headers=headers
    )
    assert response.status_code == 200, response.text


async def new_revision(
    client: httpx.AsyncClient, template_id: UUID, headers: dict[str, str] = ALICE
) -> UUID:
    """Publish the template's next revision (a copy of the current schema); return its id."""
    response = await client.post(
        f"/api/v1/forms/templates/{template_id}/revisions",
        json={"changeNote": "revision 2"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    revision_id = UUID(response.json()["id"])
    await publish(client, revision_id, headers)
    return revision_id


@pytest.fixture
async def setup(client: httpx.AsyncClient, db: TenantDb) -> Setup:
    await install_preset(db)
    asset_id = await create_asset(db)
    template_id, revision_id = await upload_template(client)
    await publish(client, revision_id)
    return Setup(asset_id=asset_id, template_id=template_id, revision_id=revision_id)
