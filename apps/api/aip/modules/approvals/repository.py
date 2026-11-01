"""Data access for approvals (APPROVALS-01, APPROVALS-02; route steps are ``routes_engine``).

Repositories receive the tenant-bound connection from ``with_tenant`` and never create their own
(ADR 0002). ``tenant_id`` on new rows is the connection's ``app.tenant_id``, never a parameter.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_DEFINITION_COLUMNS = (
    "id, record_type, project_id, key, version, status, states, transitions, initial_state, "
    "created_by, created_at, updated_at"
)

# Serialises version numbering per key within the tenant (two drafts at once would otherwise both
# compute the same max + 1 and one would fail on the unique constraint).
_LOCK_KEY = text(
    "SELECT pg_advisory_xact_lock(hashtextextended(current_setting('app.tenant_id') || :lock, 0))"
)

_NEXT_VERSION = text("""
SELECT coalesce(max(version), 0) + 1 FROM workflow_definitions WHERE key = :key
""")

_INSERT_DEFINITION = text(f"""
INSERT INTO workflow_definitions
  (id, tenant_id, record_type, project_id, key, version, status, states, transitions,
   initial_state, created_by)
VALUES
  (:id, {_TENANT}, :record_type, :project_id, :key, :version, 'draft',
   CAST(:states AS jsonb), CAST(:transitions AS jsonb), :initial_state, :created_by)
RETURNING {_DEFINITION_COLUMNS}
""")

_GET_FOR_UPDATE = text(f"""
SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions
WHERE id = :id AND deleted_at IS NULL
FOR UPDATE
""")

_UPDATE_SPEC = text(f"""
UPDATE workflow_definitions
SET states = CAST(:states AS jsonb), transitions = CAST(:transitions AS jsonb),
    initial_state = :initial_state, updated_at = now()
WHERE id = :id
RETURNING {_DEFINITION_COLUMNS}
""")

_ACTIVE_IN_SCOPE_FOR_UPDATE = text(f"""
SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions
WHERE key = :key AND project_id IS NOT DISTINCT FROM :project_id
  AND status = 'active' AND deleted_at IS NULL
FOR UPDATE
""")

_SET_STATUS = text(f"""
UPDATE workflow_definitions SET status = :status, updated_at = now()
WHERE id = :id
RETURNING {_DEFINITION_COLUMNS}
""")

_INSERT_AUDIT = text(f"""
INSERT INTO workflow_definition_audit (id, tenant_id, definition_id, actor_id, change)
VALUES (:id, {_TENANT}, :definition_id, :actor_id, CAST(:change AS jsonb))
""")

# Project-specific first, then tenant-wide. Several keys could be active for one record type;
# the lowest key wins so the choice is stable.
_RESOLVE_ACTIVE = text(f"""
SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions
WHERE record_type = :record_type AND status = 'active' AND deleted_at IS NULL
  AND (project_id IS NULL OR project_id = :project_id)
ORDER BY (project_id IS NULL), key
LIMIT 1
""")

_INSTANCE_COLUMNS = (
    "i.id, i.definition_id, d.version, i.record_type, i.record_id, i.project_id, "
    "i.current_state, i.sync_version, i.route_template_id, i.current_step_id, i.route_round, "
    "i.route_submitted_by"
)

_GET_DEFINITION = text(f"""
SELECT {_DEFINITION_COLUMNS} FROM workflow_definitions WHERE id = :id
""")

# Locks the instance row only (FOR UPDATE OF i): concurrent transitions on one instance queue here,
# and the definition row stays free for a concurrent publish.
_INSTANCE_BY_ID = f"""
SELECT {_INSTANCE_COLUMNS}, d.key AS definition_key
FROM workflow_instances i JOIN workflow_definitions d ON d.id = i.definition_id
WHERE i.id = :id AND i.deleted_at IS NULL
"""
_GET_INSTANCE_BY_ID = text(_INSTANCE_BY_ID)
_GET_INSTANCE_FOR_UPDATE = text(_INSTANCE_BY_ID + "FOR UPDATE OF i")

_DECISION_COLUMNS = (
    "id, tenant_id, instance_id, step_id, seq, from_state, to_state, action, actor_id, "
    "on_behalf_of, comment, auth_strength, ip_address, guard_result, supersedes_id, status, "
    "countersigns_id, assurance_level, assurance_method, authenticated_at, device_id, prev_hash, "
    "entry_hash, created_at"
)

_LAST_DECISION = text(f"""
SELECT {_DECISION_COLUMNS} FROM workflow_decision_history
WHERE instance_id = :instance_id
ORDER BY seq DESC
LIMIT 1
""")

_LIST_DECISIONS = text(f"""
SELECT {_DECISION_COLUMNS} FROM workflow_decision_history
WHERE instance_id = :instance_id
ORDER BY seq
""")

_INSERT_DECISION = text("""
INSERT INTO workflow_decision_history
  (id, tenant_id, instance_id, step_id, seq, from_state, to_state, action, actor_id,
   on_behalf_of, comment, auth_strength, ip_address, guard_result, status, countersigns_id,
   assurance_level, assurance_method, authenticated_at, device_id, prev_hash, entry_hash,
   created_at)
