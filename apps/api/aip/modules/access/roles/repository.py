"""Data access for roles and role assignments (ACCESS-02).

Every function takes the connection from ``with_tenant``: RLS limits it to the bound tenant, and
inserts take ``tenant_id`` from ``app.tenant_id``. Deletes are soft (``aip_app`` has no DELETE).

ACCESS-04: an assignment is held by a user, or (``scope_type = 'team'``) by a team, whose live
members hold it; ``active_grants`` and ``member_teams`` feed ``RoleGrantProvider``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "ACTIVE_ASSIGNMENT",
    "active_grants",
    "codes_added_since",
    "count_holders",
    "get_assignment",
    "get_role",
    "get_role_by_code",
    "has_live_tenant_assignment",
    "holds_role_at_tenant",
    "insert_assignment",
    "insert_role",
    "list_assignments",
    "list_roles",
    "live_catalogue",
    "live_user_assignments",
    "lock_tenant_roles",
    "member_teams",
    "privileged_codes",
    "role_code_for_id",
    "role_codes",
    "role_in_use",
    "role_permissions",
    "set_role_permissions",
    "soft_delete_assignment",
    "soft_delete_role",
    "update_role",
]

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# An assignment that grants right now: live, started, not expired, held by an active user.
ACTIVE_ASSIGNMENT = """
    ra.deleted_at IS NULL AND ra.valid_from <= now()
    AND (ra.valid_to IS NULL OR ra.valid_to > now())
    AND EXISTS (SELECT 1 FROM app_user u WHERE u.id = ra.user_id AND u.status = 'active'
                AND u.deleted_at IS NULL)
"""

_ROLE_COLUMNS = "r.id, r.code, r.name, r.name_term_key, r.is_system, r.customised_at"
_ROLE_PERMISSIONS = """
    COALESCE((SELECT array_agg(rp.permission_code ORDER BY rp.permission_code)
              FROM role_permission rp WHERE rp.role_id = r.id AND rp.deleted_at IS NULL),
             '{}') AS permissions
