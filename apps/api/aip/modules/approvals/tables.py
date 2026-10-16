"""SQLAlchemy Core declarations for approvals (APPROVALS-01, ADR 0002).

Created only by the Alembic revision ``202610161400_approvals_workflows``; ``aip-db check-schema``
compares these declarations with the migrated database. ``workflow_definitions`` and
``workflow_instances`` are tenant-scoped with soft delete; ``workflow_definition_audit`` is
append-only (monthly partitions, PK ``(id, created_at)``). All three have FORCE ROW LEVEL SECURITY.
"""

from __future__ import annotations

from sqlalchemy import CHAR, Boolean, Column, Integer, Numeric, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

__all__ = ["workflow_definition_audit", "workflow_definitions", "workflow_instances"]

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