VALUES
  (:id, :tenant_id, :instance_id, :step_id, :seq, :from_state, :to_state, :action, :actor_id,
   :on_behalf_of, :comment, :auth_strength, :ip_address, CAST(:guard_result AS jsonb), :status,
   :countersigns_id, :assurance_level, :assurance_method, :authenticated_at, :device_id,
   :prev_hash, :entry_hash, :created_at)
""")

_GET_INSTANCE = text(f"""
SELECT {_INSTANCE_COLUMNS}
FROM workflow_instances i JOIN workflow_definitions d ON d.id = i.definition_id
WHERE i.record_type = :record_type AND i.record_id = :record_id AND i.deleted_at IS NULL
""")

# DO UPDATE (a no-op) rather than DO NOTHING: a concurrent start returns the winner's row.
_INSERT_INSTANCE = text(f"""
WITH ins AS (
  INSERT INTO workflow_instances
    (id, tenant_id, project_id, definition_id, record_type, record_id, current_state, created_by)
  VALUES
    (:id, {_TENANT}, :project_id, :definition_id, :record_type, :record_id, :current_state,
     :created_by)
  ON CONFLICT (tenant_id, record_type, record_id) WHERE deleted_at IS NULL
  DO UPDATE SET updated_at = workflow_instances.updated_at
  RETURNING *
)
SELECT {_INSTANCE_COLUMNS} FROM ins i JOIN workflow_definitions d ON d.id = i.definition_id
""")


def _spec_params(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "states": json.dumps(spec["states"]),
        "transitions": json.dumps(spec["transitions"]),
        "initial_state": spec["initial"],
    }


async def lock_key(conn: AsyncConnection, key: str) -> None:
    await conn.execute(_LOCK_KEY, {"lock": f"approvals.definition:{key}"})


async def next_version(conn: AsyncConnection, key: str) -> int:
    return int((await conn.execute(_NEXT_VERSION, {"key": key})).scalar_one())


async def insert_definition(conn: AsyncConnection, **values: Any) -> RowMapping:
    spec = values.pop("spec")
    params = {**values, **_spec_params(spec)}
    return (await conn.execute(_INSERT_DEFINITION, params)).mappings().one()


async def get_definition_for_update(
    conn: AsyncConnection, definition_id: UUID
) -> RowMapping | None:
    return (await conn.execute(_GET_FOR_UPDATE, {"id": definition_id})).mappings().one_or_none()


async def update_spec(
    conn: AsyncConnection, definition_id: UUID, spec: dict[str, Any]
) -> RowMapping:
    params = {"id": definition_id, **_spec_params(spec)}
    return (await conn.execute(_UPDATE_SPEC, params)).mappings().one()


async def active_in_scope_for_update(
    conn: AsyncConnection, key: str, project_id: UUID | None
) -> RowMapping | None:
    params = {"key": key, "project_id": project_id}
    return (await conn.execute(_ACTIVE_IN_SCOPE_FOR_UPDATE, params)).mappings().one_or_none()


async def set_status(conn: AsyncConnection, definition_id: UUID, status: str) -> RowMapping:
    params = {"id": definition_id, "status": status}
    return (await conn.execute(_SET_STATUS, params)).mappings().one()


async def insert_audit(conn: AsyncConnection, **values: Any) -> None:
    values["change"] = json.dumps(values["change"])
    await conn.execute(_INSERT_AUDIT, values)


async def resolve_active(
    conn: AsyncConnection, record_type: str, project_id: UUID | None
) -> RowMapping | None:
    params = {"record_type": record_type, "project_id": project_id}
    return (await conn.execute(_RESOLVE_ACTIVE, params)).mappings().one_or_none()


async def get_instance(
    conn: AsyncConnection, record_type: str, record_id: UUID
) -> RowMapping | None:
    params = {"record_type": record_type, "record_id": record_id}
    return (await conn.execute(_GET_INSTANCE, params)).mappings().one_or_none()


async def insert_instance(conn: AsyncConnection, **values: Any) -> RowMapping:
    return (await conn.execute(_INSERT_INSTANCE, values)).mappings().one()


async def get_definition(conn: AsyncConnection, definition_id: UUID) -> RowMapping:
    """A definition by id, whatever its status (an instance's pinned version may be retired)."""
    return (await conn.execute(_GET_DEFINITION, {"id": definition_id})).mappings().one()


async def get_instance_by_id(
    conn: AsyncConnection, instance_id: UUID, *, for_update: bool = False
) -> RowMapping | None:
    stmt = _GET_INSTANCE_FOR_UPDATE if for_update else _GET_INSTANCE_BY_ID
    return (await conn.execute(stmt, {"id": instance_id})).mappings().one_or_none()


async def last_decision(conn: AsyncConnection, instance_id: UUID) -> RowMapping | None:
    params = {"instance_id": instance_id}
    return (await conn.execute(_LAST_DECISION, params)).mappings().one_or_none()


async def list_decisions(conn: AsyncConnection, instance_id: UUID) -> list[RowMapping]:
    params = {"instance_id": instance_id}
    return list((await conn.execute(_LIST_DECISIONS, params)).mappings().all())


async def insert_decision(conn: AsyncConnection, entry: dict[str, Any]) -> None:
    """Insert a fully built entry (its hash is computed over exactly these values)."""
    guard = entry["guard_result"]
    params = {**entry, "guard_result": None if guard is None else json.dumps(guard)}
    await conn.execute(_INSERT_DECISION, params)
