"""ACCESS-02 integration tests on real Postgres: seeding, the roles and assignments API, the
``RoleGrantProvider`` and the guards. The app connects as ``aip_app`` (RLS on).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.access.api import has_role
from aip.modules.access.roles.cli import _seed as seed_cli  # pyright: ignore[reportPrivateUsage]
from aip.modules.access.roles.default_roles import ROLE_CODES
from aip.modules.access.roles.service import AssignmentService
from aip.platform.access import AccessPrincipal, PolicyService, Resource
from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.session import with_tenant
from aip.platform.http import DomainError

from .conftest import (
    ADMIN2,
    ADMIN2_ID,
    ALICE,
    ALICE_AAL1,
    BOB,
    CAROL,
    CAROL_ID,
    DAVE_ID,
    seed_roles,
    su_assign,
    su_execute,
    su_fetch,
)

ROLES = "/api/v1/access/roles"
ASSIGNMENTS = "/api/v1/access/role-assignments"


async def role_id(client: httpx.AsyncClient, code: str, h: Mapping[str, str] = ALICE) -> str:
    roles = (await client.get(ROLES, headers=h)).json()["items"]
    return next(r["id"] for r in roles if r["code"] == code)


async def new_project(client: httpx.AsyncClient, code: str) -> str:
    response = await client.post(
        "/api/v1/projects", json={"code": code, "name": code}, headers=ALICE
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def assign(
    client: httpx.AsyncClient, user: UUID, code: str, h: Mapping[str, str] = ALICE, **extra: Any
) -> httpx.Response:
    body: dict[str, Any] = {
        "userId": str(user),
        "roleId": await role_id(client, code),
        "scope": {"type": "tenant"},
        **extra,
    }
    return await client.post(ASSIGNMENTS, json=body, headers=h)


async def can(app: FastAPI, user: UUID, action: str, project: str | None = None) -> bool:
    policy: PolicyService = app.state.access_policy
    principal = AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=user)
    resource = Resource(project_id=UUID(project)) if project else None
    return (await policy.can(principal, action, resource)).allowed


async def events(db: TenantDb, name: str) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db, "SELECT payload FROM domain_events WHERE event_name = $1 ORDER BY occurred_at", name
    )
    return [json.loads(row[0]) for row in rows]


# --- seeding ----------------------------------------------------------------------------------


async def test_seeding_twice_gives_eleven_roles_and_the_same_permissions(db: TenantDb) -> None:
    def counts() -> str:
        return (
            "SELECT (SELECT count(*) FROM role WHERE tenant_id = $1 AND deleted_at IS NULL),"
            " (SELECT count(*) FROM role_permission WHERE tenant_id = $1 AND deleted_at IS NULL)"
        )

    before = await su_fetch(db, counts(), TENANT_A_ID)
    report = await seed_roles(TENANT_A_ID)
    assert not report.changed
    after = await su_fetch(db, counts(), TENANT_A_ID)
    assert before == after
    assert after[0][0] == 11
    codes = await su_fetch(
        db, "SELECT code FROM role WHERE tenant_id = $1 AND is_system ORDER BY code", TENANT_A_ID
    )
    assert sorted(c[0] for c in codes) == sorted(ROLE_CODES)


async def test_system_roles_match_the_access_matrix(client: httpx.AsyncClient) -> None:
    roles = {r["code"]: r for r in (await client.get(ROLES, headers=ALICE)).json()["items"]}
    assert set(roles) == set(ROLE_CODES)
    inspector = roles["inspector"]
    assert inspector["isSystem"] is True
    assert inspector["nameTermKey"] == "access.role.inspector.name"
    assert inspector["permissions"] == [
        "approvals.view",
        "asset.create",
        "asset.view",
        "form.view",
        "project.view",
        "report.template.view",
        "site.view",
        "uploads.create",
        "uploads.view",
    ]
    assert "access.role.manage" in roles["tenant_admin"]["permissions"]
    assert "identity.user.manage" in roles["tenant_admin"]["permissions"]
    assert "project.archive" in roles["project_manager"]["permissions"]
    assert "access.role.manage" not in roles["project_manager"]["permissions"]


# --- grants -----------------------------------------------------------------------------------


async def test_a_project_role_grants_only_in_its_project(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    p1, p2 = await new_project(client, "P1"), await new_project(client, "P2")
    scope = {"type": "project", "projectId": p1}
    response = await assign(client, CAROL_ID, "inspector", scope=scope)
    assert response.status_code == 201, response.text
    assert response.json()["scopeType"] == "project"

    assert await can(app, CAROL_ID, "project.view", p1)
    assert not await can(app, CAROL_ID, "project.view", p2)
    assert not await can(app, CAROL_ID, "project.view")  # not tenant-wide

    abilities = await client.get(f"/api/v1/access/me/abilities?projectId={p2}", headers=CAROL)
    assert abilities.json() == {"permissions": []}
    assert (await client.get(f"/api/v1/projects/{p2}", headers=CAROL)).status_code == 403
    assert (await client.get(f"/api/v1/projects/{p1}", headers=CAROL)).status_code == 200


async def test_a_tenant_role_applies_to_every_project(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    p1, p2 = await new_project(client, "P1"), await new_project(client, "P2")
    assert (await assign(client, CAROL_ID, "project_manager")).status_code == 201
    assert await can(app, CAROL_ID, "project.update", p1)
    assert await can(app, CAROL_ID, "project.update", p2)


async def test_an_expired_assignment_grants_nothing(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await su_assign(db, TENANT_A_ID, CAROL_ID, "project_manager")
    assert await can(app, CAROL_ID, "project.view")
    await su_execute(
        db,
        "UPDATE role_assignment SET valid_from = now() - interval '2 days',"
        f" valid_to = now() - interval '1 day' WHERE user_id = '{CAROL_ID}'",
    )
    assert not await can(app, CAROL_ID, "project.view")


async def test_a_deactivated_user_gets_no_grants_and_cannot_be_assigned(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await su_assign(db, TENANT_A_ID, DAVE_ID, "project_manager")
    assert not await can(app, DAVE_ID, "project.view")
    response = await assign(client, DAVE_ID, "inspector")
    assert (response.status_code, response.json()) == (
        422,
        {"code": "USER_INACTIVE", "field": "userId"},
    )


# --- assignment rules -------------------------------------------------------------------------


async def test_assignment_scope_validation(client: httpx.AsyncClient) -> None:
    inspector = await role_id(client, "inspector")
    no_project = {"userId": str(CAROL_ID), "roleId": inspector, "scope": {"type": "project"}}
    assert (await client.post(ASSIGNMENTS, json=no_project, headers=ALICE)).status_code == 422

    team = {"userId": str(CAROL_ID), "roleId": inspector, "scope": {"type": "team"}}
    response = await client.post(ASSIGNMENTS, json=team, headers=ALICE)
    assert (response.status_code, response.json()) == (400, {"code": "SCOPE_NOT_SUPPORTED"})

    missing = {"type": "project", "projectId": "00000000-0000-4000-8000-000000000999"}
    response = await assign(client, CAROL_ID, "inspector", scope=missing)
    assert (response.status_code, response.json()) == (404, {"code": "PROJECT_NOT_FOUND"})


async def test_privileged_roles_need_a_stepped_up_tenant_admin(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    response = await assign(client, CAROL_ID, "tenant_admin", h=ALICE_AAL1)
    assert (response.status_code, response.json()) == (403, {"code": "STEP_UP_REQUIRED"})

    response = await assign(client, CAROL_ID, "tenant_admin")
    assert response.status_code == 201, response.text
    assert response.json()["approvedBy"] == str(ALICE_ID)
    assert response.json()["createdBy"] == str(ALICE_ID)

    # An ordinary role needs no step-up and records no approver.
    response = await assign(client, ADMIN2_ID, "inspector", h=ALICE_AAL1)
    assert response.status_code == 201
    assert response.json()["approvedBy"] is None


async def test_a_role_manager_who_is_not_tenant_admin_cannot_assign_privileged_roles(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    body = {
        "code": "access_admin",
        "name": "Access admin",
        "permissions": ["access.role.read", "access.role_assignment.manage"],
    }
    created = await client.post(ROLES, json=body, headers=ALICE)
    assert created.status_code == 201, created.text
    await su_assign(db, TENANT_A_ID, ADMIN2_ID, "access_admin")
    response = await assign(client, CAROL_ID, "tenant_admin", h=ADMIN2)
    assert (response.status_code, response.json()) == (403, {"code": "TENANT_ADMIN_REQUIRED"})


async def test_the_last_tenant_admin_cannot_be_removed(client: httpx.AsyncClient) -> None:
    listed = await client.get(f"{ASSIGNMENTS}?userId={ALICE_ID}", headers=ALICE)
    (only,) = listed.json()["items"]
    response = await client.delete(f"{ASSIGNMENTS}/{only['id']}", headers=ALICE)
    assert (response.status_code, response.json()) == (409, {"code": "LAST_TENANT_ADMIN"})


async def test_two_admins_removing_each_other_at_once_leaves_one(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    other = await su_assign(db, TENANT_A_ID, ADMIN2_ID, "tenant_admin")
    (mine,) = (await client.get(f"{ASSIGNMENTS}?userId={ALICE_ID}", headers=ALICE)).json()["items"]
    results = await asyncio.gather(
        client.delete(f"{ASSIGNMENTS}/{other}", headers=ALICE),
        client.delete(f"{ASSIGNMENTS}/{mine['id']}", headers=ADMIN2),
    )
    # The loser either lost its own role first (403) or was refused by the guard (409).
    codes = sorted(r.status_code for r in results)
    assert codes in ([204, 403], [204, 409]), [r.text for r in results]
    for loser in results:
        if loser.status_code == 409:
            assert loser.json()["code"] in ("LAST_TENANT_ADMIN", "LAST_ROLE_MANAGER")
    admins = await su_fetch(
        db,
        "SELECT count(*) FROM role_assignment ra JOIN role r ON r.id = ra.role_id"
        " WHERE ra.tenant_id = $1 AND r.code = 'tenant_admin' AND ra.deleted_at IS NULL",
        TENANT_A_ID,
    )
    assert admins[0][0] == 1


async def test_removing_the_last_role_manager_is_refused(client: httpx.AsyncClient) -> None:
    """Alice still holds tenant_admin, but stripping role management from it would lock out."""
    admin_role = await role_id(client, "tenant_admin")
    roles = (await client.get(ROLES, headers=ALICE)).json()["items"]
    held = next(r["permissions"] for r in roles if r["id"] == admin_role)
    without = [code for code in held if code != "access.role.manage"]
    response = await client.patch(
        f"{ROLES}/{admin_role}", json={"permissions": without}, headers=ALICE
    )
    assert (response.status_code, response.json()) == (409, {"code": "LAST_ROLE_MANAGER"})


async def test_another_tenants_user_is_not_found(client: httpx.AsyncClient) -> None:
    body = {
        "userId": str(ALICE_ID),
        "roleId": await role_id(client, "inspector", BOB),
        "scope": {"type": "tenant"},
    }
    response = await client.post(ASSIGNMENTS, json=body, headers=BOB)
    assert (response.status_code, response.json()) == (404, {"code": "USER_NOT_FOUND"})
    # ... and tenant B cannot see or remove tenant A's assignments.
    (alice_admin,) = (await client.get(f"{ASSIGNMENTS}?userId={ALICE_ID}", headers=ALICE)).json()[
        "items"
    ]
    assert (await client.get(f"{ASSIGNMENTS}?userId={ALICE_ID}", headers=BOB)).json() == {
        "items": []
    }
    response = await client.delete(f"{ASSIGNMENTS}/{alice_admin['id']}", headers=BOB)
    assert response.status_code == 404


async def test_assignment_events_are_written_with_the_change(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = (await assign(client, CAROL_ID, "inspector")).json()
    (event,) = await events(db, "access.role_assignment.created")
    assert event["assignmentId"] == created["id"]
    assert (event["userId"], event["roleCode"], event["scopeType"]) == (
        str(CAROL_ID),
        "inspector",
        "tenant",
    )
    assert (await client.delete(f"{ASSIGNMENTS}/{created['id']}", headers=ALICE)).status_code == 204
    (removed,) = await events(db, "access.role_assignment.removed")
    assert removed["assignmentId"] == created["id"]
    versions = await su_fetch(
        db, "SELECT access_version FROM access_settings WHERE tenant_id = $1", TENANT_A_ID
    )
    assert versions[0][0] >= 3  # each change bumps the tenant's access version


async def test_a_valid_to_in_the_past_is_rejected(client: httpx.AsyncClient) -> None:
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    response = await assign(client, CAROL_ID, "inspector", validTo=yesterday)
    assert response.status_code == 422


# --- roles API --------------------------------------------------------------------------------


async def test_editing_a_system_role_customises_it_and_takes_effect(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await su_assign(db, TENANT_A_ID, CAROL_ID, "client_reviewer")
    assert await can(app, CAROL_ID, "project.view")
    reviewer = await role_id(client, "client_reviewer")
    response = await client.patch(
        f"{ROLES}/{reviewer}", json={"permissions": ["site.view"]}, headers=ALICE
    )
    assert response.status_code == 200, response.text
    assert response.json()["customisedAt"] is not None
    assert response.json()["permissions"] == ["site.view"]
    assert not await can(app, CAROL_ID, "project.view")

    (event,) = [e for e in await events(db, "access.role.changed") if e["action"] == "updated"]
    assert event["before"] == [
        "approvals.view",
        "asset.view",
        "project.view",
        "report.template.view",
        "site.view",
        "uploads.view",
    ]
    assert event["after"] == ["site.view"]


async def test_reseeding_leaves_a_customised_role_alone_and_reports_new_codes(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    reviewer = await role_id(client, "client_reviewer")
    await client.patch(f"{ROLES}/{reviewer}", json={"permissions": ["site.view"]}, headers=ALICE)
    # The admin removed project.view on purpose: not reported. A later catalogue code is.
    assert (await seed_roles(TENANT_A_ID)).pending == {}
    await su_execute(
        db,
        "INSERT INTO permission (code, module_id, description, created_at)"
        " VALUES ('project.report.read', 'projects', 'View project reports',"
        " now() + interval '1 second')",
    )
    report = await seed_roles(TENANT_A_ID)
    assert report.pending == {"client_reviewer": ["project.report.read"]}
    assert "inspector" in report.updated  # an uncustomised role picks the new code up
    role = next(
        r for r in (await client.get(ROLES, headers=ALICE)).json()["items"] if r["id"] == reviewer
    )
    assert role["permissions"] == ["site.view"]


async def test_system_codes_are_reserved_and_assignments_are_unique(
    client: httpx.AsyncClient,
) -> None:
    body = {"code": "inspector", "name": "Mine", "permissions": []}
    response = await client.post(ROLES, json=body, headers=ALICE)
    assert (response.status_code, response.json()) == (409, {"code": "ROLE_CODE_TAKEN"})
    assert (await assign(client, CAROL_ID, "inspector")).status_code == 201
    response = await assign(client, CAROL_ID, "inspector")
    assert (response.status_code, response.json()) == (409, {"code": "ASSIGNMENT_EXISTS"})


async def test_an_edit_keeps_deprecated_codes_the_role_holds(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    reviewer = await role_id(client, "client_reviewer")
    await su_execute(db, "UPDATE permission SET deprecated_at = now() WHERE code = 'site.view'")
    response = await client.patch(
        f"{ROLES}/{reviewer}", json={"permissions": ["project.view"]}, headers=ALICE
    )
    assert response.status_code == 200, response.text
    assert response.json()["permissions"] == ["project.view", "site.view"]


async def test_reset_restores_the_defaults(client: httpx.AsyncClient, db: TenantDb) -> None:
    reviewer = await role_id(client, "client_reviewer")
    await client.patch(f"{ROLES}/{reviewer}", json={"permissions": ["site.view"]}, headers=ALICE)
    response = await client.post(f"{ROLES}/{reviewer}/reset", headers=ALICE)
    assert response.status_code == 200, response.text
    assert response.json()["customisedAt"] is None
    assert response.json()["permissions"] == [
        "approvals.view",
        "asset.view",
        "project.view",
        "report.template.view",
        "site.view",
        "uploads.view",
    ]
    (event,) = [e for e in await events(db, "access.role.changed") if e["action"] == "reset"]
    assert (event["before"], event["after"]) == (
        ["site.view"],
        [
            "approvals.view",
            "asset.view",
            "project.view",
            "report.template.view",
            "site.view",
            "uploads.view",
        ],
    )


async def test_system_roles_keep_their_code_and_cannot_be_deleted(
    client: httpx.AsyncClient,
) -> None:
    reviewer = await role_id(client, "client_reviewer")
    for body in ({"code": "reviewer"}, {"name": "Reviewer"}):
        response = await client.patch(f"{ROLES}/{reviewer}", json=body, headers=ALICE)
        assert (response.status_code, response.json()) == (409, {"code": "SYSTEM_ROLE_IMMUTABLE"})
    response = await client.delete(f"{ROLES}/{reviewer}", headers=ALICE)
    assert (response.status_code, response.json()) == (409, {"code": "SYSTEM_ROLE_IMMUTABLE"})


async def test_custom_role_lifecycle(client: httpx.AsyncClient, db: TenantDb) -> None:
    body = {"code": "viewer", "name": "Viewer", "permissions": ["project.view"]}
    created = await client.post(ROLES, json=body, headers=ALICE)
    assert created.status_code == 201, created.text
    viewer = created.json()["id"]
    assert (await client.post(ROLES, json=body, headers=ALICE)).json() == {
        "code": "ROLE_CODE_TAKEN"
    }

    bad = {**body, "code": "bad", "permissions": ["nope.thing.read"]}
    response = await client.post(ROLES, json=bad, headers=ALICE)
    assert response.status_code == 422

    clone = await client.post(
        f"{ROLES}/{await role_id(client, 'inspector')}/clone",
        json={"code": "inspector_plus", "name": "Inspector plus"},
        headers=ALICE,
    )
    assert clone.status_code == 201
    assert clone.json()["isSystem"] is False
    assert clone.json()["permissions"] == [
        "approvals.view",
        "asset.create",
        "asset.view",
        "form.view",
        "project.view",
        "report.template.view",
        "site.view",
        "uploads.create",
        "uploads.view",
    ]

    assignment = (await assign(client, CAROL_ID, "viewer")).json()
    response = await client.delete(f"{ROLES}/{viewer}", headers=ALICE)
    assert (response.status_code, response.json()) == (409, {"code": "ROLE_IN_USE"})
    await client.delete(f"{ASSIGNMENTS}/{assignment['id']}", headers=ALICE)
    assert (await client.delete(f"{ROLES}/{viewer}", headers=ALICE)).status_code == 204
    assert viewer not in [r["id"] for r in (await client.get(ROLES, headers=ALICE)).json()["items"]]


async def test_routes_need_the_role_permissions(client: httpx.AsyncClient) -> None:
    assert (await client.get(ROLES, headers=CAROL)).status_code == 403
    assert (await client.get(ASSIGNMENTS, headers=CAROL)).status_code == 403
    body = {"code": "x_role", "name": "X", "permissions": []}
    assert (await client.post(ROLES, json=body, headers=CAROL)).status_code == 403


@pytest.mark.parametrize("code", ["tenant_admin"])
async def test_tenant_b_sees_only_its_own_roles(client: httpx.AsyncClient, code: str) -> None:
    a = await role_id(client, code, ALICE)
    b = await role_id(client, code, BOB)
    assert a != b
    response = await client.patch(f"{ROLES}/{a}", json={"permissions": []}, headers=BOB)
    assert (response.status_code, response.json()) == (404, {"code": "ROLE_NOT_FOUND"})
    assert BOB_ID  # tenant B's admin exists (seeded in the fixture)


async def test_the_role_lock_serialises_concurrent_admin_removals(db: TenantDb) -> None:
    """Both removals pass their permission checks; the per-tenant lock lets exactly one win."""
    first = await su_fetch(
        db, "SELECT id FROM role_assignment WHERE user_id = $1 AND deleted_at IS NULL", ALICE_ID
    )
    second = await su_assign(db, TENANT_A_ID, ADMIN2_ID, "tenant_admin")

    async def remove(assignment: UUID, actor: UUID) -> str:
        ctx = RequestContext(tenant_id=TENANT_A_ID, request_id=new_request_id(), actor_id=actor)
        with use_context(ctx):
            try:
                admin = AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=actor, aal=2)
                await AssignmentService().delete(assignment, admin)
            except DomainError as exc:
                return exc.code
            return "ok"

    results = await asyncio.gather(remove(second, ALICE_ID), remove(first[0][0], ADMIN2_ID))
    # The loser is refused either as no longer an admin or by the last-admin guard; never both win.
    assert results.count("ok") == 1, results
    assert set(results) - {"ok"} <= {"LAST_TENANT_ADMIN", "TENANT_ADMIN_REQUIRED"}
    admins = await su_fetch(
        db,
        "SELECT count(*) FROM role_assignment ra JOIN role r ON r.id = ra.role_id"
        " WHERE ra.tenant_id = $1 AND r.code = 'tenant_admin' AND ra.deleted_at IS NULL",
        TENANT_A_ID,
    )
    assert admins[0][0] == 1


async def test_the_cli_backfills_a_tenant(db: TenantDb, capsys: pytest.CaptureFixture[str]) -> None:
    await su_execute(db, "UPDATE role SET deleted_at = now() WHERE code = 'auditor'")
    assert await seed_cli([TENANT_A_ID]) == 0
    out = capsys.readouterr().out
    assert f"{TENANT_A_ID}: created 1, updated 0" in out


# --- privileged changes need a stepped-up tenant admin (security review, 2026-10-13) -----------


async def _role_editor(client: httpx.AsyncClient, db: TenantDb) -> None:
    """ADMIN2 holds role and assignment management, but is not tenant_admin."""
    body = {
        "code": "role_editor",
        "name": "Role editor",
        "permissions": ["access.role.read", "access.role.manage", "access.role_assignment.manage"],
    }
    assert (await client.post(ROLES, json=body, headers=ALICE)).status_code == 201
    await su_assign(db, TENANT_A_ID, ADMIN2_ID, "role_editor")


async def test_a_role_editor_cannot_add_privileged_codes_to_a_role(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _role_editor(client, db)
    inspector = await role_id(client, "inspector")
    escalate = {"permissions": ["project.view", "site.view", "identity.user.manage"]}
    response = await client.patch(f"{ROLES}/{inspector}", json=escalate, headers=ADMIN2)
    assert (response.status_code, response.json()) == (403, {"code": "TENANT_ADMIN_REQUIRED"})
    # Ordinary edits stay open to role editors.
    response = await client.patch(
        f"{ROLES}/{inspector}", json={"permissions": ["project.view"]}, headers=ADMIN2
    )
    assert response.status_code == 200

    privileged = {"code": "sneaky", "name": "Sneaky", "permissions": ["identity.user.manage"]}
    response = await client.post(ROLES, json=privileged, headers=ADMIN2)
    assert (response.status_code, response.json()) == (403, {"code": "TENANT_ADMIN_REQUIRED"})
    response = await client.post(
        f"{ROLES}/{await role_id(client, 'tenant_admin')}/clone",
        json={"code": "admin_copy", "name": "Admin copy"},
        headers=ADMIN2,
    )
    assert (response.status_code, response.json()) == (403, {"code": "TENANT_ADMIN_REQUIRED"})


async def test_a_role_editor_cannot_strip_or_reset_a_privileged_role(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _role_editor(client, db)
    admin_role = await role_id(client, "tenant_admin")
    response = await client.patch(f"{ROLES}/{admin_role}", json={"permissions": []}, headers=ADMIN2)
    assert (response.status_code, response.json()) == (403, {"code": "TENANT_ADMIN_REQUIRED"})
    response = await client.post(f"{ROLES}/{admin_role}/reset", headers=ADMIN2)
    assert (response.status_code, response.json()) == (403, {"code": "TENANT_ADMIN_REQUIRED"})


async def test_privileged_role_changes_by_a_tenant_admin_need_step_up(
    client: httpx.AsyncClient,
) -> None:
    inspector = await role_id(client, "inspector")
    escalate = {"permissions": ["project.view", "identity.user.manage"]}
    response = await client.patch(f"{ROLES}/{inspector}", json=escalate, headers=ALICE_AAL1)
    assert (response.status_code, response.json()) == (403, {"code": "STEP_UP_REQUIRED"})
    assert (
        await client.patch(f"{ROLES}/{inspector}", json=escalate, headers=ALICE)
    ).status_code == 200


async def test_only_a_tenant_admin_can_remove_a_privileged_assignment(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _role_editor(client, db)
    other_admin = await su_assign(db, TENANT_A_ID, CAROL_ID, "tenant_admin")
    response = await client.delete(f"{ASSIGNMENTS}/{other_admin}", headers=ADMIN2)
    assert (response.status_code, response.json()) == (403, {"code": "TENANT_ADMIN_REQUIRED"})
    assert (await client.delete(f"{ASSIGNMENTS}/{other_admin}", headers=ALICE)).status_code == 204


@pytest.mark.parametrize("code", ["platform.tenants.manage", "platform.events.manage"])
async def test_no_tenant_role_can_hold_an_operator_permission(
    client: httpx.AsyncClient, code: str
) -> None:
    # ENT-01 security review: a stepped-up tenant admin must not grant themselves operator powers.
    body = {
        "code": "operator_wannabe",
        "name": "Operator",
        "permissions": ["access.role.read", code],
    }
    created = await client.post(ROLES, json=body, headers=ALICE)
    assert created.status_code == 422
    assert created.json() == {
        "code": "OPERATOR_ONLY_PERMISSION",
        "field": "permissions",
        "permissions": [code],
    }

    roles = {r["code"]: r for r in (await client.get(ROLES, headers=ALICE)).json()["items"]}
    admin = roles["tenant_admin"]
    assert not [c for c in admin["permissions"] if c.startswith("platform.")]
    patched = await client.patch(
        f"{ROLES}/{admin['id']}",
        json={"permissions": [*admin["permissions"], code]},
        headers=ALICE,
    )
    assert (patched.status_code, patched.json()["code"]) == (422, "OPERATOR_ONLY_PERMISSION")


# --- TENANCY-03: has_role and the organisation permissions ------------------------------------


async def test_has_role_is_true_only_in_the_assigned_project(client: httpx.AsyncClient) -> None:
    p1, p2 = await new_project(client, "P1"), await new_project(client, "P2")
    scope = {"type": "project", "projectId": p1}
    assert (await assign(client, CAROL_ID, "inspector", scope=scope)).status_code == 201

    async with with_tenant(TENANT_A_ID) as conn:
        assert await has_role(conn, CAROL_ID, "inspector", UUID(p1))
        assert not await has_role(conn, CAROL_ID, "inspector", UUID(p2))
        assert not await has_role(conn, CAROL_ID, "inspector")  # not tenant-wide
        assert not await has_role(conn, CAROL_ID, "project_manager", UUID(p1))


async def test_has_role_with_a_tenant_assignment_holds_in_every_project(
    client: httpx.AsyncClient,
) -> None:
    p1 = await new_project(client, "P1")
    assert (await assign(client, CAROL_ID, "project_manager")).status_code == 201

    async with with_tenant(TENANT_A_ID) as conn:
        assert await has_role(conn, CAROL_ID, "project_manager", UUID(p1))
        assert await has_role(conn, CAROL_ID, "project_manager")
    async with with_tenant(TENANT_B_ID) as conn:  # another tenant sees no assignment
        assert not await has_role(conn, CAROL_ID, "project_manager")


async def test_default_roles_get_the_organisation_permissions(client: httpx.AsyncClient) -> None:
    roles = {r["code"]: r for r in (await client.get(ROLES, headers=ALICE)).json()["items"]}
    admin = set(roles["tenant_admin"]["permissions"])
    manager = set(roles["project_manager"]["permissions"])
    assert {"tenancy.organisation.read", "tenancy.organisation.manage"} <= admin
    assert "tenancy.organisation.read" in manager
    assert "tenancy.organisation.manage" not in manager
    assert "tenancy.organisation.read" not in roles["inspector"]["permissions"]


async def test_has_role_ignores_expired_deleted_and_inactive(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    async def holds(user: UUID, code: str) -> bool:
        async with with_tenant(TENANT_A_ID) as conn:
            return await has_role(conn, user, code)

    await su_assign(db, TENANT_A_ID, DAVE_ID, "supervisor")  # Dave is deactivated
    assert not await holds(DAVE_ID, "supervisor")

    await su_assign(db, TENANT_A_ID, CAROL_ID, "supervisor")
    assert await holds(CAROL_ID, "supervisor")
    await su_execute(
        db,
        "UPDATE role_assignment SET valid_from = now() - interval '2 days',"
        f" valid_to = now() - interval '1 day' WHERE user_id = '{CAROL_ID}'",
    )
    assert not await holds(CAROL_ID, "supervisor")  # expired

    await su_assign(db, TENANT_A_ID, CAROL_ID, "hse_officer")
    await su_execute(
        db, f"UPDATE role_assignment SET deleted_at = now() WHERE user_id = '{CAROL_ID}'"
    )
    assert not await holds(CAROL_ID, "hse_officer")  # assignment soft-deleted

    await su_assign(db, TENANT_A_ID, CAROL_ID, "field_worker")
    assert await holds(CAROL_ID, "field_worker")
    await su_execute(
        db,
        "UPDATE role SET deleted_at = now()"
        f" WHERE tenant_id = '{TENANT_A_ID}' AND code = 'field_worker'",
    )
    assert not await holds(CAROL_ID, "field_worker")  # role soft-deleted


async def test_the_auditor_reads_organisations(client: httpx.AsyncClient) -> None:
    roles = {r["code"]: r for r in (await client.get(ROLES, headers=ALICE)).json()["items"]}
    assert "tenancy.organisation.read" in roles["auditor"]["permissions"]
    assert "tenancy.organisation.manage" not in roles["auditor"]["permissions"]
