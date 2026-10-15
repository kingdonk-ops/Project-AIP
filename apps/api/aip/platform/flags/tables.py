"""SQLAlchemy Core declaration of ``tenant_feature_flags`` (ARCH-08, ADR 0002/0008).

Created only by the Alembic revision ``202610161000_record_links_feature_flags``; ``aip-db
check-schema`` compares this declaration with the migrated database. A tenant table: FORCE RLS on
``app.tenant_id``, soft delete only (``aip_app`` has no DELETE), and at most one live row per
``(tenant_id, flag)``. A missing row means the flag's default from the code registry.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, Table, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

__all__ = ["tenant_feature_flags"]

tenant_feature_flags = Table(
    "tenant_feature_flags",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
    Column("flag", Text, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("updated_by", UUID(as_uuid=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)
