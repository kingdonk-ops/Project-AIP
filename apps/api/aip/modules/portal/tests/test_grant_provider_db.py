"""PORTAL-01 integration tests: ``PortalGrantProvider`` through the real ``PolicyService``, grant
expiry without a job, project close through the real outbox dispatcher, and fail-closed RLS."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import Outbox, TenantDb

from aip.modules.identity import api as identity
from aip.modules.portal.api import PortalApi, PortalGrantProvider
from aip.platform.access import AccessPrincipal, PolicyService, Resource
from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.events.dispatcher import DispatchSettings, dispatch_batch
from aip.platform.events.subscribers import subscribers

from .conftest import (
    ALICE,
    CHILD,
    NODE,
    P1,
    P2,
    ROOT,
    SIBLING,
    USERS,
    headers,
    invite_body,
    su_assign,
    su_count,
    su_execute,
    su_fetch,
    tenant_tx,
)

PORTAL_ONLY = subscribers.for_modules(["portal"])


def external(user_id: UUID) -> AccessPrincipal:
    return AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=user_id, external=True)


async def invite_active(client: httpx.AsyncClient, **body: Any) -> dict[str, Any]:
    res = await client.post(USERS, json=invite_body(**body), headers=dict(ALICE))
    assert res.status_code == 201, res.text
    created = res.json()
    await sign_in(UUID(created["userId"]))
    return created


async def sign_in(user_id: UUID) -> None:
    """What PORTAL-02's first sign-in does: identity activates, then the portal user."""
    async with tenant_tx() as conn:
        await identity.set_user_status(conn, user_id, "active")
        await PortalApi().mark_signed_in(conn, user_id)


async def can(app: FastAPI, user_id: UUID, code: str, resource: Resource) -> bool:
    policy: PolicyService = app.state.access_policy
    return (await policy.can(external(user_id), code, resource)).allowed


async def provider_grants(user_id: UUID) -> list[Any]:
    return list(await PortalGrantProvider().grants(external(user_id)))


TWO_PROJECTS = [
    {"projectId": str(P1), "actions": ["view", "sign_off"]},
    {"projectId": str(P2), "actions": ["view"]},
]


