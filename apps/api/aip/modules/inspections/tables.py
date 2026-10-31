"""SQLAlchemy Core declaration for inspections (INSPECTIONS-01, ADR 0002).

Created only by the Alembic revision ``202610311600_inspections_core``; ``aip-db check-schema``
compares this declaration with the migrated database. The table is tenant-scoped with soft delete,
FORCE ROW LEVEL SECURITY and the ACCESS-03 project-scope policy; ``aip_app`` has no DELETE.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

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