"""


async def lock_tenant_roles(conn: AsyncConnection) -> None:
    """Serialise role and assignment changes in this tenant until the transaction ends."""
    await conn.execute(
        text(f"SELECT pg_advisory_xact_lock(hashtextextended('access.roles:' || {_TENANT}, 0))")
    )


async def live_catalogue(conn: AsyncConnection) -> list[tuple[str, str, bool]]:
    """``(code, module_id, is_privileged)`` for every catalogue code that is not deprecated."""
    rows = await conn.execute(
        text(
            "SELECT code, module_id, is_privileged FROM permission"
            " WHERE deprecated_at IS NULL ORDER BY code"
        )
    )
    return [(r[0], r[1], r[2]) for r in rows]


async def privileged_codes(conn: AsyncConnection) -> set[str]:
    """Every privileged catalogue code, deprecated ones included (fail closed)."""
    rows = await conn.execute(text("SELECT code FROM permission WHERE is_privileged"))
    return {r[0] for r in rows}


async def codes_added_since(conn: AsyncConnection, since: datetime) -> set[str]:
    """Live catalogue codes first synced after ``since``."""
    rows = await conn.execute(
        text("SELECT code FROM permission WHERE deprecated_at IS NULL AND created_at > :since"),
        {"since": since},
    )
    return {r[0] for r in rows}


async def list_roles(conn: AsyncConnection) -> list[dict[str, Any]]:
    rows = await conn.execute(
        text(
            f"SELECT {_ROLE_COLUMNS}, {_ROLE_PERMISSIONS} FROM role r"
            " WHERE r.deleted_at IS NULL ORDER BY r.is_system DESC, r.code"
        )
    )
    return [dict(r._mapping) for r in rows]


async def get_role(
    conn: AsyncConnection, role_id: UUID, *, for_update: bool = False
) -> dict[str, Any] | None:
    lock = " FOR UPDATE OF r" if for_update else ""
    row = (
        await conn.execute(
            text(
                f"SELECT {_ROLE_COLUMNS}, {_ROLE_PERMISSIONS} FROM role r"
                f" WHERE r.id = :id AND r.deleted_at IS NULL{lock}"
            ),
            {"id": role_id},
        )
    ).first()
    return None if row is None else dict(row._mapping)


async def get_role_by_code(conn: AsyncConnection, code: str) -> dict[str, Any] | None:
    row = (
        await conn.execute(
            text(
                f"SELECT {_ROLE_COLUMNS}, {_ROLE_PERMISSIONS} FROM role r"
                " WHERE r.code = :code AND r.deleted_at IS NULL"
            ),
            {"code": code},
        )
    ).first()
    return None if row is None else dict(row._mapping)


async def insert_role(
    conn: AsyncConnection,
    *,
    role_id: UUID,
    code: str,
    name: str | None,
    name_term_key: str | None,
    is_system: bool,
) -> None:
    await conn.execute(
        text(
            "INSERT INTO role (id, tenant_id, code, name, name_term_key, is_system)"
            f" VALUES (:id, {_TENANT}, :code, :name, :key, :system)"
        ),
        {"id": role_id, "code": code, "name": name, "key": name_term_key, "system": is_system},
    )


async def update_role(
    conn: AsyncConnection,
    role_id: UUID,
    *,
    code: str | None = None,
    name: str | None = None,
    customised: bool | None = None,
) -> None:
    """Change the given fields; ``customised`` True stamps ``customised_at`` once, False clears."""
    sets = ["updated_at = now()"]
    params: dict[str, Any] = {"id": role_id}
    if code is not None:
        sets.append("code = :code")
        params["code"] = code
    if name is not None:
        sets.append("name = :name")
        params["name"] = name
    if customised is True:
        sets.append("customised_at = COALESCE(customised_at, now())")
    elif customised is False:
        sets.append("customised_at = NULL")
    await conn.execute(text(f"UPDATE role SET {', '.join(sets)} WHERE id = :id"), params)


async def soft_delete_role(conn: AsyncConnection, role_id: UUID) -> None:
    await conn.execute(
        text(
            "UPDATE role_permission SET deleted_at = now(), updated_at = now()"
            " WHERE role_id = :id AND deleted_at IS NULL"
        ),
        {"id": role_id},
    )
    await conn.execute(
        text("UPDATE role SET deleted_at = now(), updated_at = now() WHERE id = :id"),
        {"id": role_id},
    )


async def role_permissions(conn: AsyncConnection, role_id: UUID) -> set[str]:
    rows = await conn.execute(
        text(
            "SELECT permission_code FROM role_permission WHERE role_id = :id AND deleted_at IS NULL"
        ),
        {"id": role_id},
    )
    return {r[0] for r in rows}


async def set_role_permissions(
    conn: AsyncConnection, role_id: UUID, codes: Iterable[str], *, keep: Iterable[str] = ()
) -> None:
    """Make the role's live permissions exactly ``codes`` plus whatever of ``keep`` it holds."""
    wanted = sorted(set(codes))
    await conn.execute(
        text(
            "UPDATE role_permission SET deleted_at = now(), updated_at = now()"
            " WHERE role_id = :id AND deleted_at IS NULL"
            " AND NOT (permission_code = ANY(CAST(:wanted AS text[])))"
            " AND NOT (permission_code = ANY(CAST(:keep AS text[])))"
        ),
        {"id": role_id, "wanted": wanted, "keep": sorted(set(keep))},
    )
    if wanted:
        await conn.execute(
            text(
                "INSERT INTO role_permission (id, tenant_id, role_id, permission_code)"
                f" SELECT gen_random_uuid(), {_TENANT}, :id, code"
                " FROM unnest(CAST(:wanted AS text[])) AS code"
                " ON CONFLICT (role_id, permission_code) WHERE deleted_at IS NULL DO NOTHING"
            ),
            {"id": role_id, "wanted": wanted},
        )


async def role_in_use(conn: AsyncConnection, role_id: UUID) -> bool:
    """True while a live assignment (current or future) holds the role."""
    row = await conn.execute(
        text(
            "SELECT 1 FROM role_assignment WHERE role_id = :id AND deleted_at IS NULL"
            " AND (valid_to IS NULL OR valid_to > now()) LIMIT 1"
        ),
        {"id": role_id},
    )
    return row.first() is not None


async def active_grants(
    conn: AsyncConnection, user_id: UUID
) -> list[tuple[str, str, UUID | None, UUID | None]]:
    """``(permission, scope_type, project_id, team_id)`` from the active user's live, current
    tenant/project assignments and the team assignments of the teams the user is a live member of.
    """
    rows = await conn.execute(
        text(
            "SELECT DISTINCT rp.permission_code, ra.scope_type, ra.project_id, ra.team_id"
            " FROM role_assignment ra"
            " JOIN role r ON r.id = ra.role_id AND r.deleted_at IS NULL"
            " JOIN role_permission rp ON rp.role_id = r.id AND rp.deleted_at IS NULL"
            " WHERE ra.deleted_at IS NULL AND ra.valid_from <= now()"
            " AND (ra.valid_to IS NULL OR ra.valid_to > now())"
            " AND EXISTS (SELECT 1 FROM app_user u WHERE u.id = :user AND u.status = 'active'"
            "             AND u.deleted_at IS NULL)"
            " AND ((ra.scope_type IN ('tenant', 'project') AND ra.user_id = :user)"
            "   OR (ra.scope_type = 'team' AND ra.team_id IN"
            "       (SELECT tm.team_id FROM team_member tm JOIN team t ON t.id = tm.team_id"
            "        WHERE tm.user_id = :user AND tm.deleted_at IS NULL"
            "        AND t.deleted_at IS NULL)))"
        ),
        {"user": user_id},
    )
    return [(r[0], r[1], r[2], r[3]) for r in rows]


