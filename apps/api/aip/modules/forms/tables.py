"""SQLAlchemy Core declarations for the forms tables (FORMS-01, ADR 0002).

Created only by the Alembic revision ``202610261200_forms_templates_revisions`` (FORMS-10 adds
``form_templates.has_supervisor_review`` in ``202611011300_forms_supervisor_review``); ``aip-db
check-schema`` compares these declarations with the migrated database. Both tables are
tenant-scoped with soft delete and FORCE ROW LEVEL SECURITY, and ``aip_app`` has no DELETE on
either. ``form_templates`` carries the offline-sync columns (``sync=True`` in the migration);
``form_revisions`` is frozen once published by a database trigger, so it has no ``sync_version``.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

form_templates = Table(
    "form_templates",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("current_revision_id", UUID(as_uuid=True), nullable=True),
    Column("has_supervisor_review", Boolean, nullable=False, server_default=text("true")),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    Column("client_generated_id", UUID(as_uuid=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

form_revisions = Table(
    "form_revisions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("template_id", UUID(as_uuid=True), nullable=False),
    Column("revision_no", Integer, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("schema", JSONB, nullable=False),
    Column("schema_hash", Text, nullable=True),
    Column("evaluator_version", Text, nullable=True),
    Column("change_note", Text, nullable=True),
    Column("published_at", TIMESTAMP(timezone=True), nullable=True),
    Column("published_by", UUID(as_uuid=True), nullable=True),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)
