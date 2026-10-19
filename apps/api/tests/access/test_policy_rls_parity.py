"""ACCESS-03 parity property: ``PolicyService`` and the RLS project predicate agree.

For 200 generated assignment configurations (a tenant with 3 projects and 4 users, random tenant/
project assignments with validity windows around now), for every user and project:

(a) if ``PolicyService`` allows the user any ability on the project, the project row is visible to
    that user under RLS (so a policy-allowed action can actually load its row); and
(b) if the project row is visible under RLS, the user holds an active assignment covering it (no
    row leaks past the two layers).

Since every seeded role carries abilities, visibility and policy-allow both coincide with "an active
assignment covers the project", so the test also asserts that stronger equality. A single migrated
database is reused across cases on one event loop: Hypothesis's per-example model does not compose
with the async connection pool here, so the 200 cases are drawn from a seeded ``random.Random``
(the seed is in each assertion message). Disabling the scope trigger (a seeded fault) breaks parity.
"""

from __future__ import annotations

import os
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy import text

from aip.modules.access.tests.roles.conftest import app, db  # noqa: F401 - reused fixtures
from aip.platform.access import AccessPrincipal, PolicyService, Resource
from aip.platform.db.scope import ScopePrincipal, with_principal
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import (  # pyright: ignore[reportPrivateUsage]
    TenantDb,
    _execute,
    _fetch,
)

CASES = 200
SEED = 0xACCE5503

USER_IDS = tuple(UUID(f"00000000-0000-4000-8000-0000000e000{i}") for i in range(4))
PROJECT_IDS = tuple(UUID(f"00000000-0000-4000-8000-0000000f000{i}") for i in range(3))

_STATES = ("active", "expired", "future")
_VALIDITY = {
    "active": ("now() - interval '1 hour'", "NULL"),
    "expired": ("now() - interval '2 hours'", "now() - interval '1 hour'"),
    "future": ("now() + interval '1 hour'", "NULL"),
}


@dataclass(frozen=True)
class Assignment:
    user: UUID
    scope_type: str  # 'tenant' | 'project'
    project: UUID | None
    state: str


@dataclass
class World:
    db: TenantDb
    policy: PolicyService
    role_id: UUID

    async def apply(self, assignments: list[Assignment]) -> None:
        await _execute(
            self.db.db.superuser_url, "DELETE FROM role_assignment"
        )  # trigger clears scope
        if not assignments:
            return
        values = ",".join(
            "(gen_random_uuid(), '{t}', '{u}', '{r}', '{s}', {p}, {vf}, {vt})".format(
                t=TENANT_A_ID,
                u=a.user,
                r=self.role_id,
                s=a.scope_type,
                p=f"'{a.project}'" if a.project else "NULL",
                vf=_VALIDITY[a.state][0],
                vt=_VALIDITY[a.state][1],
            )
            for a in assignments
        )
        await _execute(
            self.db.db.superuser_url,
            "INSERT INTO role_assignment"
            " (id, tenant_id, user_id, role_id, scope_type, project_id, valid_from, valid_to)"
            f" VALUES {values}",
        )

    async def rls_visible(self, user: UUID) -> set[UUID]:
        principal = ScopePrincipal(TENANT_A_ID, kind="user", user_id=user)
        async with with_principal(principal, engine=self.db.engine) as conn:
            rows = (await conn.execute(text("SELECT id FROM projects"))).all()
        return {UUID(str(r[0])) for r in rows}

    async def policy_allows_any(self, user: UUID, project: UUID) -> bool:
        principal = AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=user, kind="user")
        abilities = await self.policy.allowed_permissions(principal, Resource(project_id=project))
        return bool(abilities)


def covering(assignments: list[Assignment], user: UUID, project: UUID) -> bool:
    return any(
        a.user == user
        and a.state == "active"
        and (a.scope_type == "tenant" or a.project == project)
        for a in assignments
    )


def generate(rng: random.Random) -> list[Assignment]:
    assignments: list[Assignment] = []
    for user in USER_IDS:
        if rng.random() < 0.4:
            assignments.append(Assignment(user, "tenant", None, rng.choice(_STATES)))
        for project in PROJECT_IDS:
            if rng.random() < 0.4:
                assignments.append(Assignment(user, "project", project, rng.choice(_STATES)))
    return assignments


@pytest.fixture
async def world(app: object, db: TenantDb) -> AsyncIterator[World]:  # noqa: F811
    policy: PolicyService = app.state.access_policy  # pyright: ignore[reportAttributeAccessIssue]
    await _execute(
        db.db.superuser_url,
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
        + ",".join(
            f"('{u}', '{TENANT_A_ID}', 'staff', 'parity{i}@kaefer.test', 'Parity {i}', 'active')"
            for i, u in enumerate(USER_IDS)
        )
        + ";INSERT INTO projects (id, tenant_id, code, name) VALUES "
        + ",".join(
            f"('{p}', '{TENANT_A_ID}', 'PP{i}', 'Parity project {i}')"
            for i, p in enumerate(PROJECT_IDS)
        ),
    )
    rows = await _fetch(
        db.db.superuser_url,
        f"SELECT id FROM role WHERE tenant_id = '{TENANT_A_ID}' AND code = 'inspector'",
    )
    assert os.environ.get("DATABASE_URL"), "RoleGrantProvider needs DATABASE_URL"
    yield World(db=db, policy=policy, role_id=UUID(str(rows[0][0])))


async def test_policy_and_rls_agree_across_generated_cases(world: World) -> None:
    rng = random.Random(SEED)
    for case in range(CASES):
        assignments = generate(rng)
        await world.apply(assignments)
        for user in USER_IDS:
            visible = await world.rls_visible(user)
            for project in PROJECT_IDS:
                is_visible = project in visible
                covers = covering(assignments, user, project)
                allowed = await world.policy_allows_any(user, project)
                context = f"case={case} seed={SEED:#x} user={user} project={project}"
                # (b) nothing is visible without a real active assignment covering it.
                assert is_visible == covers, (
                    f"RLS visibility must match an active assignment: {context}"
                )
                # (a) a policy-allowed action can load its row.
                assert not allowed or is_visible, f"policy allows but RLS hides the row: {context}"


async def test_seeded_fault_disabling_the_trigger_breaks_parity(world: World) -> None:
    await _execute(
        world.db.db.superuser_url,
        "ALTER TABLE role_assignment DISABLE TRIGGER trg_access_user_scope_sync",
    )
    # With the trigger off, a fresh tenant-scope assignment leaves no scope row, so the project is
    # invisible though the user is clearly covered: the parity property (a) fails.
    await world.apply([Assignment(USER_IDS[0], "tenant", None, "active")])
    visible = await world.rls_visible(USER_IDS[0])
    allowed = await world.policy_allows_any(USER_IDS[0], PROJECT_IDS[0])
    assert allowed and PROJECT_IDS[0] not in visible, (
        "the seeded fault must break parity: policy allows but RLS hides every project"
    )