async def member_teams(conn: AsyncConnection, user_id: UUID) -> dict[UUID, UUID | None]:
    """``{team id: team project or None}`` for every live team the user is a live member of."""
    rows = await conn.execute(
        text(
            "SELECT t.id, t.project_id FROM team_member tm"
            " JOIN team t ON t.id = tm.team_id AND t.deleted_at IS NULL"
            " WHERE tm.user_id = :user AND tm.deleted_at IS NULL"
        ),
        {"user": user_id},
    )
    return {r[0]: r[1] for r in rows}


async def has_role(
    conn: AsyncConnection, user_id: UUID, role_code: str, project_id: UUID | None = None
) -> bool:
    """Whether the user actively holds role ``role_code`` at tenant scope, or (with
    ``project_id``) on that project. Team and asset-subtree scopes never count here. Matches only
    the connection's tenant, also on a connection that bypasses RLS."""
    row = await conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM role_assignment ra"
            " JOIN role r ON r.id = ra.role_id AND r.deleted_at IS NULL"
            " WHERE ra.user_id = :user AND r.code = :code AND"
            " ra.tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND"
            " (ra.scope_type = 'tenant' OR"
            "  (ra.scope_type = 'project' AND ra.project_id = CAST(:project AS uuid))) AND"
            f" {ACTIVE_ASSIGNMENT})"
        ),
        {"user": user_id, "code": role_code, "project": project_id},
    )
    return bool(row.scalar_one())


async def role_code_for_id(conn: AsyncConnection, role_id: UUID) -> str | None:
    """The code of live role ``role_id`` in the connection's tenant, else ``None``. Matches only
    the connection's tenant, also on a connection that bypasses RLS."""
    row = await conn.execute(
        text(
            f"SELECT code FROM role WHERE id = :id AND deleted_at IS NULL AND tenant_id = {_TENANT}"
        ),
        {"id": role_id},
    )
    return row.scalar_one_or_none()


async def role_codes(
    conn: AsyncConnection, user_id: UUID, project_id: UUID | None = None
) -> list[str]:
    """The codes of the roles the user actively holds at tenant scope, or (with ``project_id``)
    on that project, sorted. Same scope rules as ``has_role``."""
    rows = await conn.execute(
        text(
            "SELECT DISTINCT r.code FROM role_assignment ra"
            " JOIN role r ON r.id = ra.role_id AND r.deleted_at IS NULL"
            " WHERE ra.user_id = :user AND"
            " ra.tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND"
            " (ra.scope_type = 'tenant' OR"
            "  (ra.scope_type = 'project' AND ra.project_id = CAST(:project AS uuid))) AND"
            f" {ACTIVE_ASSIGNMENT}"
            " ORDER BY r.code"
        ),
        {"user": user_id, "project": project_id},
    )
    return [str(r[0]) for r in rows]


async def count_holders(
    conn: AsyncConnection, *, permission: str | None = None, role_code: str | None = None
) -> int:
    """Distinct active users holding ``permission`` (or role ``role_code``) at tenant scope."""
    if (permission is None) == (role_code is None):
        raise ValueError("pass exactly one of permission or role_code")
    if permission is not None:
        match = (
            "EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id"
            " AND rp.deleted_at IS NULL AND rp.permission_code = :value)"
        )
        value = permission
    else:
        match = "r.code = :value"
        value = role_code
    row = await conn.execute(
        text(
            "SELECT count(DISTINCT ra.user_id) FROM role_assignment ra"
            " JOIN role r ON r.id = ra.role_id AND r.deleted_at IS NULL"
            f" WHERE ra.scope_type = 'tenant' AND {match} AND {ACTIVE_ASSIGNMENT}"
        ),
        {"value": value},
    )
    return int(row.scalar_one())