async def test_a_portal_user_gets_only_their_live_grants(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await invite_active(client, grants=[TWO_PROJECTS[0]])
    user_id = UUID(created["userId"])
    assert await can(app, user_id, "portal.record.view", Resource(project_id=P1))
    assert await can(app, user_id, "portal.record.sign_off", Resource(project_id=P1))
    assert not await can(app, user_id, "portal.record.view", Resource(project_id=P2))
    assert not await can(app, user_id, "portal.record.witness", Resource(project_id=P1))
    assert not await can(app, user_id, "project.view", Resource(project_id=P1))

    # A role assignment row for the portal user never reaches the policy.
    await su_assign(db, TENANT_A_ID, user_id, "project_manager", P1)
    assert not await can(app, user_id, "project.view", Resource(project_id=P1))
    assert await can(app, user_id, "portal.record.view", Resource(project_id=P1))


# Internal routes a portal user must never reach, whatever role rows exist for them.
INTERNAL_ROUTES = (
    ("GET", "/api/v1/projects"),
    ("GET", f"/api/v1/projects/{P1}"),
    ("GET", USERS),
    ("POST", USERS),
    ("POST", f"{USERS}/00000000-0000-4000-8000-000000000001/suspend"),
)


async def test_a_portal_user_is_refused_on_internal_routes(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await invite_active(client, grants=[TWO_PROJECTS[0]])
    user_id = UUID(created["userId"])
    await su_assign(db, TENANT_A_ID, user_id, "tenant_admin")  # a row that must never count
    await su_assign(db, TENANT_A_ID, user_id, "project_manager", P1)
    portal = dict(headers(TENANT_A_ID, user_id, user_class="portal"))
    bodies: dict[str, Any] = {"POST": {"reason": "x"}}
    for method, path in INTERNAL_ROUTES:
        body = invite_body(email="other@rio.example") if path == USERS else bodies.get(method)
        res = await client.request(method, path, json=body, headers=portal)
        # PORTAL-02: an internal route hides itself from a portal user (404, not 403).
        assert (res.status_code, res.json()) == (404, {"code": "NOT_FOUND"}), (method, path)
    assert await su_count(db, "SELECT count(*) FROM portal_users") == 1


async def test_an_internal_user_never_gets_a_portal_grant(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await invite_active(client)
    portal_user_as_internal = AccessPrincipal(TENANT_A_ID, UUID(created["userId"]))
    assert list(await PortalGrantProvider().grants(portal_user_as_internal)) == []

    calls: list[AccessPrincipal] = []
    original = PortalGrantProvider.grants

    async def spy(self: PortalGrantProvider, principal: AccessPrincipal) -> Any:
        calls.append(principal)
        return await original(self, principal)

    monkeypatch.setattr(PortalGrantProvider, "grants", spy)
    policy: PolicyService = app.state.access_policy
    internal = AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=ALICE_ID)
    await policy.can(internal, "portal.record.view", Resource(project_id=P1))
    assert calls == []  # the portal provider is never asked for an internal principal
    await policy.can(external(UUID(created["userId"])), "portal.record.view")
    assert len(calls) == 1


async def test_invited_and_suspended_users_get_nothing(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    res = await client.post(USERS, json=invite_body(), headers=dict(ALICE))
    created = res.json()
    user_id = UUID(created["userId"])
    assert await provider_grants(user_id) == []  # invited: before the first sign-in

    await sign_in(user_id)
    assert len(await provider_grants(user_id)) == 2
    async with tenant_tx() as conn:
        await identity.issue_session(
            conn,
            user_id=user_id,
            user_class="portal",
            aal=2,
            amr=["pwd", "otp"],
            authenticated_at=datetime.now(UTC),
            kc_sid=None,
            audience="portal",  # IDENTITY-10: a portal user holds only portal sessions
        )
    live_sessions = "SELECT count(*) FROM user_session WHERE user_id = $1 AND revoked_at IS NULL"
    assert await su_count(db, live_sessions, user_id) == 1

    suspended = await client.post(
        f"{USERS}/{created['id']}/suspend", json={"reason": "contract ended"}, headers=dict(ALICE)
    )
    assert suspended.status_code == 200, suspended.text
    assert await provider_grants(user_id) == []
    assert await su_count(db, live_sessions, user_id) == 0


async def test_an_asset_subtree_grant_allows_only_its_subtree(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    created = await invite_active(
        client, grants=[{"projectId": str(P1), "assetId": str(NODE), "actions": ["view"]}]
    )
    user_id = UUID(created["userId"])

    def record(path: str | None) -> Resource:
        return Resource(project_id=P1, asset_path=path)

    assert await can(
        app, user_id, "portal.record.view", record(f"{ROOT.hex}.{NODE.hex}.{CHILD.hex}")
    )
    assert not await can(app, user_id, "portal.record.view", record(f"{ROOT.hex}.{SIBLING.hex}"))
    assert not await can(app, user_id, "portal.record.view", record(ROOT.hex))
    assert not await can(app, user_id, "portal.record.view", record(None))


async def test_expiry_needs_no_job_and_renewal_restores_access(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await invite_active(client, grants=TWO_PROJECTS)
    user_id = UUID(created["userId"])
    await su_execute(
        db,
        "UPDATE portal_grants SET expires_at = now() - interval '1 second'"
        f" WHERE project_id = '{P1}'",
    )
    assert not await can(app, user_id, "portal.record.view", Resource(project_id=P1))
    assert await can(app, user_id, "portal.record.view", Resource(project_id=P2))

    await su_execute(db, "UPDATE portal_grants SET expires_at = now() - interval '1 second'")
    assert await provider_grants(user_id) == []
    shown = (await client.get(f"{USERS}/{created['id']}", headers=dict(ALICE))).json()
    assert shown["effectiveStatus"] == "expired"

    p1_grant = next(g["id"] for g in created["grants"] if g["projectId"] == str(P1))
    res = await client.post(f"{USERS}/{created['id']}/grants/{p1_grant}/renew", headers=dict(ALICE))
    assert res.status_code == 200, res.text
    assert await can(app, user_id, "portal.record.view", Resource(project_id=P1))
    async with tenant_tx() as conn:
        live = await PortalApi().live_grants(conn, user_id)
    assert [str(g.id) for g in live] == [p1_grant]


async def test_archiving_a_project_revokes_its_grants_once(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, outbox: Outbox
) -> None:
    created = await invite_active(client, grants=TWO_PROJECTS)
    user_id = UUID(created["userId"])

    async def archive_p1() -> None:
        ctx = RequestContext(tenant_id=TENANT_A_ID, request_id=new_request_id(), actor_id=ALICE_ID)
        with use_context(ctx):
            async with with_tenant(ctx, engine=outbox.app) as conn:
                await emit(
                    conn,
                    "project.archived",
                    1,
                    Aggregate("project", P1),
                    {"projectId": str(P1), "code": "P1", "status": "archived"},
                )
        settings = DispatchSettings(batch_size=100)
        while (await dispatch_batch(outbox.jobs, outbox.app, PORTAL_ONLY, settings)).claimed:
            pass

    await archive_p1()
    rows = await su_fetch(db, "SELECT revoked_reason FROM portal_grants WHERE project_id = $1", P1)
    assert rows == [("project_closed",)]
    revoked = "SELECT count(*) FROM domain_events WHERE event_name = 'portal_grant.revoked'"
    assert await su_count(db, revoked) == 1
    assert not await can(app, user_id, "portal.record.view", Resource(project_id=P1))
    assert await can(app, user_id, "portal.record.view", Resource(project_id=P2))

    await archive_p1()  # redelivery-equivalent: nothing left to revoke
    assert await su_count(db, revoked) == 1


async def test_rls_fails_closed_without_a_tenant(client: httpx.AsyncClient, db: TenantDb) -> None:
    await invite_active(client)
    async with db.no_tenant() as conn:
        grants = (await conn.execute(text("SELECT count(*) FROM portal_grants"))).scalar_one()
        users = (await conn.execute(text("SELECT count(*) FROM portal_users"))).scalar_one()
    assert (grants, users) == (0, 0)
    assert await su_count(db, "SELECT count(*) FROM portal_grants") == 1
