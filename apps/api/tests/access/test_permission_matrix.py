"""TESTING-04: the generated permission matrix against the real ``PolicyService``.

The matrix is parametrized at collection time from the module manifests (the permission catalogue)
and ``default_permissions`` (the 11 default roles), so every case is its own test in the JUnit
report. The database test proves the same rule through real role assignments and the real
``RoleGrantProvider``: a project-scoped role allows in its project and denies in another.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI

from aip.modules.access.roles.default_roles import ROLE_CODES, default_permissions
from aip.modules.access.tests.roles.conftest import CAROL_ID, su_assign
from aip.platform.access import (
    AccessPrincipal,
    Grant,
    PolicyService,
    ProjectScope,
    Resource,
    TenantScope,
)
from aip.platform.access.catalogue import build_catalogue, load_manifests
from tests.access.matrix_gen import MatrixCase, matrix_cases
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

MODULES = Path(__file__).resolve().parents[2] / "aip" / "modules"
CATALOGUE = build_catalogue(load_manifests(MODULES))
ROLES = default_permissions((p.code, p.module_id) for p in CATALOGUE.values())
CASES = matrix_cases(ROLES, CATALOGUE)
P1 = UUID("00000000-0000-4000-8000-0000000000f1")
P2 = UUID("00000000-0000-4000-8000-0000000000f2")


class RoleGrants:
    """Grants for one role assignment of one principal (or none when unassigned)."""

    def __init__(self, case: MatrixCase) -> None:
        self.case = case

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        if not self.case.assigned:
            return []
        scope = TenantScope() if self.case.assignment == "tenant" else ProjectScope(P1)
        return [Grant(code, scope) for code in sorted(ROLES[self.case.role])]


# --- unit: the generator ----------------------------------------------------------------------


def test_one_role_one_permission_two_scopes_two_states_gives_four_cases_one_allow() -> None:
    cases = matrix_cases(
        {"inspector": {"inspection.create"}}, ["inspection.create"], assignments=("project",)
    )
    assert len(cases) == 4
    assert [c.id for c in cases if c.expected] == [
        "inspector-inspection.create-assigned-project-P1-allow"
    ]


def test_every_catalogue_permission_and_default_role_is_in_the_matrix() -> None:
    assert {c.permission for c in CASES} == set(CATALOGUE)
    assert {c.role for c in CASES} == set(ROLE_CODES)
    assert len(CASES) == len(ROLE_CODES) * len(set(CATALOGUE)) * 2 * 2 * 2


def test_operator_permissions_are_never_allowed_for_a_tenant_role() -> None:
    assert not [c for c in CASES if c.permission.startswith("platform.") and c.expected]


def test_an_unassigned_principal_is_denied_everything() -> None:
    assert not [c for c in CASES if not c.assigned and c.expected]


# --- the matrix -------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_policy_matches_the_matrix(case: MatrixCase) -> None:
    policy = PolicyService(CATALOGUE, [RoleGrants(case)])
    principal = AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=ALICE_ID)
    project = P1 if case.in_scope else P2
    decision = await policy.can(principal, case.permission, Resource(project_id=project))
    assert decision.allowed is case.expected, decision.reason


# --- integration: real role assignments -------------------------------------------------------


async def test_a_project_scoped_role_allows_in_its_project_and_denies_in_another(
    app: FastAPI, db: TenantDb
) -> None:
    role = next(r for r in sorted(ROLES) if "project.update" in ROLES[r] and r != "tenant_admin")
    await su_assign(db, TENANT_A_ID, CAROL_ID, role, project=P1)
    policy: PolicyService = app.state.access_policy
    carol = AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=CAROL_ID)
    in_p1 = await policy.can(carol, "project.update", Resource(project_id=P1))
    in_p2 = await policy.can(carol, "project.update", Resource(project_id=P2))
    tenant_wide = await policy.can(carol, "project.update")
    assert (in_p1.allowed, in_p2.allowed, tenant_wide.allowed) == (True, False, False)
