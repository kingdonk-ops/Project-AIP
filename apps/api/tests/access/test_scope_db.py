"""ACCESS-03 integration tests on real Postgres: the project-scope RLS and the scope trigger.

Seeding is done as the superuser (bypasses RLS); every assertion connects as ``aip_app`` through
``with_principal`` / ``run_as_system`` (or a bare ``with_tenant`` for the fail-closed case), so what
the database actually enforces is what is checked.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from aip.platform.db.scope import ScopePrincipal, run_as_system, with_principal
from aip.platform.db.session import with_tenant
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # pyright: ignore[reportPrivateUsage]
    TenantDb,
    _execute,
    _fetch,
)

U_ID = UUID("00000000-0000-4000-8000-0000000000c1")  # a kaefer-demo user, project P1 only
P1 = UUID("00000000-0000-4000-8000-0000000001a1")
P2 = UUID("00000000-0000-4000-8000-0000000001a2")
P3 = UUID("00000000-0000-4000-8000-0000000001a3")
PB = UUID("00000000-0000-4000-8000-0000000001b1")  # a tenant-B project
ROLE_A = UUID("00000000-0000-4000-8000-0000000000a0")
ROLE_B = UUID("00000000-0000-4000-8000-0000000000b0")
INSUFFICIENT_PRIVILEGE = "42501"

IDS = text("SELECT id FROM projects ORDER BY code")
COUNT = text("SELECT count(*) FROM projects")


@dataclass
class Scoped:
    db: TenantDb

    async def su(self, sql: str, *args: object) -> list[tuple[object, ...]]:
        return await _fetch(self.db.db.superuser_url, sql, *args)

    async def assign(
        self,
        tenant: UUID,
        user: UUID,
        role: UUID,
        scope_type: str,
        project: UUID | None = None,
        valid_to: str | None = None,
    ) -> UUID:
        project_sql = f"'{project}'" if project else "NULL"
        valid_to_sql = f"now() + interval '{valid_to}'" if valid_to else "NULL"
        rows = await self.su(
            "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type,"
            " project_id, valid_to) VALUES "
            f"(gen_random_uuid(), '{tenant}', '{user}', '{role}', '{scope_type}',"
            f" {project_sql}, {valid_to_sql}) RETURNING id"
        )
        return UUID(str(rows[0][0]))

    async def ids_as(self, principal: ScopePrincipal) -> list[UUID]:
        async with with_principal(principal, engine=self.db.engine) as conn:
            return [UUID(str(r[0])) for r in (await conn.execute(IDS)).all()]


@pytest.fixture
async def scoped(tenant_db: TenantDb) -> AsyncIterator[Scoped]:
    s = Scoped(tenant_db)
    await _execute(
        tenant_db.db.superuser_url,
        "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
        f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'),"
        f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
        f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active'),"
        f"('{U_ID}', '{TENANT_A_ID}', 'staff', 'u@kaefer.test', 'U', 'active');"
        "INSERT INTO role (id, tenant_id, code, name) VALUES "
        f"('{ROLE_A}', '{TENANT_A_ID}', 'inspector', 'Inspector'),"
        f"('{ROLE_B}', '{TENANT_B_ID}', 'inspector', 'Inspector');"
        "INSERT INTO projects (id, tenant_id, code, name) VALUES "
        f"('{P1}', '{TENANT_A_ID}', 'P1', 'Project 1'),"
        f"('{P2}', '{TENANT_A_ID}', 'P2', 'Project 2'),"
        f"('{P3}', '{TENANT_A_ID}', 'P3', 'Project 3'),"
        f"('{PB}', '{TENANT_B_ID}', 'PB', 'Tenant B project')",
    )
    yield s


def user(user_id: UUID, tenant: UUID = TENANT_A_ID) -> ScopePrincipal:
    return ScopePrincipal(tenant, kind="user", user_id=user_id)


async def test_project_scoped_user_sees_only_that_project(scoped: Scoped) -> None:
    await scoped.assign(TENANT_A_ID, U_ID, ROLE_A, "project", project=P1)
    assert await scoped.ids_as(user(U_ID)) == [P1]


async def test_tenant_scoped_user_sees_every_project(scoped: Scoped) -> None:
    await scoped.assign(TENANT_A_ID, ALICE_ID, ROLE_A, "tenant")
    assert await scoped.ids_as(user(ALICE_ID)) == [P1, P2, P3]


async def test_no_user_set_returns_no_projects(scoped: Scoped) -> None:
    await scoped.assign(TENANT_A_ID, ALICE_ID, ROLE_A, "tenant")
    # A bare tenant (no principal) fails closed even though a tenant-scope row exists.
    async with with_tenant(TENANT_A_ID, engine=scoped.db.engine) as conn:
        assert (await conn.execute(COUNT)).scalar_one() == 0


async def test_project_scoped_user_cannot_create_a_project(scoped: Scoped) -> None:
    await scoped.assign(TENANT_A_ID, U_ID, ROLE_A, "project", project=P1)
    with pytest.raises(DBAPIError) as caught:
        async with with_principal(user(U_ID), engine=scoped.db.engine) as conn:
            await conn.execute(
                text(
                    "INSERT INTO projects (id, tenant_id, code, name)"
                    " VALUES (gen_random_uuid(), :tenant, 'NEW', 'New project')"
                ),
                {"tenant": TENANT_A_ID},
            )
    assert getattr(caught.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE


async def test_expired_assignment_stops_being_visible(scoped: Scoped) -> None:
    await scoped.assign(TENANT_A_ID, U_ID, ROLE_A, "project", project=P1, valid_to="1 second")
    assert await scoped.ids_as(user(U_ID)) == [P1]
    await asyncio.sleep(2)
    assert await scoped.ids_as(user(U_ID)) == [], "validity is checked at query time"


async def test_run_as_system_sees_all_projects_in_its_tenant_only(scoped: Scoped) -> None:
    async with run_as_system(TENANT_A_ID, engine=scoped.db.engine) as conn:
        assert [UUID(str(r[0])) for r in (await conn.execute(IDS)).all()] == [P1, P2, P3]
    async with run_as_system(TENANT_B_ID, engine=scoped.db.engine) as conn:
        assert [UUID(str(r[0])) for r in (await conn.execute(IDS)).all()] == [PB]


async def test_api_client_principal_sees_every_project(scoped: Scoped) -> None:
    allowed = await scoped.ids_as(ScopePrincipal(TENANT_A_ID, kind="api_client"))
    assert allowed == [P1, P2, P3]


async def test_soft_deleting_the_assignment_removes_the_scope_row(scoped: Scoped) -> None:
    assignment = await scoped.assign(TENANT_A_ID, U_ID, ROLE_A, "project", project=P1)
    assert await scoped.ids_as(user(U_ID)) == [P1]

    await _execute(
        scoped.db.db.superuser_url,
        f"UPDATE role_assignment SET deleted_at = now() WHERE id = '{assignment}'",
    )
    rows = await scoped.su(
        f"SELECT count(*) FROM access_user_scope WHERE role_assignment_id = '{assignment}'"
    )
    assert rows[0][0] == 0, "the trigger removes the scope row on soft-delete"
    assert await scoped.ids_as(user(U_ID)) == []
