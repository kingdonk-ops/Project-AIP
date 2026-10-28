"""SQLAlchemy Core declarations for the item_types tables (ITEMTYPES-01/02, ADR 0002).

Created only by the Alembic revisions ``202610251200_item_types_core`` and
``202610281300_item_types_versions``; ``aip-db check-schema`` compares these declarations with the
migrated database. All four tables are tenant-scoped with soft delete and FORCE ROW LEVEL SECURITY;
``aip_app`` has no DELETE on any of them. A published ``item_type_versions`` row is frozen by a
database trigger.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

content_types = Table(
    "content_types",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("key", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("icon", Text, nullable=False, server_default=text("'folder'")),
    Column("sort_order", Integer, nullable=False, server_default=text("0")),
    Column("show_in_nav", Boolean, nullable=False, server_default=text("true")),
    Column("is_system", Boolean, nullable=False, server_default=text("false")),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

item_categories = Table(
    "item_categories",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("content_type_id", UUID(as_uuid=True), nullable=False),
    Column("key", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("applicable_for", Text, nullable=False, server_default=text("'any'")),
    Column("sort_order", Integer, nullable=False, server_default=text("0")),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

item_types = Table(
    "item_types",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("category_id", UUID(as_uuid=True), nullable=False),
    Column("key", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("is_component", Boolean, nullable=False, server_default=text("false")),
    Column("allows_components", Boolean, nullable=False, server_default=text("false")),
    Column("published_version_id", UUID(as_uuid=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

item_type_versions = Table(
    "item_type_versions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("item_type_id", UUID(as_uuid=True), nullable=False),
    Column("version", Integer, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("attributes", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("compiled_schema", JSONB, nullable=True),
    Column("change_summary", Text, nullable=True),
    Column("published_at", TIMESTAMP(timezone=True), nullable=True),
    Column("published_by", UUID(as_uuid=True), nullable=True),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)
