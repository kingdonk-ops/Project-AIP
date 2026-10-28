"""ACCESS-04 unit tests: cache keys, team grant resolution and the team-scope schema."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from aip.modules.access.policy_cache import grants_key, version_key
from aip.modules.access.roles.grant_provider import AssignmentGrant, resolve_grants
from aip.modules.access.roles.schemas import AssignmentCreate

T1 = UUID("00000000-0000-4000-8000-00000000a001")
U1 = UUID("00000000-0000-4000-8000-00000000b001")
TEAM = UUID("00000000-0000-4000-8000-00000000c001")
P1 = UUID("00000000-0000-4000-8000-00000000d001")
ROLE = UUID("00000000-0000-4000-8000-00000000e001")


def test_version_key_uses_the_tenant_key_builder() -> None:
    assert version_key(T1, U1) == f"tenant:{T1}:access:ver:{U1}"
    assert version_key(T1) == f"tenant:{T1}:access:ver"
    assert grants_key(T1, U1, (3, 7)) == f"tenant:{T1}:access:grants:{U1}:3:7"


def test_a_team_assignment_grants_members_at_the_teams_project() -> None:
    inspector = [
        AssignmentGrant("project.view", "team", team_id=TEAM),
        AssignmentGrant("form.view", "team", team_id=TEAM),
    ]
    assert resolve_grants(inspector, {TEAM: P1}) == [
        ("form.view", "project", str(P1)),
        ("project.view", "project", str(P1)),
    ]
    assert resolve_grants(inspector, {}) == []  # not a member: nothing


def test_a_tenant_level_team_grants_at_tenant_scope() -> None:
    grants = [AssignmentGrant("project.view", "team", team_id=TEAM)]
    assert resolve_grants(grants, {TEAM: None}) == [("project.view", "tenant", None)]


def test_operator_codes_are_never_granted_through_a_team() -> None:
    grants = [AssignmentGrant("platform.tenants.manage", "team", team_id=TEAM)]
    assert resolve_grants(grants, {TEAM: None}) == []


def test_the_schema_rejects_a_team_scope_with_a_user() -> None:
    team_scope = {"type": "team", "teamId": str(TEAM)}
    with pytest.raises(ValidationError):
        AssignmentCreate.model_validate({"userId": str(U1), "roleId": str(ROLE), "scope": team_scope})
    ok = AssignmentCreate.model_validate({"roleId": str(ROLE), "scope": team_scope})
    assert ok.user_id is None
    with pytest.raises(ValidationError):  # every other scope needs a user
        AssignmentCreate.model_validate({"roleId": str(ROLE), "scope": {"type": "tenant"}})
    with pytest.raises(ValidationError):  # a team scope needs its team
        AssignmentCreate.model_validate({"roleId": str(ROLE), "scope": {"type": "team"}})
