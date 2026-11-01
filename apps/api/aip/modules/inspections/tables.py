"""SQLAlchemy Core declarations for inspections (INSPECTIONS-01, INSPECTIONS-02, ADR 0002).

Created only by the Alembic revisions ``202610311800_inspections_core`` and
``202611011000_inspections_responses``; ``aip-db check-schema`` compares these declarations with the
migrated database.

- ``inspections`` is tenant-scoped with soft delete, FORCE ROW LEVEL SECURITY and the ACCESS-03
  project-scope policy; ``aip_app`` has no DELETE.
- ``inspection_responses`` is append-only evidence (monthly partitions, PK ``(id, created_at)``):
  ``aip_app`` has SELECT and INSERT only.
- ``inspection_current_responses`` is a view (the latest row per field). It is declared on its own
  ``MetaData``: check-schema compares tables only, so the shared one must not list it.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, MetaData, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

__all__ = ["inspection_current_responses", "inspection_responses", "inspections"]

inspections = Table(
    "inspections",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("asset_id", UUID(as_uuid=True), nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("template_id", UUID(as_uuid=True), nullable=False),
    Column("template_revision_id", UUID(as_uuid=True), nullable=False),
    Column("kind", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("source_ref_id", UUID(as_uuid=True), nullable=True),
    Column("itp_parent_id", UUID(as_uuid=True), nullable=True),
    Column("workflow_instance_id", UUID(as_uuid=True), nullable=False),
    Column("state", Text, nullable=False),
    Column("created_by", UUID(as_uuid=True), nullable=False),
    Column("client_generated_id", UUID(as_uuid=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

inspection_responses = Table(
    "inspection_responses",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("inspection_id", UUID(as_uuid=True), nullable=False),
    Column("field_key", Text, nullable=False),
    Column("value", JSONB(none_as_null=True), nullable=True),
    Column("failed", Boolean, nullable=False),
    Column("revision_id", UUID(as_uuid=True), nullable=False),
    Column("client_id", UUID(as_uuid=True), nullable=False),
    Column("supersedes_id", UUID(as_uuid=True), nullable=True),
    Column("responded_by", UUID(as_uuid=True), nullable=False),
    Column("responded_at", TIMESTAMP(timezone=True), nullable=False),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        primary_key=True,
        server_default=text("now()"),
    ),
)

inspection_current_responses = Table(
    "inspection_current_responses",
    MetaData(),
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("inspection_id", UUID(as_uuid=True), nullable=False),
    Column("field_key", Text, nullable=False),
    Column("value", JSONB(none_as_null=True), nullable=True),
    Column("failed", Boolean, nullable=False),
    Column("revision_id", UUID(as_uuid=True), nullable=False),
    Column("responded_by", UUID(as_uuid=True), nullable=False),
    Column("responded_at", TIMESTAMP(timezone=True), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
)
