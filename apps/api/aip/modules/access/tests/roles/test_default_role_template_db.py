"""ACCESS-09 integration tests on real Postgres: the operator's default role template (ADR 0042).

The app connects as ``aip_app`` (RLS on). Tenant users get their grants from their roles as in
production; the platform operator (tenant B, no role) gets ``platform.roles.manage`` from a test
grant provider, since until OPS-12 nobody holds a ``platform.*`` code in a running deployment.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    _fetch,  # pyright: ignore[reportPrivateUsage]
)

from aip.modules.access.roles.default_roles import MATRIX, ROLE_CODES
from aip.platform.access import AccessPrincipal, Grant

from .conftest import ALICE, headers, seed_roles, su_execute, su_fetch

TEMPLATE = "/api/v1/platform/default-roles"
ROLES = "/api/v1/access/roles"
OPERATOR_ID = UUID("00000000-0000-4000-8000-0000000c0e09")
OPERATOR = headers(TENANT_B_ID, OPERATOR_ID)
OPERATOR_GRANTS = {"platform.roles.manage"}
TENANT_C_ID = UUID("00000000-0000-4000-8000-00000000c009")


class _OperatorGrants:
    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        if principal.actor_id == OPERATOR_ID:
            return [Grant(code) for code in sorted(OPERATOR_GRANTS)]
        return []


@pytest.fixture
def operator(app: FastAPI) -> None:
    app.state.access_policy.register(_OperatorGrants())


def shipped(module: str, role: str) -> str:
    return MATRIX[module][ROLE_CODES.index(role)]


async def patch(
    client: httpx.AsyncClient, changes: list[dict[str, str]], reason: str = "ops review"
) -> httpx.Response:
    return await client.patch(
        TEMPLATE, json={"changes": changes, "reason": reason}, headers=OPERATOR
    )


async def role(client: httpx.AsyncClient, code: str) -> dict[str, Any]:
    roles = (await client.get(ROLES, headers=ALICE)).json()["items"]
    return next(r for r in roles if r["code"] == code)


def cell(template: dict[str, Any], module: str, role_code: str) -> dict[str, Any]:
    return next(c for c in template["cells"] if (c["module"], c["role"]) == (module, role_code))


@pytest.mark.usefixtures("operator")
async def test_only_an_operator_may_read_or_change_the_template(
    client: httpx.AsyncClient,
) -> None:
    # A tenant admin holds every tenant code but no platform.* code (ADR 0029 amendment).
    assert (await client.get(TEMPLATE, headers=ALICE)).status_code == 403
    body = {"changes": [{"module": "projects", "role": "auditor", "level": "edit"}], "reason": "x"}
    assert (await client.patch(TEMPLATE, json=body, headers=ALICE)).status_code == 403
    assert (await client.post(f"{TEMPLATE}/sync", json={}, headers=ALICE)).status_code == 403
    assert (await client.get(TEMPLATE, headers=OPERATOR)).status_code == 200


@pytest.mark.usefixtures("operator")
async def test_the_template_starts_as_the_shipped_matrix(client: httpx.AsyncClient) -> None:
    template = (await client.get(TEMPLATE, headers=OPERATOR)).json()
    assert template["roles"] == list(ROLE_CODES)
    assert template["levels"] == ["none", "view", "create", "edit", "approve", "admin"]
    for module, levels in MATRIX.items():
        for code, level in zip(ROLE_CODES, levels, strict=True):
            c = cell(template, module, code)
            assert (c["level"], c["shippedLevel"], c["overridden"]) == (level, level, False)
    # A catalogue module the matrix does not list ships as none and can still be set.
    assert {c["module"] for c in template["cells"]} >= set(MATRIX)


@pytest.mark.usefixtures("operator")
async def test_a_change_is_audited_and_synced_to_uncustomised_roles(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    assert shipped("projects", "auditor") == "view"
    assert "project.update" not in (await role(client, "auditor"))["permissions"]

    response = await patch(client, [{"module": "projects", "role": "auditor", "level": "edit"}])
    assert response.status_code == 200, response.text
    (change,) = response.json()["items"]
    assert change["module"] == "projects"
    assert change["role"] == "auditor"
    assert (change["levelBefore"], change["levelAfter"]) == ("view", "edit")
    assert change["changedBy"] == str(OPERATOR_ID)
    assert change["reason"] == "ops review"

    c = cell((await client.get(TEMPLATE, headers=OPERATOR)).json(), "projects", "auditor")
    assert (c["level"], c["shippedLevel"], c["overridden"]) == ("edit", "view", True)
    assert c["updatedBy"] == str(OPERATOR_ID)

    # Nothing changes in a tenant until the template is pushed.
    assert "project.update" not in (await role(client, "auditor"))["permissions"]
    response = await client.post(
        f"{TEMPLATE}/sync", json={"tenantIds": [str(TENANT_A_ID)]}, headers=OPERATOR
    )
    assert response.status_code == 200, response.text
    (report,) = response.json()["tenants"]
    assert report["tenantId"] == str(TENANT_A_ID)
    assert report["updated"] == ["auditor"]
    held = (await role(client, "auditor"))["permissions"]
    assert {"project.create", "project.update", "project.archive"} <= set(held)
    assert "site.manage" not in held  # manage stays admin-only
    # The push was made by the operator: the role event in tenant A names them as the actor.
    rows = await su_fetch(
        db,
        "SELECT actor_id FROM domain_events WHERE event_name = 'access.role.changed'"
        " AND tenant_id = $1 AND payload->>'code' = 'auditor' AND payload->>'action' = 'seeded'"
        " AND payload->>'before' IS NOT NULL",
        TENANT_A_ID,
    )
    assert [r[0] for r in rows] == [OPERATOR_ID]


@pytest.mark.usefixtures("operator")
async def test_setting_a_cell_back_to_its_shipped_level_resets_it(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await patch(client, [{"module": "projects", "role": "auditor", "level": "edit"}])
    response = await patch(client, [{"module": "projects", "role": "auditor", "level": "view"}])
    assert [c["levelAfter"] for c in response.json()["items"]] == ["view"]
    assert await su_fetch(db, "SELECT 1 FROM default_role_level") == []
    c = cell((await client.get(TEMPLATE, headers=OPERATOR)).json(), "projects", "auditor")
    assert (c["level"], c["overridden"], c["updatedBy"]) == ("view", False, None)
    # A no-op change writes no history.
    response = await patch(client, [{"module": "projects", "role": "auditor", "level": "view"}])
    assert response.json()["items"] == []
    # A row the shipped matrix has caught up with shows as overridden and resets without history.
    await su_execute(
        db,
        "INSERT INTO default_role_level (module_id, role_code, level)"
        " VALUES ('projects', 'inspector', 'view')",
    )
    c = cell((await client.get(TEMPLATE, headers=OPERATOR)).json(), "projects", "inspector")
    assert (c["level"], c["shippedLevel"], c["overridden"]) == ("view", "view", True)
    response = await patch(client, [{"module": "projects", "role": "inspector", "level": "view"}])
    assert response.json()["items"] == []
    assert await su_fetch(db, "SELECT 1 FROM default_role_level") == []
    history = (await client.get(f"{TEMPLATE}/history", headers=OPERATOR)).json()["items"]
    assert [(h["levelBefore"], h["levelAfter"]) for h in history] == [
        ("edit", "view"),
        ("view", "edit"),
    ]
    one = await client.get(f"{TEMPLATE}/history", params={"role": "inspector"}, headers=OPERATOR)
    assert one.json()["items"] == []


@pytest.mark.usefixtures("operator")
@pytest.mark.parametrize(
    ("change", "code"),
    [
        (
            {"module": "inspections", "role": "client_reviewer", "level": "edit"},
            "SIGN_OFF_ONLY_ROLE",
        ),
        ({"module": "projects", "role": "client_reviewer", "level": "admin"}, "SIGN_OFF_ONLY_ROLE"),
        ({"module": "access", "role": "tenant_admin", "level": "edit"}, "TENANT_ADMIN_LOCKOUT"),
        ({"module": "projects", "role": "super_admin", "level": "view"}, "UNKNOWN_ROLE"),
        ({"module": "no_such_module", "role": "auditor", "level": "view"}, "UNKNOWN_MODULE"),
    ],
)
async def test_guardrails_refuse_the_whole_request(
    client: httpx.AsyncClient, db: TenantDb, change: dict[str, str], code: str
) -> None:
    good = {"module": "projects", "role": "auditor", "level": "edit"}
    response = await patch(client, [good, change])
    assert response.status_code == 422, response.text
    assert response.json()["code"] == code
    assert await su_fetch(db, "SELECT 1 FROM default_role_level") == []
    assert await su_fetch(db, "SELECT 1 FROM default_role_level_change") == []


@pytest.mark.usefixtures("operator")
async def test_a_cell_may_appear_once_and_a_reason_is_required(client: httpx.AsyncClient) -> None:
    same = {"module": "projects", "role": "auditor", "level": "edit"}
    response = await patch(client, [same, {**same, "level": "create"}])
    assert (response.status_code, response.json()["code"]) == (422, "DUPLICATE_CELL")
    assert (await patch(client, [same], reason="   ")).status_code == 422
    bad_level = {**same, "level": "owner"}
    assert (await patch(client, [bad_level])).status_code == 422


@pytest.mark.usefixtures("operator")
async def test_the_template_never_grants_operator_or_portal_only_codes(
    client: httpx.AsyncClient,
) -> None:
    # ops declares platform.* codes and ops.jobs.admin; portal declares portal-only codes.
    changes = [
        {"module": module, "role": "project_manager", "level": "admin"}
        for module in ("ops", "portal")
    ]
    assert (await patch(client, changes)).status_code == 200
    response = await client.post(f"{TEMPLATE}/sync", json={}, headers=OPERATOR)
    assert response.status_code == 200, response.text
    held = set((await role(client, "project_manager"))["permissions"])
    assert "ops.jobs.admin" in held
    assert not {c for c in held if c.startswith(("platform.", "portal.record.", "portal.report."))}


@pytest.mark.usefixtures("operator")
async def test_customised_roles_are_reported_not_overwritten(client: httpx.AsyncClient) -> None:
    # Customise both roles first: only template changes made after that are reported.
    auditor = await role(client, "auditor")
    supervisor = await role(client, "supervisor")
    response = await client.patch(
        f"{ROLES}/{auditor['id']}", json={"permissions": ["project.view"]}, headers=ALICE
    )
    assert response.status_code == 200, response.text
    kept = [c for c in supervisor["permissions"] if c != "site.view"]
    response = await client.patch(
        f"{ROLES}/{supervisor['id']}", json={"permissions": kept}, headers=ALICE
    )
    assert response.status_code == 200, response.text
    assert shipped("assets", "supervisor") == "edit"
    await patch(
        client,
        [
            {"module": "projects", "role": "auditor", "level": "edit"},
            {"module": "assets", "role": "supervisor", "level": "view"},
        ],
    )
    response = await client.post(
        f"{TEMPLATE}/sync", json={"tenantIds": [str(TENANT_A_ID)]}, headers=OPERATOR
    )
    (report,) = response.json()["tenants"]
    assert report["updated"] == []
    # Every code the new projects level gives and the role lacks, site.view included.
    assert report["pending"]["auditor"] == [
        "project.archive",
        "project.create",
        "project.update",
        "site.view",
    ]
    # Lowering supervisor's assets level would take codes away: reported as excess, kept.
    assert "asset.move" in report["excess"]["supervisor"]
    assert (await role(client, "auditor"))["permissions"] == ["project.view"]
    assert (await role(client, "supervisor"))["permissions"] == kept


@pytest.mark.usefixtures("operator")
async def test_sync_defaults_to_every_active_tenant_and_refuses_unknown_ones(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await su_execute(db, f"UPDATE tenants SET status = 'suspended' WHERE id = '{TENANT_B_ID}'")
    other = "00000000-0000-4000-8000-00000000ffff"
    for target in (other, str(TENANT_B_ID)):
        response = await client.post(
            f"{TEMPLATE}/sync",
            json={"tenantIds": [target]},
            headers=headers(TENANT_A_ID, OPERATOR_ID),
        )
        assert (response.status_code, response.json()["code"]) == (422, "UNKNOWN_TENANT")
    response = await client.post(
        f"{TEMPLATE}/sync", json={}, headers=headers(TENANT_A_ID, OPERATOR_ID)
    )
    assert [t["tenantId"] for t in response.json()["tenants"]] == [str(TENANT_A_ID)]


async def test_a_new_tenant_is_seeded_from_the_template(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    # Provisioning (seed_default_roles) reads the template; no push is needed for a new tenant.
    await su_execute(
        db,
        "INSERT INTO default_role_level (module_id, role_code, level)"
        " VALUES ('projects', 'auditor', 'edit')",
    )
    await su_execute(
        db,
        "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
        f"('{TENANT_C_ID}', 'Tenant C', 'tenant-c', 'ap-southeast-2', 'active')",
    )
    report = await seed_roles(TENANT_C_ID)
    assert "auditor" in report.created
    rows = await su_fetch(
        db,
        "SELECT rp.permission_code FROM role_permission rp JOIN role r ON r.id = rp.role_id"
        " WHERE r.tenant_id = $1 AND r.code = 'auditor' AND rp.permission_code = 'project.update'",
        TENANT_C_ID,
    )
    assert len(rows) == 1


async def test_aip_app_writes_the_template_only_through_the_audited_function(
    app: FastAPI, db: TenantDb
) -> None:
    await su_execute(
        db,
        "INSERT INTO default_role_level_change"
        " (id, module_id, role_code, level_before, level_after, reason)"
        " VALUES (gen_random_uuid(), 'projects', 'auditor', 'view', 'edit', 'seeded');"
        "INSERT INTO default_role_level (module_id, role_code, level)"
        " VALUES ('projects', 'auditor', 'edit')",
    )
    # No direct write to either table: a change can never skip or rewrite its history.
    for sql in (
        "INSERT INTO default_role_level (module_id, role_code, level)"
        " VALUES ('projects', 'inspector', 'edit')",
        "UPDATE default_role_level SET level = 'admin'",
        "DELETE FROM default_role_level",
        "INSERT INTO default_role_level_change"
        " (id, module_id, role_code, level_before, level_after, reason)"
        " VALUES (gen_random_uuid(), 'projects', 'auditor', 'edit', 'view', 'forged')",
        "UPDATE default_role_level_change SET reason = 'changed'",
        "DELETE FROM default_role_level_change",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await _execute(db.db.app_url, sql)

    # The function moves the cell and appends its history row in the same call.
    rows = await _fetch(
        db.db.app_url,
        "SELECT level_before, level_after, reason FROM"
        " access_set_default_role_level('projects', 'auditor', 'admin', 'view', NULL, 'why')",
    )
    assert rows == [("edit", "admin", "why")]
    # The shipped level deletes the row; a blank reason or an invalid shipped level is refused.
    rows = await _fetch(
        db.db.app_url,
        "SELECT level_after FROM"
        " access_set_default_role_level('projects', 'auditor', 'view', 'view', NULL, 'reset')",
    )
    assert rows == [("view",)]
    assert await su_fetch(db, "SELECT 1 FROM default_role_level") == []
    for call in (
        "('projects', 'auditor', 'edit', 'view', NULL, '  ')",
        "('projects', 'auditor', 'edit', 'owner', NULL, 'why')",
    ):
        with pytest.raises(asyncpg.InvalidParameterValueError):
            await _fetch(db.db.app_url, f"SELECT * FROM access_set_default_role_level{call}")
    # The table CHECKs still hold inside the definer function.
    for call in (
        "('inspections', 'client_reviewer', 'edit', 'approve', NULL, 'why')",
        "('access', 'tenant_admin', 'view', 'admin', NULL, 'why')",
        "('projects', 'super_admin', 'edit', 'view', NULL, 'why')",
    ):
        with pytest.raises(asyncpg.CheckViolationError):
            await _fetch(db.db.app_url, f"SELECT * FROM access_set_default_role_level{call}")
    history = await su_fetch(db, "SELECT count(*) FROM default_role_level_change")
    assert history == [(3,)]
    # Only aip_app may call it.
    grantees = await su_fetch(
        db,
        "SELECT r.rolname FROM pg_roles r WHERE has_function_privilege(r.oid,"
        " 'access_set_default_role_level(text, text, text, text, uuid, text)', 'EXECUTE')"
        r" AND r.rolname LIKE 'aip\_%'"
        " AND NOT r.rolsuper ORDER BY 1",  # a superuser (CI's aip_test) can execute anything
    )
    assert [g[0] for g in grantees] == ["aip_app", "aip_owner"]
