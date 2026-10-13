"""SQLAlchemy Core declarations for projects and sites (PROJECTS-01, ADR 0002).

Created only by the Alembic revision ``202610131300_projects_sites``; ``aip-db check-schema``
compares these declarations with the migrated database. Both tables are tenant-scoped with soft
delete and FORCE ROW LEVEL SECURITY; ``aip_app`` has no DELETE on either.
"""

from __future__ import annotations

from sqlalchemy import CHAR, Boolean, Column, Integer, Numeric, Table, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

sites = Table(
    "sites",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("lat", Numeric(9, 6), nullable=True),
    Column("lng", Numeric(9, 6), nullable=True),
    Column("timezone", Text, nullable=True),
    Column("is_system", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

projects = Table(
    "projects",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("client_company_id", UUID(as_uuid=True), nullable=True),
    Column("site_id", UUID(as_uuid=True), nullable=True),
    Column("classification_id", UUID(as_uuid=True), nullable=True),
    Column("template_id", UUID(as_uuid=True), nullable=True),
    Column("region", Text, nullable=True),
    Column("timezone", Text, nullable=True),
    Column("currency", CHAR(3), nullable=True),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("closed_at", TIMESTAMP(timezone=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)
