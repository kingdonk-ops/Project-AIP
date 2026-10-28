"""Data access for teams and team membership (ACCESS-04).

Every function takes the connection from ``with_tenant``: RLS limits it to the bound tenant, and
inserts take ``tenant_id`` from ``app.tenant_id``. Deletes are soft (``aip_app`` has no DELETE on
``team`` or ``team_member``). Membership writes fire ``trg_access_team_member_scope_sync``, which
keeps ``access_user_scope`` in step (ADR 0037).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "active_member_ids",
    "add_members",
    "get_team",
    "insert_team",
    "list_members",
    "list_teams",
    "member_ids",
    "remove_all_members",
    "remove_member",
    "remove_user_memberships",
    "soft_delete_team",
    "team_assignments",
    "team_role_permissions",
    "teams_for_user",
    "update_team",
]

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_TEAM_COLUMNS = (
    "t.id, t.name, t.team_type, t.project_id, t.organisation_id, t.scim_group_id,"
    " t.created_at, t.updated_at,"
    " (SELECT count(*) FROM team_member tm WHERE tm.team_id = t.id AND tm.deleted_at IS NULL)"
    " AS member_count"
)


async def get_team(
    conn: AsyncConnection, team_id: UUID, *, for_update: bool = False
) -> dict[str, Any] | None:
    lock = " FOR UPDATE OF t" if for_update else ""
    row = (
        await conn.execute(
            text(f"SELECT {_TEAM_COLUMNS} FROM team t WHERE t.id = :id AND t.deleted_at IS NULL{lock}"),
            {"id": team_id},
        )
    ).first()
    return None if row is None else dict(row._mapping)


async def list_teams(conn: AsyncConnection, *, project_id: UUID | None) -> list[dict[str, Any]]:
    """Live teams, by name; with ``project_id`` only that project's."""
    where = "t.deleted_at IS NULL"
    params: dict[str, Any] = {}
    if project_id is not None:
        where += " AND t.project_id = :project"
        params["project"] = project_id
    rows = await conn.execute(
        text(f"SELECT {_TEAM_COLUMNS} FROM team t WHERE {where} ORDER BY lower(t.name), t.id LIMIT 1000"),
        params,
    )
    return [dict(r._mapping) for r in rows]


async def insert_team(
    conn: AsyncConnection,
    *,
    team_id: UUID,
    name: str,
    team_type: str,
    project_id: UUID | None,
    organisation_id: UUID | None,
    created_by: UUID | None,
) -> None:
    await conn.execute(
        text(
            "INSERT INTO team (id, tenant_id, name, team_type, project_id, organisation_id,"
            f" created_by) VALUES (:id, {_TENANT}, :name, :type, :project, :org, :created)"
        ),
        {
            "id": team_id,
            "name": name,
            "type": team_type,
            "project": project_id,
            "org": organisation_id,
            "created": created_by,
        },
    )


async def update_team(conn: AsyncConnection, team_id: UUID, fields: dict[str, Any]) -> None:
    """Set the given columns (``name``, ``team_type``, ``organisation_id``)."""
    allowed = {"name", "team_type", "organisation_id"}
    assert set(fields) <= allowed, fields
    sets = ["updated_at = now()", *(f"{column} = :{column}" for column in sorted(fields))]
    await conn.execute(
        text(f"UPDATE team SET {', '.join(sets)} WHERE id = :id AND deleted_at IS NULL"),
        {"id": team_id, **fields},
    )


async def soft_delete_team(conn: AsyncConnection, team_id: UUID) -> None:
    await conn.execute(
        text("UPDATE team SET deleted_at = now(), updated_at = now() WHERE id = :id"),
        {"id": team_id},
    )


async def member_ids(conn: AsyncConnection, team_id: UUID) -> list[UUID]:
    """The users with a live membership of the team, whatever their status, sorted."""
    rows = await conn.execute(
        text(
            "SELECT user_id FROM team_member WHERE team_id = :team AND deleted_at IS NULL"
            " ORDER BY user_id"
        ),
        {"team": team_id},
    )
    return [r[0] for r in rows]


