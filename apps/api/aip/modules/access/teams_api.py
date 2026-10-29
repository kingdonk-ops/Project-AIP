"""Team lookups other modules use through ``aip.modules.access.api`` (ACCESS-04, APPROVALS-04)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.teams import repository as repo

__all__ = ["TeamRef", "list_team_members", "teams_for_user"]


@dataclass(frozen=True, slots=True)
class TeamRef:
    id: UUID
    name: str
    team_type: str
    project_id: UUID | None


async def list_team_members(conn: AsyncConnection, team_id: UUID) -> list[UUID]:
    """The active users with a live membership of live team ``team_id``, sorted (empty for an
    unknown team or another tenant's). Takes the ``with_tenant`` connection."""
    return await repo.active_member_ids(conn, team_id)


async def teams_for_user(conn: AsyncConnection, user_id: UUID) -> list[TeamRef]:
    """The live teams the user is a live member of, by name."""
    return [TeamRef(**row) for row in await repo.teams_for_user(conn, user_id)]
