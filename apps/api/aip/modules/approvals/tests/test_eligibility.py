"""APPROVALS-04: who may decide a route step (``is_eligible`` over a fake directory)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from aip.modules.approvals.routes_engine.eligibility import TeamScope, is_eligible

ACTOR = UUID(int=10)
OTHER = UUID(int=11)
QA = UUID(int=20)
CLIENT = UUID(int=30)
P1, P2 = UUID(int=101), UUID(int=102)


@dataclass(frozen=True)
class _Team:
    id: UUID
    project_id: UUID | None


class _Directory:
    """Role assignments as ``(user, role, project or None for tenant-wide)``; team memberships."""

    def __init__(
        self,
        roles: set[tuple[UUID, UUID, UUID | None]] | None = None,
        teams: dict[UUID, list[_Team]] | None = None,
    ) -> None:
        self.roles = roles or set()
        self.memberships = teams or {}

    async def has_role(self, user_id: UUID, role_id: UUID, project_id: UUID | None) -> bool:
        return (user_id, role_id, None) in self.roles or (
            project_id is not None and (user_id, role_id, project_id) in self.roles
        )

    async def teams(self, user_id: UUID) -> Sequence[TeamScope]:
        return self.memberships.get(user_id, [])


async def test_a_user_step_accepts_only_that_user() -> None:
    directory = _Directory()
    assert await is_eligible(directory, ACTOR, "user", ACTOR, P1)
    assert not await is_eligible(directory, OTHER, "user", ACTOR, P1)
    assert not await is_eligible(directory, None, "user", ACTOR, P1)


async def test_a_role_held_on_another_project_does_not_count() -> None:
    directory = _Directory(roles={(ACTOR, QA, P1)})
    assert await is_eligible(directory, ACTOR, "role", QA, P1)
    assert not await is_eligible(directory, ACTOR, "role", QA, P2)
    assert not await is_eligible(directory, ACTOR, "role", QA, None)


async def test_a_tenant_wide_role_counts_on_every_project() -> None:
    directory = _Directory(roles={(ACTOR, QA, None)})
    assert await is_eligible(directory, ACTOR, "role", QA, P2)
    assert await is_eligible(directory, ACTOR, "role", QA, None)


async def test_a_team_step_needs_a_member_of_a_team_in_scope() -> None:
    directory = _Directory(
        teams={ACTOR: [_Team(CLIENT, None)], OTHER: [_Team(CLIENT, P1)]},
    )
    assert await is_eligible(directory, ACTOR, "team", CLIENT, P2)
    assert await is_eligible(directory, OTHER, "team", CLIENT, P1)
    assert not await is_eligible(directory, OTHER, "team", CLIENT, P2)
    assert not await is_eligible(directory, OTHER, "team", QA, P1)
    assert not await is_eligible(_Directory(), ACTOR, "team", CLIENT, P1)
