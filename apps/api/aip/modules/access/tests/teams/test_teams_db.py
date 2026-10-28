"""ACCESS-04 integration tests on real Postgres (and Redis where named): teams, membership, team
role assignments, the policy cache and its invalidation events. The app connects as ``aip_app``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from tests.conftest import BOB_ID, TENANT_A_ID
from tests.fixtures.postgres import Outbox, TenantDb
from tests.fixtures.redis import RedisServer

from aip.modules.access.api import RoleGrantProvider, configure_policy_cache, list_team_members
from aip.modules.access.api import teams_for_user as teams_for_user_api
from aip.modules.access.policy_cache import RedisPolicyCache, version_key
from aip.platform.access import AccessPrincipal, PolicyService, Resource
from aip.platform.context import RequestContext, use_context
from aip.platform.db.scope import ScopePrincipal, with_principal
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, DictEventSchemaLookup, emit
from aip.platform.events.dispatcher import DispatchSettings, dispatch_batch
from aip.platform.events.subscribers import subscribers

from ..roles.conftest import ALICE, BOB, CAROL, CAROL_ID, su_fetch

ROLES = "/api/v1/access/roles"
ASSIGNMENTS = "/api/v1/access/role-assignments"
TEAMS = "/api/v1/access/teams"
ACCESS_ONLY = subscribers.for_modules(["access"])


class _Free(BaseModel):
    model_config = ConfigDict(extra="allow")


async def role_id(client: httpx.AsyncClient, code: str) -> str:
    roles = (await client.get(ROLES, headers=ALICE)).json()["items"]
    return next(r["id"] for r in roles if r["code"] == code)


async def new_project(client: httpx.AsyncClient, code: str) -> str:
    response = await client.post(
        "/api/v1/projects", json={"code": code, "name": code}, headers=ALICE
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def new_team(
    client: httpx.AsyncClient,
    name: str,
    project: str | None = None,
    h: Mapping[str, str] = ALICE,
) -> httpx.Response:
    body: dict[str, Any] = {"name": name, "teamType": "internal"}
    if project is not None:
        body["projectId"] = project
    return await client.post(TEAMS, json=body, headers=h)


async def add_members(
    client: httpx.AsyncClient, team: str, users: Iterable[UUID], h: Mapping[str, str] = ALICE
) -> httpx.Response:
    body = {"userIds": [str(u) for u in users]}
    return await client.post(f"{TEAMS}/{team}/members", json=body, headers=h)


async def assign_team(client: httpx.AsyncClient, team: str, code: str) -> httpx.Response:
    body = {"roleId": await role_id(client, code), "scope": {"type": "team", "teamId": team}}
    return await client.post(ASSIGNMENTS, json=body, headers=ALICE)


async def inspector_team(client: httpx.AsyncClient) -> tuple[str, str]:
    """Project P1 and a team on it holding ``inspector``; returns (project, team)."""
    p1 = await new_project(client, "P1")
    created = await new_team(client, "Inspectors", p1)
    assert created.status_code == 201, created.text
    team = created.json()["id"]
    response = await assign_team(client, team, "inspector")
    assert response.status_code == 201, response.text
    assert response.json()["userId"] is None
    return p1, team


async def can(policy: PolicyService, user: UUID, action: str, project: str | None) -> bool:
    principal = AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=user)
    resource = Resource(project_id=UUID(project)) if project else None
    return (await policy.can(principal, action, resource)).allowed


async def events(db: TenantDb, name: str) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db, "SELECT payload FROM domain_events WHERE event_name = $1 ORDER BY occurred_at", name
    )
    return [json.loads(row[0]) for row in rows]


async def dispatch_all(outbox: Outbox) -> None:
    settings = DispatchSettings(batch_size=100)
    while (await dispatch_batch(outbox.jobs, outbox.app, ACCESS_ONLY, settings)).claimed:
        pass


# --- grants through a team ----------------------------------------------------------------------


async def test_a_team_role_follows_membership(app: FastAPI, client: httpx.AsyncClient) -> None:
    policy: PolicyService = app.state.access_policy
    p1, team = await inspector_team(client)
    assert not await can(policy, CAROL_ID, "project.view", p1)

    assert (await add_members(client, team, [CAROL_ID])).status_code == 200
    assert await can(policy, CAROL_ID, "project.view", p1)
    assert not await can(policy, CAROL_ID, "project.view", None)  # project scope only

    removed = await client.delete(f"{TEAMS}/{team}/members/{CAROL_ID}", headers=ALICE)
    assert removed.status_code == 204, removed.text
    assert not await can(policy, CAROL_ID, "project.view", p1)  # the next call, not stale


async def test_a_team_member_selects_the_project_under_rls(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    p1, team = await inspector_team(client)
    await new_project(client, "P2")
    principal = ScopePrincipal(TENANT_A_ID, kind="user", user_id=CAROL_ID)
    query = text("SELECT id FROM projects ORDER BY code")

    async with with_principal(principal, engine=db.engine) as conn:
        assert (await conn.execute(query)).all() == []
    assert (await add_members(client, team, [CAROL_ID])).status_code == 200
    async with with_principal(principal, engine=db.engine) as conn:
        assert [str(r[0]) for r in (await conn.execute(query)).all()] == [p1]
    await client.delete(f"{TEAMS}/{team}/members/{CAROL_ID}", headers=ALICE)
    async with with_principal(principal, engine=db.engine) as conn:
        assert (await conn.execute(query)).all() == []


async def test_the_published_team_lookups(client: httpx.AsyncClient, db: TenantDb) -> None:
    p1, team = await inspector_team(client)
    await add_members(client, team, [CAROL_ID])
    async with db.with_tenant(TENANT_A_ID) as conn:
        assert await list_team_members(conn, UUID(team)) == [CAROL_ID]
        (ref,) = await teams_for_user_api(conn, CAROL_ID)
    assert (str(ref.id), ref.name, str(ref.project_id)) == (team, "Inspectors", p1)


# --- teams API ----------------------------------------------------------------------------------


async def test_a_duplicate_team_name_in_a_project_is_refused(client: httpx.AsyncClient) -> None:
    p1, p2 = await new_project(client, "P1"), await new_project(client, "P2")
    assert (await new_team(client, "Crew", p1)).status_code == 201
    duplicate = await new_team(client, "crew", p1)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "TEAM_NAME_TAKEN"
    assert (await new_team(client, "Crew", p2)).status_code == 201  # another project
    assert (await new_team(client, "Crew")).status_code == 201  # tenant level
    assert (await new_team(client, "CREW")).status_code == 409  # one tenant-level bucket


async def test_adding_a_member_writes_a_membership_event(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    _, team = await inspector_team(client)
    assert (await add_members(client, team, [CAROL_ID])).status_code == 200
    (event,) = await events(db, "team.membership_changed")
    assert event == {"teamId": team, "userIds": [str(CAROL_ID)], "change": "added"}
    assert (await add_members(client, team, [CAROL_ID])).status_code == 200  # already in
    assert len(await events(db, "team.membership_changed")) == 1


async def test_a_role_edit_invalidates_the_whole_tenant(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    inspector = await role_id(client, "inspector")
    roles = (await client.get(ROLES, headers=ALICE)).json()["items"]
    current = next(r["permissions"] for r in roles if r["id"] == inspector)
    patch = {"permissions": [p for p in current if p != "form.view"]}
    response = await client.patch(f"{ROLES}/{inspector}", json=patch, headers=ALICE)
    assert response.status_code == 200, response.text
    assert {"userIds": None} in await events(db, "access.grants_changed")


async def test_another_tenants_user_cannot_be_added(client: httpx.AsyncClient) -> None:
    _, team = await inspector_team(client)
    response = await add_members(client, team, [BOB_ID])
    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


async def test_tenant_b_cannot_add_a_tenant_a_user_to_its_team(client: httpx.AsyncClient) -> None:
    created = await new_team(client, "B team", h=BOB)
    assert created.status_code == 201, created.text
    response = await add_members(client, created.json()["id"], [CAROL_ID], h=BOB)
    assert response.status_code == 404


async def test_tenant_b_cannot_see_tenant_a_teams(client: httpx.AsyncClient) -> None:
    _, team = await inspector_team(client)
    assert (await client.get(f"{TEAMS}/{team}/members", headers=BOB)).status_code == 404
    assert (await add_members(client, team, [BOB_ID], h=BOB)).status_code == 404
    assert (await client.get(TEAMS, headers=BOB)).json()["items"] == []


async def test_managing_teams_needs_the_permission(client: httpx.AsyncClient) -> None:
    assert (await new_team(client, "Mine", h=CAROL)).status_code == 403
    assert (await client.get(TEAMS, headers=CAROL)).json()["items"] == []


async def test_deleting_a_team_removes_its_grants(app: FastAPI, client: httpx.AsyncClient) -> None:
    policy: PolicyService = app.state.access_policy
    p1, team = await inspector_team(client)
    await add_members(client, team, [CAROL_ID])
    assert await can(policy, CAROL_ID, "project.view", p1)
    assert (await client.delete(f"{TEAMS}/{team}", headers=ALICE)).status_code == 204
    assert not await can(policy, CAROL_ID, "project.view", p1)
    assignments = (await client.get(f"{ASSIGNMENTS}?teamId={team}", headers=ALICE)).json()
    assert assignments["items"] == []


# --- user.deactivated ---------------------------------------------------------------------------


async def test_a_deactivated_user_loses_every_membership(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, outbox: Outbox
) -> None:
    policy: PolicyService = app.state.access_policy
    p1, team = await inspector_team(client)
    await add_members(client, team, [CAROL_ID])
    assert await can(policy, CAROL_ID, "project.view", p1)

    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id=f"test-{uuid4().hex}")
    schemas = DictEventSchemaLookup({("user.deactivated", 1): _Free})
    async with use_context(ctx), with_tenant(ctx, engine=outbox.app) as conn:
        payload = {"userId": str(CAROL_ID)}
        agg = Aggregate("user", CAROL_ID)
        await emit(conn, "user.deactivated", 1, agg, payload, schemas=schemas)
    await dispatch_all(outbox)

    rows = await su_fetch(
        db, "SELECT deleted_at IS NOT NULL FROM team_member WHERE user_id = $1", CAROL_ID
    )
    assert rows == [(True,)]
    assert not await can(policy, CAROL_ID, "project.view", p1)
    removed = [e for e in await events(db, "team.membership_changed") if e["change"] == "removed"]
    assert removed == [{"teamId": team, "userIds": [str(CAROL_ID)], "change": "removed"}]


# --- the cross-instance cache -------------------------------------------------------------------


class _LostBump(RedisPolicyCache):
    """Instance 1: caches like the real one, but its after-commit bump never reaches Redis."""

    async def bump(self, tenant_id: UUID, user_ids: Iterable[UUID] | None) -> None:
        return None


async def test_another_instance_sees_a_removal_after_one_dispatch(
    app: FastAPI, client: httpx.AsyncClient, outbox: Outbox, redis_server: RedisServer
) -> None:
    configure_policy_cache(RedisPolicyCache.from_url(redis_server.url))
    p1, team = await inspector_team(client)
    await add_members(client, team, [CAROL_ID])

    instance2 = PolicyService(app.state.access_policy.catalogue)
    instance2.register(RoleGrantProvider(RedisPolicyCache.from_url(redis_server.url)))
    assert await can(instance2, CAROL_ID, "project.view", p1)  # cached in Redis now

    configure_policy_cache(_LostBump.from_url(redis_server.url))  # instance 1's bump is lost
    removed = await client.delete(f"{TEAMS}/{team}/members/{CAROL_ID}", headers=ALICE)
    assert removed.status_code == 204
    assert await can(instance2, CAROL_ID, "project.view", p1)  # stale until dispatch

    configure_policy_cache(RedisPolicyCache.from_url(redis_server.url))  # the dispatcher's
    await dispatch_all(outbox)
    assert not await can(instance2, CAROL_ID, "project.view", p1)


async def test_the_writing_instance_reads_its_own_change(
    app: FastAPI, client: httpx.AsyncClient, redis_server: RedisServer
) -> None:
    cache = RedisPolicyCache.from_url(redis_server.url)
    configure_policy_cache(cache)
    policy: PolicyService = app.state.access_policy
    p1, team = await inspector_team(client)
    await add_members(client, team, [CAROL_ID])
    assert await can(policy, CAROL_ID, "project.view", p1)  # cached

    before = await cache.versions(TENANT_A_ID, CAROL_ID)
    await client.delete(f"{TEAMS}/{team}/members/{CAROL_ID}", headers=ALICE)
    after = await cache.versions(TENANT_A_ID, CAROL_ID)
    assert before is not None and after is not None and after[0] > before[0]
    assert not await can(policy, CAROL_ID, "project.view", p1)  # no dispatcher needed
    assert version_key(TENANT_A_ID, CAROL_ID).endswith(f":access:ver:{CAROL_ID}")
