"""Data access for approval routes (APPROVALS-04).

Receives the tenant-bound connection from ``with_tenant`` and never creates its own (ADR 0002).
``tenant_id`` on new rows is the connection's ``app.tenant_id``, never a parameter. A template step
has no ``instance_id``; an instance step names its instance and ``route_round``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_TEMPLATE_COLUMNS = (
    "id, name, record_type, version, on_approved_action, on_rejected_action, "
    "allow_self_approval, created_by, created_at, updated_at"
)

_STEP_COLUMNS = (
    "id, route_template_id, instance_id, route_round, step_order, mode, approver_type, "
    "approver_ref, due_hours, due_at, status, decided_by, decided_at, created_at, updated_at"
)

_INSERT_TEMPLATE = text(f"""
INSERT INTO approval_route_templates
  (id, tenant_id, name, record_type, on_approved_action, on_rejected_action, allow_self_approval,
   created_by)
VALUES
  (:id, {_TENANT}, :name, :record_type, :on_approved_action, :on_rejected_action,
   :allow_self_approval, :created_by)
RETURNING {_TEMPLATE_COLUMNS}
""")

_INSERT_TEMPLATE_STEP = text(f"""
INSERT INTO approval_steps
  (id, tenant_id, route_template_id, step_order, mode, approver_type, approver_ref, due_hours)
VALUES
  (:id, {_TENANT}, :route_template_id, :step_order, :mode, :approver_type, :approver_ref,
   :due_hours)
RETURNING {_STEP_COLUMNS}
""")

_LIST_TEMPLATES = text(f"""
SELECT {_TEMPLATE_COLUMNS} FROM approval_route_templates
WHERE deleted_at IS NULL
ORDER BY name, id
""")

# A template by id even when soft-deleted: a running route keeps the template it started on.
_GET_TEMPLATE = text(f"""
SELECT {_TEMPLATE_COLUMNS}, deleted_at FROM approval_route_templates WHERE id = :id
""")

_TEMPLATE_STEPS = text(f"""
SELECT {_STEP_COLUMNS} FROM approval_steps
WHERE route_template_id = ANY(CAST(:ids AS uuid[])) AND instance_id IS NULL AND deleted_at IS NULL
ORDER BY route_template_id, step_order, id
""")

_INSERT_INSTANCE_STEP = text(f"""
INSERT INTO approval_steps
  (id, tenant_id, route_template_id, instance_id, route_round, step_order, mode, approver_type,
   approver_ref, due_hours, status)
VALUES
  (:id, {_TENANT}, :route_template_id, :instance_id, :route_round, :step_order, :mode,
   :approver_type, :approver_ref, :due_hours, 'waiting')
RETURNING {_STEP_COLUMNS}
""")

_ROUND_STEPS = text(f"""
SELECT {_STEP_COLUMNS} FROM approval_steps
WHERE instance_id = :instance_id AND route_round = :route_round AND deleted_at IS NULL
ORDER BY step_order, id
""")

_ACTIVATE_GROUP = text(f"""
UPDATE approval_steps
SET status = 'pending', updated_at = now(),
    due_at = CASE WHEN due_hours IS NULL THEN NULL
                  ELSE now() + make_interval(hours => due_hours) END
WHERE instance_id = :instance_id AND route_round = :route_round AND step_order = :step_order
  AND status = 'waiting' AND deleted_at IS NULL
RETURNING {_STEP_COLUMNS}
""")

_DECIDE_STEP = text(f"""
UPDATE approval_steps
SET status = :status, decided_by = :decided_by, decided_at = now(), updated_at = now()
WHERE id = :id AND status = 'pending'
RETURNING {_STEP_COLUMNS}
""")

_SKIP_STEPS = text("""
UPDATE approval_steps SET status = 'skipped', updated_at = now()
WHERE id = ANY(CAST(:ids AS uuid[])) AND status IN ('waiting', 'pending')
""")

_SKIP_OPEN_STEPS = text("""
UPDATE approval_steps SET status = 'skipped', updated_at = now()
WHERE instance_id = :instance_id AND route_round = :route_round
  AND status IN ('waiting', 'pending') AND deleted_at IS NULL