async def active_member_ids(conn: AsyncConnection, team_id: UUID) -> list[UUID]:
    """The active users with a live membership of a live team, sorted (APPROVALS-04)."""
    rows = await conn.execute(
        text(
            "SELECT tm.user_id FROM team_member tm"
            " JOIN team t ON t.id = tm.team_id AND t.deleted_at IS NULL"
            " JOIN app_user u ON u.id = tm.user_id AND u.status = 'active'"
            "  AND u.deleted_at IS NULL"
            " WHERE tm.team_id = :team AND tm.deleted_at IS NULL ORDER BY tm.user_id"
        ),
        {"team": team_id},
    )
    return [r[0] for r in rows]


async def list_members(conn: AsyncConnection, team_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.execute(
        text(
            "SELECT user_id, source, created_at FROM team_member"
            " WHERE team_id = :team AND deleted_at IS NULL ORDER BY created_at, user_id"
        ),
        {"team": team_id},
    )
    return [dict(r._mapping) for r in rows]


async def add_members(
    conn: AsyncConnection, team_id: UUID, user_ids: Iterable[UUID], created_by: UUID | None
) -> list[UUID]:
    """Add the users who are not live members yet; returns those actually added, sorted."""
    rows = await conn.execute(
        text(
            "INSERT INTO team_member (id, tenant_id, team_id, user_id, source, created_by)"
            f" SELECT gen_random_uuid(), {_TENANT}, :team, u, 'manual', :created"
            " FROM unnest(CAST(:users AS uuid[])) AS u"
            " ON CONFLICT (team_id, user_id) WHERE deleted_at IS NULL DO NOTHING"
            " RETURNING user_id"
        ),
        {"team": team_id, "users": sorted(set(user_ids)), "created": created_by},
    )
    return sorted(r[0] for r in rows)


async def remove_member(conn: AsyncConnection, team_id: UUID, user_id: UUID) -> bool:
    """Soft-delete the live membership; False when there was none."""
    rows = await conn.execute(
        text(
            "UPDATE team_member SET deleted_at = now(), updated_at = now()"
            " WHERE team_id = :team AND user_id = :user AND deleted_at IS NULL RETURNING id"
        ),
        {"team": team_id, "user": user_id},
    )
    return rows.first() is not None


async def remove_all_members(conn: AsyncConnection, team_id: UUID) -> list[UUID]:
    rows = await conn.execute(
        text(
            "UPDATE team_member SET deleted_at = now(), updated_at = now()"
            " WHERE team_id = :team AND deleted_at IS NULL RETURNING user_id"
        ),
        {"team": team_id},
    )
    return sorted(r[0] for r in rows)


async def remove_user_memberships(conn: AsyncConnection, user_id: UUID) -> list[UUID]:
    """Soft-delete every live membership of the user; returns the teams left, sorted."""
    rows = await conn.execute(
        text(
            "UPDATE team_member SET deleted_at = now(), updated_at = now()"
            " WHERE user_id = :user AND deleted_at IS NULL RETURNING team_id"
        ),
        {"user": user_id},
    )
    return sorted(r[0] for r in rows)


async def team_assignments(conn: AsyncConnection, team_id: UUID) -> list[UUID]:
    """The ids of the team's live role assignments."""
    rows = await conn.execute(
        text(
            "SELECT id FROM role_assignment WHERE team_id = :team AND scope_type = 'team'"
            " AND deleted_at IS NULL ORDER BY id"
        ),
        {"team": team_id},
    )
    return [r[0] for r in rows]


async def team_role_permissions(conn: AsyncConnection, team_id: UUID) -> set[str]:
    """Every permission of every role live-assigned to the team (current or future)."""
    rows = await conn.execute(
        text(
            "SELECT DISTINCT rp.permission_code FROM role_assignment ra"
            " JOIN role_permission rp ON rp.role_id = ra.role_id AND rp.deleted_at IS NULL"
            " WHERE ra.team_id = :team AND ra.scope_type = 'team' AND ra.deleted_at IS NULL"
        ),
        {"team": team_id},
    )
    return {r[0] for r in rows}


async def teams_for_user(conn: AsyncConnection, user_id: UUID) -> list[dict[str, Any]]:
    """The live teams the user is a live member of, by name."""
    rows = await conn.execute(
        text(
            "SELECT t.id, t.name, t.team_type, t.project_id FROM team_member tm"
            " JOIN team t ON t.id = tm.team_id AND t.deleted_at IS NULL"
            " WHERE tm.user_id = :user AND tm.deleted_at IS NULL ORDER BY lower(t.name), t.id"
        ),
        {"user": user_id},
    )
    return [dict(r._mapping) for r in rows]
