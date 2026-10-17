"""ARCH-08: per-tenant release flags (unit, integration and the API journey, real Postgres).

The real app is built with ``AUTH_TEST_STUB`` and the real ``RoleGrantProvider``. ``alice``
(kaefer-demo) holds ``tenant.flags.manage`` through a tenant role; ``carol`` (same tenant, no grant)
and ``bob`` (tenant B) do not. ``GET /api/v1/_fixtures/bim-probe`` is the test-only route guarded by
``requires_flag("bim")``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.main import create_app
from aip.modules.access.api import sync_catalogue
from aip.modules.access.roles.default_roles import default_permissions
from aip.modules.tenancy.api import EntitlementService, FlagEntitlements, SubscriptionPut
from aip.platform.context import RequestContext, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant
from aip.platform.flags import (
    FLAG_CHANGED,
    AllowAllEntitlements,
    FlagService,
    UnknownFlagError,
    known_flags,
    requires_flag,
)
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

CAROL_ID = UUID("00000000-0000-4000-8000-00000000ca01")
ADMIN_ROLE_ID = UUID("00000000-0000-4000-8000-00000000f1a9")
FLAGS = "/api/v1/settings/flags"
PROBE = "/api/v1/_fixtures/bim-probe"

SEED_TENANTS_USERS = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
    "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
    f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active'), "
    f"('{CAROL_ID}', '{TENANT_A_ID}', 'staff', 'carol@kaefer.test', 'Carol', 'active'), "
    f"('{BOB_ID}', '{TENANT_B_ID}', 'staff', 'bob@acme.test', 'Bob', 'active');"
)

# After sync_catalogue: role_permission.permission_code references the permission table.
GRANT_SQL = (
    "INSERT INTO role (id, tenant_id, code, name, is_system) VALUES "
    f"('{ADMIN_ROLE_ID}', '{TENANT_A_ID}', 'flag_admin', 'Flag Admin', false);"
    "INSERT INTO role_permission (id, tenant_id, role_id, permission_code) VALUES "
    f"(gen_random_uuid(), '{TENANT_A_ID}', '{ADMIN_ROLE_ID}', 'tenant.flags.manage');"
    "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type) VALUES "
    f"(gen_random_uuid(), '{TENANT_A_ID}', '{ALICE_ID}', '{ADMIN_ROLE_ID}', 'tenant');"
)


def headers(tenant: UUID, user: UUID) -> dict[str, str]:
    principal = {
        "kind": "user",
        "tenantId": str(tenant),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": 2,
        "amr": ["fed"],
    }
    return {"x-test-principal": json.dumps(principal)}


ALICE = headers(TENANT_A_ID, ALICE_ID)
CAROL = headers(TENANT_A_ID, CAROL_ID)
BOB = headers(TENANT_B_ID, BOB_ID)


def ctx(tenant: UUID, actor: UUID) -> RequestContext:
    return RequestContext(tenant_id=tenant, request_id=f"test-{uuid.uuid4().hex}", actor_id=actor)


class FakeConn:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def execute(self, statement: Any, *args: Any) -> None:
        self.calls.append(statement)


# --- unit -------------------------------------------------------------------------------------


def test_the_registry_knows_the_deferred_module_flags() -> None:
    assert {"bim", "ai"} <= set(known_flags())
    assert known_flags()["bim"] is False


async def test_an_unknown_flag_raises_before_any_sql() -> None:
    conn = FakeConn()
    with pytest.raises(UnknownFlagError):
        await FlagService().is_enabled(cast("AsyncConnection", conn), "no_such_flag")
    assert conn.calls == []


def test_requires_flag_refuses_an_unknown_flag_at_import_time() -> None:
    with pytest.raises(UnknownFlagError):
        requires_flag("no_such_flag")


async def test_the_default_entitlement_hook_allows_everything() -> None:
    assert await AllowAllEntitlements().allows(TENANT_A_ID, "bim") is True


def test_tenant_admin_gets_flag_management_by_default() -> None:
    granted = default_permissions([("tenant.flags.manage", "tenancy")])
    assert "tenant.flags.manage" in granted["tenant_admin"]
    assert "tenant.flags.manage" not in granted["project_manager"]


# --- integration and API journey --------------------------------------------------------------


@pytest.fixture
async def app(tenant_db: TenantDb, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:  # noqa: F811
    await _execute(tenant_db.db.superuser_url, SEED_TENANTS_USERS)
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", tenant_db.db.app_url)
    await dispose_engine()
    application = create_app(env="test", tracing=False)
    await sync_catalogue(application.state.access_catalogue)
    await _execute(tenant_db.db.superuser_url, GRANT_SQL)
    yield application
    await dispose_engine()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def set_flag(tenant: UUID, actor: UUID, flag: str, enabled: bool) -> None:
    with use_context(ctx(tenant, actor)):
        async with with_tenant(tenant) as conn:
            await FlagService().set(conn, flag, enabled)


async def subscribe(tenant: UUID, actor: UUID, add_ons: list[str]) -> None:
    """Give the tenant a live ``core`` subscription with ``add_ons`` (``bim`` adds ``feature.bim``)."""
    body = SubscriptionPut.model_validate(
        {
            "planCode": "core",
            "term": "sandbox",
            "startsOn": "2026-07-01",
            "addOns": add_ons,
            "reason": "test set-up",
        }
    )
    with use_context(ctx(tenant, actor)):
        await EntitlementService().put_subscription(tenant, body)


async def flag_events(db: TenantDb, tenant: UUID) -> list[tuple[Any, ...]]:
    return await _fetch(
        db.db.superuser_url,
        "SELECT payload, actor_id FROM domain_events WHERE tenant_id = $1"
        " AND event_name = $2 ORDER BY occurred_at, id",
        tenant,
        FLAG_CHANGED,
    )


async def test_a_missing_row_is_the_registry_default(app: FastAPI) -> None:
    async with with_tenant(TENANT_A_ID) as conn:
        assert await FlagService().is_enabled(conn, "bim") is False


async def test_the_flagged_route_follows_the_tenant_flag(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    await subscribe(TENANT_A_ID, ALICE_ID, ["bim"])
    await subscribe(TENANT_B_ID, BOB_ID, ["bim"])
    await set_flag(TENANT_A_ID, ALICE_ID, "bim", False)
    assert (await client.get(PROBE, headers=ALICE)).status_code == 404
    before_b = (await client.get(PROBE, headers=BOB)).status_code

    await set_flag(TENANT_A_ID, ALICE_ID, "bim", True)
    assert (await client.get(PROBE, headers=ALICE)).status_code == 200
    assert (await client.get(PROBE, headers=BOB)).status_code == before_b == 404

    await set_flag(TENANT_B_ID, BOB_ID, "bim", True)
    await set_flag(TENANT_A_ID, ALICE_ID, "bim", False)
    assert (await client.get(PROBE, headers=ALICE)).status_code == 404
    assert (await client.get(PROBE, headers=BOB)).status_code == 200


async def test_the_entitlement_hook_can_refuse_a_flag_that_is_on(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    class DenyBim:
        async def allows(self, tenant_id: UUID, flag: str) -> bool:
            return flag != "bim"

    await set_flag(TENANT_A_ID, ALICE_ID, "bim", True)
    app.state.flag_entitlements = DenyBim()
    assert (await client.get(PROBE, headers=ALICE)).status_code == 404


def test_the_app_installs_the_entitlement_hook(app: FastAPI) -> None:
    assert isinstance(app.state.flag_entitlements, FlagEntitlements)


async def test_a_core_tenant_without_the_bim_add_on_never_reaches_the_flagged_route(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    # Review 11 M7 / ENT-01: the flag is on, but core has no feature.bim, so the route stays absent.
    await subscribe(TENANT_A_ID, ALICE_ID, [])
    await set_flag(TENANT_A_ID, ALICE_ID, "bim", True)
    assert (await client.get(PROBE, headers=ALICE)).status_code == 404

    await subscribe(TENANT_A_ID, ALICE_ID, ["bim"])
    assert (await client.get(PROBE, headers=ALICE)).status_code == 200


async def test_a_flag_with_no_feature_key_is_never_entitled(app: FastAPI) -> None:
    await subscribe(TENANT_A_ID, ALICE_ID, ["bim"])
    hook = FlagEntitlements(app)
    assert await hook.allows(TENANT_A_ID, "bim") is True
    assert await hook.allows(TENANT_A_ID, "ai") is False  # no feature.ai anywhere: fails closed


async def test_the_probe_needs_a_principal(client: httpx.AsyncClient) -> None:
    assert (await client.get(PROBE)).status_code == 401


async def test_an_admin_toggles_a_flag_and_one_event_is_written(
    app: FastAPI,
    client: httpx.AsyncClient,
    tenant_db: TenantDb,  # noqa: F811
) -> None:
    put = await client.put(f"{FLAGS}/bim", json={"enabled": True}, headers=ALICE)
    assert put.status_code == 200, put.text
    assert put.json() == {"flag": "bim", "enabled": True}

    listed = await client.get(FLAGS, headers=ALICE)
    assert listed.status_code == 200
    assert {f["flag"]: f["enabled"] for f in listed.json()["flags"]}["bim"] is True

    events = await flag_events(tenant_db, TENANT_A_ID)
    assert len(events) == 1
    payload, actor = events[0]
    body = json.loads(payload) if isinstance(payload, str) else payload
    assert body == {"flag": "bim", "enabled": True}
    assert actor == ALICE_ID

    # Setting the same value again changes nothing and writes no event.
    assert (
        await client.put(f"{FLAGS}/bim", json={"enabled": True}, headers=ALICE)
    ).status_code == 200
    assert len(await flag_events(tenant_db, TENANT_A_ID)) == 1

    off = await client.put(f"{FLAGS}/bim", json={"enabled": False}, headers=ALICE)
    assert off.status_code == 200
    listed = await client.get(FLAGS, headers=ALICE)
    assert {f["flag"]: f["enabled"] for f in listed.json()["flags"]}["bim"] is False
    assert len(await flag_events(tenant_db, TENANT_A_ID)) == 2

    # Tenant B is untouched: still the default, and no event in its outbox.
    listed_b = await client.get(FLAGS, headers=BOB)
    assert {f["flag"]: f["enabled"] for f in listed_b.json()["flags"]}["bim"] is False
    assert await flag_events(tenant_db, TENANT_B_ID) == []


async def test_every_signed_in_user_can_read_flags_but_only_admins_change_them(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get(FLAGS, headers=CAROL)).status_code == 200
    assert (
        await client.put(f"{FLAGS}/bim", json={"enabled": True}, headers=CAROL)
    ).status_code == 403
    assert (
        await client.put(f"{FLAGS}/bim", json={"enabled": True}, headers=BOB)
    ).status_code == 403
    assert (await client.get(FLAGS)).status_code == 401


async def test_an_unknown_flag_is_404_and_a_bad_body_is_422(client: httpx.AsyncClient) -> None:
    unknown = await client.put(f"{FLAGS}/no_such_flag", json={"enabled": True}, headers=ALICE)
    assert unknown.status_code == 404
    bad = await client.put(f"{FLAGS}/bim", json={"enabled": "yes", "extra": 1}, headers=ALICE)
    assert bad.status_code == 422


async def test_concurrent_changes_leave_events_matching_the_stored_value(
    app: FastAPI,
    tenant_db: TenantDb,  # noqa: F811
) -> None:
    await asyncio.gather(
        set_flag(TENANT_A_ID, ALICE_ID, "bim", True),
        set_flag(TENANT_A_ID, ALICE_ID, "bim", False),
        set_flag(TENANT_A_ID, ALICE_ID, "bim", True),
    )
    async with with_tenant(TENANT_A_ID) as conn:
        stored = await FlagService().is_enabled(conn, "bim")
    events = await flag_events(tenant_db, TENANT_A_ID)
    values = [(json.loads(p) if isinstance(p, str) else p)["enabled"] for p, _ in events]
    # Every event is a real change from the value before it, and the last one is what is stored.
    previous = False
    for value in values:
        assert value != previous
        previous = value
    assert previous == stored
