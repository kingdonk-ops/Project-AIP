"""ACCESS-01 integration: startup checks, catalogue sync, deny by default, abilities, version.

Real Postgres (``tenant_db``: a migrated database and an ``aip_app`` engine). Seeding runs as the
superuser (``tests.fixtures.postgres._execute``); every assertion goes through ``aip_app``.
The fixture module packages are described in ``fixtures/README.md``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable, Mapping
from uuid import UUID

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from tests.fixtures.postgres import TenantDb
from tests.fixtures.postgres import _execute as su_execute  # pyright: ignore[reportPrivateUsage]

from aip.main import create_app
from aip.modules.access import repository as repo
from aip.platform.access import (
    AccessPrincipal,
    CatalogueError,
    Grant,
    PolicyService,
    ProjectScope,
    RouteAccessError,
    requires,
)
from aip.platform.context import Principal
from aip.platform.db.engine import dispose_engine

FIXTURES = "aip.modules.access.tests.fixtures"
TENANT_A = UUID("00000000-0000-4000-8000-00000000000a")
TENANT_B = UUID("00000000-0000-4000-8000-00000000000b")
ALICE = UUID("00000000-0000-4000-8000-0000000a11ce")
PROJECT_A1 = UUID("00000000-0000-4000-8000-0000000000a1")

SEED_SQL = f"""
INSERT INTO tenants (id, name, slug, region_code, status) VALUES
  ('{TENANT_A}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'),
  ('{TENANT_B}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');
INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status, sso_managed)
  VALUES ('{ALICE}', '{TENANT_A}', 'staff', 'alice@kaefer.test', 'Alice', 'active', true);
INSERT INTO tenant_membership (id, tenant_id, user_id, membership_type)
  VALUES (gen_random_uuid(), '{TENANT_A}', '{ALICE}', 'member');
