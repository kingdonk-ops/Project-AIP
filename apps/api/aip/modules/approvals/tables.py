"""SQLAlchemy Core declarations for approvals (APPROVALS-01, ADR 0002).

Created only by the Alembic revision ``202610161400_approvals_workflows``; ``aip-db check-schema``
compares these declarations with the migrated database. ``workflow_definitions`` and
``workflow_instances`` are tenant-scoped with soft delete; ``workflow_definition_audit`` is
append-only (monthly partitions, PK ``(id, created_at)``). ``workflow_decision_history``
(APPROVALS-02, revision ``202610181200``) is append-only and hash-chained, not partitioned. All
four have FORCE ROW LEVEL SECURITY. APPROVALS-04 (revision ``202610311900``) adds
``approval_route_templates`` and ``approval_steps`` (tenant-scoped, soft delete, FORCE RLS) and the
route columns of ``workflow_instances``.
"""

from __future__ import annotations

from sqlalchemy import CHAR, Boolean, Column, Integer, Numeric, SmallInteger, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

__all__ = [
    "approval_route_templates",
    "approval_steps",
    "workflow_decision_history",
    "workflow_definition_audit",
    "workflow_definitions",
    "workflow_instances",
]

workflow_definitions = Table(
    "workflow_definitions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("record_type", Text, nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("key", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("states", JSONB, nullable=False),
    Column("transitions", JSONB, nullable=False),
    Column("initial_state", Text, nullable=False),
    Column("is_preset", Boolean, nullable=False, server_default=text("false")),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

workflow_instances = Table(
    "workflow_instances",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("definition_id", UUID(as_uuid=True), nullable=False),
    Column("record_type", Text, nullable=False),
    Column("record_id", UUID(as_uuid=True), nullable=False),
    Column("asset_id", UUID(as_uuid=True), nullable=True),
    Column("current_state", Text, nullable=False),
    Column("record_value", Numeric(18, 2), nullable=True),
    Column("currency", CHAR(3), nullable=True),
    Column("visibility_scope", Text, nullable=True),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    Column("client_generated_id", UUID(as_uuid=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("route_template_id", UUID(as_uuid=True), nullable=True),
    Column("current_step_id", UUID(as_uuid=True), nullable=True),
    Column("route_round", Integer, nullable=False, server_default=text("0")),
    Column("route_submitted_by", UUID(as_uuid=True), nullable=True),
)

workflow_definition_audit = Table(
    "workflow_definition_audit",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("definition_id", UUID(as_uuid=True), nullable=False),
    Column("actor_id", UUID(as_uuid=True), nullable=True),
    Column("change", JSONB, nullable=False),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        primary_key=True,
        server_default=text("now()"),
    ),
)


workflow_decision_history = Table(
    "workflow_decision_history",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("instance_id", UUID(as_uuid=True), nullable=False),
    Column("step_id", UUID(as_uuid=True), nullable=True),
    Column("seq", Integer, nullable=False),
    Column("from_state", Text, nullable=False),
    Column("to_state", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("actor_id", UUID(as_uuid=True), nullable=True),
    Column("on_behalf_of", UUID(as_uuid=True), nullable=True),
    Column("comment", Text, nullable=True),
    Column("auth_strength", Text, nullable=True),
    Column("ip_address", Text, nullable=True),
    Column("guard_result", JSONB, nullable=True),
    Column("supersedes_id", UUID(as_uuid=True), nullable=True),
    Column("status", Text, nullable=False),
    Column("countersigns_id", UUID(as_uuid=True), nullable=True),
    Column("assurance_level", SmallInteger, nullable=True),
    Column("assurance_method", Text, nullable=True),
    Column("authenticated_at", TIMESTAMP(timezone=True), nullable=True),
    Column("device_id", UUID(as_uuid=True), nullable=True),
    Column("prev_hash", Text, nullable=False),
    Column("entry_hash", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
)


approval_route_templates = Table(
    "approval_route_templates",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("name", Text, nullable=False),
    Column("record_type", Text, nullable=False),
    Column("conditions", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("threshold_bands", JSONB, nullable=True),
    Column("escalation_hours", Integer, nullable=True),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("on_approved_action", Text, nullable=False),
    Column("on_rejected_action", Text, nullable=False),
    Column("allow_self_approval", Boolean, nullable=False, server_default=text("false")),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

approval_steps = Table(
    "approval_steps",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("route_template_id", UUID(as_uuid=True), nullable=False),
    Column("instance_id", UUID(as_uuid=True), nullable=True),
    Column("route_round", Integer, nullable=True),
    Column("step_order", Integer, nullable=False),
    Column("mode", Text, nullable=False),
    Column("approver_type", Text, nullable=False),
    Column("approver_ref", UUID(as_uuid=True), nullable=False),
    Column("required_discipline_id", UUID(as_uuid=True), nullable=True),
    Column("due_hours", Integer, nullable=True),
    Column("due_at", TIMESTAMP(timezone=True), nullable=True),
    Column("status", Text, nullable=True),
    Column("decided_by", UUID(as_uuid=True), nullable=True),
    Column("decided_at", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)
