"""SQLAlchemy Core declarations for report templates (REPORTS-01, ADR 0002).

Created only by the Alembic revision ``202610281500_report_engine_templates``; ``aip-db
check-schema`` compares these declarations with the migrated database. The table is tenant-scoped
with soft delete and FORCE ROW LEVEL SECURITY, ``aip_app`` has no DELETE on it, and the
``report_templates_published_immutable`` trigger freezes a row once it leaves ``draft``.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

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