""")

# The inbox candidates: pending steps on live instances naming the user, one of the user's teams,
# or any role (role holding depends on the instance's project, so the service checks it).
_PENDING_CANDIDATES = text("""
SELECT s.id, s.route_template_id, s.instance_id, s.route_round, s.step_order, s.mode,
       s.approver_type, s.approver_ref, s.due_hours, s.due_at, s.status, s.decided_by,
       s.decided_at, s.created_at, s.updated_at,
       i.record_type, i.record_id, i.project_id, i.current_state
FROM approval_steps s JOIN workflow_instances i ON i.id = s.instance_id
WHERE s.status = 'pending' AND s.deleted_at IS NULL AND i.deleted_at IS NULL
  AND s.route_round = i.route_round
  AND ((s.approver_type = 'user' AND s.approver_ref = :user_id)
       OR (s.approver_type = 'team' AND s.approver_ref = ANY(CAST(:team_ids AS uuid[])))
       OR s.approver_type = 'role')
ORDER BY s.due_at NULLS LAST, s.created_at, s.id
LIMIT :limit
""")

__all__ = [
    "activate_group",
    "decide_step",
    "get_template",
    "insert_instance_step",
    "insert_template",
    "insert_template_step",
    "list_templates",
    "pending_candidates",
    "round_steps",
    "skip_open_steps",
    "skip_steps",
    "template_steps",
]


async def insert_template(conn: AsyncConnection, **values: Any) -> RowMapping:
    return (await conn.execute(_INSERT_TEMPLATE, values)).mappings().one()


async def insert_template_step(conn: AsyncConnection, **values: Any) -> RowMapping:
    return (await conn.execute(_INSERT_TEMPLATE_STEP, values)).mappings().one()


async def list_templates(conn: AsyncConnection) -> list[RowMapping]:
    return list((await conn.execute(_LIST_TEMPLATES)).mappings().all())


async def get_template(conn: AsyncConnection, template_id: UUID) -> RowMapping | None:
    return (await conn.execute(_GET_TEMPLATE, {"id": template_id})).mappings().one_or_none()


async def template_steps(conn: AsyncConnection, template_ids: Sequence[UUID]) -> list[RowMapping]:
    params = {"ids": list(template_ids)}
    return list((await conn.execute(_TEMPLATE_STEPS, params)).mappings().all())


async def insert_instance_step(conn: AsyncConnection, **values: Any) -> RowMapping:
    return (await conn.execute(_INSERT_INSTANCE_STEP, values)).mappings().one()


async def round_steps(
    conn: AsyncConnection, instance_id: UUID, route_round: int
) -> list[RowMapping]:
    params = {"instance_id": instance_id, "route_round": route_round}
    return list((await conn.execute(_ROUND_STEPS, params)).mappings().all())


async def activate_group(
    conn: AsyncConnection, instance_id: UUID, route_round: int, step_order: int
) -> list[RowMapping]:
    params = {"instance_id": instance_id, "route_round": route_round, "step_order": step_order}
    return list((await conn.execute(_ACTIVATE_GROUP, params)).mappings().all())


async def decide_step(
    conn: AsyncConnection, step_id: UUID, status: str, decided_by: UUID | None
) -> RowMapping:
    params = {"id": step_id, "status": status, "decided_by": decided_by}
    return (await conn.execute(_DECIDE_STEP, params)).mappings().one()


async def skip_steps(conn: AsyncConnection, step_ids: Sequence[UUID]) -> None:
    if step_ids:
        await conn.execute(_SKIP_STEPS, {"ids": list(step_ids)})


async def skip_open_steps(conn: AsyncConnection, instance_id: UUID, route_round: int) -> None:
    await conn.execute(_SKIP_OPEN_STEPS, {"instance_id": instance_id, "route_round": route_round})


async def pending_candidates(
    conn: AsyncConnection, user_id: UUID, team_ids: Sequence[UUID], limit: int
) -> list[RowMapping]:
    params = {"user_id": user_id, "team_ids": list(team_ids), "limit": limit}
    return list((await conn.execute(_PENDING_CANDIDATES, params)).mappings().all())