"""

ALICE_STUB = {
    "x-test-principal": json.dumps(
        {
            "kind": "user",
            "tenantId": str(TENANT_A),
            "userId": str(ALICE),
            "userClass": "staff",
            "sessionId": None,
            "aal": 1,
            "amr": ["fed"],
        }
    )
}


class TokenResolver:
    """``authorization: Bearer alice`` is alice in tenant A."""

    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        if headers.get("authorization") == "Bearer alice":
            return Principal(tenant_id=TENANT_A, actor_id=ALICE)
        return None


class MutableGrants:
    def __init__(self, *grants: Grant) -> None:
        self.items = list(grants)

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        return list(self.items) if principal.actor_id == ALICE else []


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def policy_of(app: FastAPI) -> PolicyService:
    return app.state.access_policy


@pytest.fixture
async def db(tenant_db: TenantDb, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[TenantDb]:
    await su_execute(tenant_db.db.superuser_url, SEED_SQL)
    monkeypatch.setenv("DATABASE_URL", tenant_db.db.app_url)
    await dispose_engine()
    yield tenant_db
    await dispose_engine()


async def start(app: FastAPI) -> None:
    """Run the lifespan startup (catalogue sync) and shutdown once."""
    async with app.router.lifespan_context(app):
        pass


# --- startup checks (no database) ---------------------------------------------------------------


def test_undeclared_route_stops_create_app() -> None:
    with pytest.raises(RouteAccessError) as exc:
        create_app(f"{FIXTURES}.unguarded", tracing=False)
    assert "GET /api/v1/fixture/unguarded" in str(exc.value)


def test_duplicate_permission_stops_create_app() -> None:
    with pytest.raises(CatalogueError, match=r"duplicate permission fixture\.item\.read"):
        create_app(f"{FIXTURES}.duplicate", tracing=False)


async def test_without_a_database_the_sync_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    await start(create_app(f"{FIXTURES}.guarded", tracing=False))


# --- the permission table -------------------------------------------------------------------------


async def permissions(db: TenantDb) -> dict[str, repo.PermissionRow]:
    async with db.no_tenant() as conn:
        return {row.code: row for row in await repo.list_permissions(conn)}


async def test_sync_mirrors_manifests_and_deprecates_removed_codes(db: TenantDb) -> None:
    await start(create_app(f"{FIXTURES}.guarded", tracing=False))
    rows = await permissions(db)
    assert {"fixture.item.read", "fixture.item.create"} <= set(rows)
    assert rows["fixture.item.create"].deprecated_at is None
    assert rows["fixture.item.read"].module_id == "fixture"

    await start(create_app(f"{FIXTURES}.shrunk", tracing=False))
    rows = await permissions(db)
    assert rows["fixture.item.create"].deprecated_at is not None  # kept, never deleted
    assert rows["fixture.item.read"].deprecated_at is None

    await start(create_app(f"{FIXTURES}.guarded", tracing=False))
    assert (await permissions(db))["fixture.item.create"].deprecated_at is None  # re-declared


async def test_real_app_syncs_the_access_permissions(db: TenantDb) -> None:
    await start(create_app(tracing=False))
    rows = await permissions(db)
    assert rows["access.role.manage"].is_privileged
    assert rows["identity.user.manage"].is_privileged
    assert not rows["access.role.read"].is_privileged


async def test_aip_app_cannot_write_the_permission_table(db: TenantDb) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with db.no_tenant() as conn:
            await conn.execute(
                text(
                    "INSERT INTO permission (code, module_id, description) "
                    "VALUES ('evil.thing.read', 'evil', 'x')"
                )
            )
    for statement in ("UPDATE permission SET description = 'x'", "DELETE FROM permission"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            async with db.no_tenant() as conn:
                await conn.execute(text(statement))


async def test_sync_function_rejects_an_invalid_code(db: TenantDb) -> None:
    bad = [{"code": "Bad.Code", "module_id": "x", "description": "x", "is_privileged": False}]
    with pytest.raises(Exception, match="ck_permission_code"):
        async with db.no_tenant() as conn:
            await repo.sync_permissions(conn, bad)


# --- deny by default over HTTP --------------------------------------------------------------------


@pytest.fixture
async def guarded_app(db: TenantDb) -> FastAPI:
    return create_app(f"{FIXTURES}.guarded", principal_resolver=TokenResolver(), tracing=False)


async def test_requires_route_without_grants_is_403(guarded_app: FastAPI) -> None:
    async with client_for(guarded_app) as c:
        response = await c.get("/api/v1/fixture/items", headers={"authorization": "Bearer alice"})
    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "permission": "fixture.item.read"}


async def test_requires_route_with_a_provider_grant_is_200(guarded_app: FastAPI) -> None:
    policy_of(guarded_app).register(MutableGrants(Grant("fixture.item.read")))
    async with client_for(guarded_app) as c:
        response = await c.get("/api/v1/fixture/items", headers={"authorization": "Bearer alice"})
    assert response.status_code == 200


async def test_a_grant_change_applies_on_the_next_request(guarded_app: FastAPI) -> None:
    """ADR 0020: no logout needed. Grants are never cached across requests here (ACCESS-04)."""
    grants = MutableGrants(Grant("fixture.item.read"))
    policy_of(guarded_app).register(grants)
    headers = {"authorization": "Bearer alice"}
    async with client_for(guarded_app) as c:
        assert (await c.get("/api/v1/fixture/items", headers=headers)).status_code == 200
        grants.items = []  # the role changed
        assert (await c.get("/api/v1/fixture/items", headers=headers)).status_code == 403


# --- the real app: /me, abilities and a requires() route for a user with no roles ---------------


@pytest.fixture
async def real_app(db: TenantDb, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    app = create_app(env="test", tracing=False)

    # A requires() route added after create_app: AccessCheckedRoute is the default route class.
    @app.get("/api/v1/_test/users", dependencies=[Depends(requires("identity.user.read"))])
    async def users() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "yes"}

    return app


async def test_user_without_roles_is_authenticated_but_holds_nothing(real_app: FastAPI) -> None:
    """The ACCESS-01 e2e journey, in process (signed-in alice needs IDENTITY-03 sessions)."""
    async with client_for(real_app) as c:
        assert (await c.get("/api/v1/me", headers=ALICE_STUB)).status_code == 200
        abilities = await c.get("/api/v1/access/me/abilities", headers=ALICE_STUB)
        assert abilities.status_code == 200
        assert abilities.json() == {"permissions": []}
        assert abilities.headers["cache-control"] == "no-store"
        denied = await c.get("/api/v1/_test/users", headers=ALICE_STUB)
        assert denied.status_code == 403
        assert denied.json() == {"code": "FORBIDDEN", "permission": "identity.user.read"}


async def test_abilities_needs_a_principal(real_app: FastAPI) -> None:
    async with client_for(real_app) as c:
        assert (await c.get("/api/v1/access/me/abilities")).status_code == 401


async def test_abilities_lists_tenant_and_project_grants(real_app: FastAPI) -> None:
    policy_of(real_app).register(
        MutableGrants(
            Grant("access.role.read"), Grant("identity.user.read", ProjectScope(PROJECT_A1))
        )
    )
    async with client_for(real_app) as c:
        tenant_wide = await c.get("/api/v1/access/me/abilities", headers=ALICE_STUB)
        in_project = await c.get(
            f"/api/v1/access/me/abilities?projectId={PROJECT_A1}", headers=ALICE_STUB
        )
        allowed = await c.get("/api/v1/_test/users", headers=ALICE_STUB)
    assert tenant_wide.json() == {"permissions": ["access.role.read"]}
    assert in_project.json() == {"permissions": ["access.role.read", "identity.user.read"]}
    assert allowed.status_code == 403  # the route checks tenant-wide; the grant is per project


# --- the access version (ADR 0020) ----------------------------------------------------------------


async def test_access_version_starts_at_1_and_bumps_per_tenant(db: TenantDb) -> None:
    async with db.with_tenant(TENANT_A) as conn:
        assert await repo.get_access_version(conn) == 1
        assert await repo.bump_access_version(conn) == 2
        assert await repo.bump_access_version(conn) == 3
    async with db.with_tenant(TENANT_A) as conn:
        assert await repo.get_access_version(conn) == 3
    async with db.with_tenant(TENANT_B) as conn:
        assert await repo.get_access_version(conn) == 1


async def test_access_version_bump_rolls_back_with_its_transaction(db: TenantDb) -> None:
    with pytest.raises(RuntimeError):
        async with db.with_tenant(TENANT_A) as conn:
            await repo.bump_access_version(conn)
            raise RuntimeError("the role edit failed")
    async with db.with_tenant(TENANT_A) as conn:
        assert await repo.get_access_version(conn) == 1


async def test_access_settings_are_invisible_without_a_tenant(db: TenantDb) -> None:
    async with db.with_tenant(TENANT_A) as conn:
        await repo.bump_access_version(conn)
    async with db.no_tenant() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM access_settings"))).scalar_one()
    assert count == 0


# --- review follow-ups: the sync function's guards and the never-decreasing version -----------


def entry(code: str, module: str = "fixture", privileged: bool = False) -> dict[str, object]:
    return {"code": code, "module_id": module, "description": code, "is_privileged": privileged}


async def test_sync_refuses_an_empty_catalogue(db: TenantDb) -> None:
    with pytest.raises(Exception, match="empty or invalid catalogue"):
        async with db.no_tenant() as conn:
            await repo.sync_permissions(conn, [])


async def test_sync_never_downgrades_a_privileged_permission(db: TenantDb) -> None:
    async with db.no_tenant() as conn:
        await repo.sync_permissions(conn, [entry("fixture.item.delete", privileged=True)])
    with pytest.raises(Exception, match="cannot be downgraded"):
        async with db.no_tenant() as conn:
            await repo.sync_permissions(conn, [entry("fixture.item.delete", privileged=False)])
    assert (await permissions(db))["fixture.item.delete"].is_privileged


async def test_sync_only_deprecates_codes_of_the_modules_it_was_given(db: TenantDb) -> None:
    await start(create_app(tracing=False))  # access, identity, ...
    await start(create_app(f"{FIXTURES}.guarded", tracing=False))  # only the fixture module
    rows = await permissions(db)
    assert rows["access.role.read"].deprecated_at is None
    assert rows["identity.user.read"].deprecated_at is None


async def test_access_version_never_goes_down(db: TenantDb) -> None:
    async with db.with_tenant(TENANT_A) as conn:
        await repo.bump_access_version(conn)
    for statement in (
        "UPDATE access_settings SET access_version = 1",
        "UPDATE access_settings SET deleted_at = now(), access_version = access_version + 1",
    ):
        with pytest.raises(Exception, match=r"access_version must increase|never deleted"):
            async with db.with_tenant(TENANT_A) as conn:
                await conn.execute(text(statement))
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with db.with_tenant(TENANT_A) as conn:
            await conn.execute(text("DELETE FROM access_settings"))
    async with db.with_tenant(TENANT_A) as conn:
        assert await repo.get_access_version(conn) == 2
