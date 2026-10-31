"""SQLAlchemy Core declarations for report_engine (REPORTS-01, REPORTS-02, ADR 0002).

Created only by the Alembic revisions ``202610281500_report_engine_templates`` and
``202610311200_report_engine_render_jobs`` (``record_label`` by ``202610311500``); ``aip-db check-schema`` compares these declarations
with the migrated database. Every table has FORCE ROW LEVEL SECURITY.

- ``report_templates``: tenant-scoped with soft delete; ``aip_app`` has no DELETE on it, and the
  ``report_templates_published_immutable`` trigger freezes a row once it leaves ``draft``.
- ``report_data_snapshots``: append-only (no ``updated_at``/``deleted_at``; UPDATE, DELETE and
  TRUNCATE revoked from every runtime role), project-scoped. One row per distinct render input.
- ``report_render_jobs``: one row per render request (tenant table, project-scoped), pinned to a
  template version and a snapshot; the worker moves it ``queued -> running -> succeeded|failed``.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

__all__ = ["report_data_snapshots", "report_render_jobs", "report_templates"]

report_templates = Table(
    "report_templates",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("key", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("variant", Text, nullable=False),
    Column("record_type", Text, nullable=False),
    Column("name_key", Text, nullable=False),
    Column("orientation", Text, nullable=False),
    Column("paper", Text, nullable=False),
    Column("definition", JSONB, nullable=False),
    Column("body", Text, nullable=False),
    Column("css", Text, nullable=False),
    Column("assets", JSONB, nullable=False),
    Column("content_sha256", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("source", Text, nullable=False),
    Column("client_company_id", UUID(as_uuid=True), nullable=True),
    Column("published_at", TIMESTAMP(timezone=True), nullable=True),
    Column("published_by", UUID(as_uuid=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

report_data_snapshots = Table(
    "report_data_snapshots",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("record_type", Text, nullable=False),
    Column("record_id", UUID(as_uuid=True), nullable=False),
    Column("record_version", Integer, nullable=True),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("schema_version", Integer, nullable=False, server_default=text("1")),
    Column("data", JSONB, nullable=False),
    Column("data_hash", Text, nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
)

report_render_jobs = Table(
    "report_render_jobs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("template_id", UUID(as_uuid=True), nullable=False),
    Column("template_key", Text, nullable=False),
    Column("template_version", Integer, nullable=False),
    Column("variant", Text, nullable=False),
    Column("record_type", Text, nullable=False),
    Column("record_id", UUID(as_uuid=True), nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("snapshot_id", UUID(as_uuid=True), nullable=False),
    Column("data_hash", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'queued'")),
    Column("ops_job_id", UUID(as_uuid=True), nullable=True),
    Column("idempotency_key", Text, nullable=True),
    Column("trigger_event_id", UUID(as_uuid=True), nullable=True),
    Column("requested_by", UUID(as_uuid=True), nullable=True),
    Column("rerender_of", UUID(as_uuid=True), nullable=True),
    Column("html_sha256", Text, nullable=True),
    Column("file_id", UUID(as_uuid=True), nullable=True),
    Column("pdf_sha256", Text, nullable=True),
    Column("pdf_size_bytes", BigInteger, nullable=True),
    Column("error_code", Text, nullable=True),
    Column("rendered_at", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    # REPORTS-04: the source record's label at request time, for the register.
    Column("record_label", Text, nullable=True),
)