async def holds_role_at_tenant(conn: AsyncConnection, user_id: UUID, role_code: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM role_assignment ra"
            " JOIN role r ON r.id = ra.role_id AND r.deleted_at IS NULL"
            " WHERE ra.user_id = :user AND r.code = :code AND ra.scope_type = 'tenant'"
            f" AND {ACTIVE_ASSIGNMENT} LIMIT 1"
        ),
        {"user": user_id, "code": role_code},
    )
    return row.first() is not None


async def has_live_tenant_assignment(conn: AsyncConnection, user_id: UUID, role_id: UUID) -> bool:
    """A live (not deleted) tenant-scope assignment exists, whatever the user's status."""
    row = await conn.execute(
        text(
            "SELECT 1 FROM role_assignment WHERE user_id = :user AND role_id = :role"
            " AND scope_type = 'tenant' AND deleted_at IS NULL LIMIT 1"
        ),
        {"user": user_id, "role": role_id},
    )
    return row.first() is not None


_ASSIGNMENT_COLUMNS = (
    "ra.id, ra.user_id, ra.team_id, ra.role_id, r.code AS role_code, ra.scope_type,"
    " ra.project_id, ra.source, ra.valid_from, ra.valid_to, ra.approved_by, ra.created_by,"
    " ra.created_at"
)


async def list_assignments(
    conn: AsyncConnection,
    *,
    user_id: UUID | None,
    project_id: UUID | None,
    team_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Live (not soft-deleted) assignments, newest first; expired ones are included."""
    filters = ["ra.deleted_at IS NULL"]
    params: dict[str, Any] = {}
    if user_id is not None:
        filters.append("ra.user_id = :user")
        params["user"] = user_id
    if project_id is not None:
        filters.append("ra.project_id = :project")
        params["project"] = project_id
    if team_id is not None:
        filters.append("ra.team_id = :team")
        params["team"] = team_id
    rows = await conn.execute(
        text(
            f"SELECT {_ASSIGNMENT_COLUMNS} FROM role_assignment ra"
            " JOIN role r ON r.id = ra.role_id"
            f" WHERE {' AND '.join(filters)} ORDER BY ra.created_at DESC, ra.id LIMIT 1000"
        ),
        params,
    )
    return [dict(r._mapping) for r in rows]


async def get_assignment(conn: AsyncConnection, assignment_id: UUID) -> dict[str, Any] | None:
    row = (
        await conn.execute(
            text(
                f"SELECT {_ASSIGNMENT_COLUMNS} FROM role_assignment ra"
                " JOIN role r ON r.id = ra.role_id"
                " WHERE ra.id = :id AND ra.deleted_at IS NULL"
            ),
            {"id": assignment_id},
        )
    ).first()
    return None if row is None else dict(row._mapping)


async def insert_assignment(
    conn: AsyncConnection,
    *,
    assignment_id: UUID,
    user_id: UUID | None,
    role_id: UUID,
    scope_type: str,
    project_id: UUID | None,
    valid_to: datetime | None,
    approved_by: UUID | None,
    created_by: UUID | None,
    team_id: UUID | None = None,
) -> None:
    await conn.execute(
        text(
            "INSERT INTO role_assignment (id, tenant_id, user_id, team_id, role_id, scope_type,"
            " project_id, valid_to, approved_by, created_by)"
            f" VALUES (:id, {_TENANT}, :user, :team, :role, :scope, :project, :valid_to,"
            " :approved, :created)"
        ),
        {
            "id": assignment_id,
            "user": user_id,
            "team": team_id,
            "role": role_id,
            "scope": scope_type,
            "project": project_id,
            "valid_to": valid_to,
            "approved": approved_by,
            "created": created_by,
        },
    )


async def soft_delete_assignment(conn: AsyncConnection, assignment_id: UUID) -> None:
    await conn.execute(
        text(
            "UPDATE role_assignment SET deleted_at = now(), updated_at = now()"
            " WHERE id = :id AND deleted_at IS NULL"
        ),
        {"id": assignment_id},
    )


async def live_user_assignments(conn: AsyncConnection, user_id: UUID) -> list[dict[str, Any]]:
    """Every live assignment held by the user directly (any scope), locked for update."""
    rows = await conn.execute(
        text(
            f"SELECT {_ASSIGNMENT_COLUMNS} FROM role_assignment ra"
            " JOIN role r ON r.id = ra.role_id"
            " WHERE ra.user_id = :user AND ra.deleted_at IS NULL ORDER BY ra.created_at, ra.id"
            " FOR UPDATE OF ra"
        ),
        {"user": user_id},
    )
    return [dict(r._mapping) for r in rows]
