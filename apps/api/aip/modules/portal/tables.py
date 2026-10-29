"""SQLAlchemy Core declarations for portal users and grants (PORTAL-01, ADR 0002).

Created only by the Alembic revision ``202610291100_portal_users_grants``; ``aip-db check-schema``
compares these declarations with the migrated database. Both tables are tenant-scoped with soft
delete and FORCE ROW LEVEL SECURITY; ``aip_app`` has no DELETE on either.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

portal_users = Table(
    "portal_users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("user_id", UUID(as_uuid=True), nullable=False),
    Column("company_name", Text, nullable=False),
    Column("organisation_id", UUID(as_uuid=True), nullable=True),
    Column("status", Text, nullable=False, server_default=text("'invited'")),
    Column("invited_by", UUID(as_uuid=True), nullable=False),
    Column("first_signed_in_at", TIMESTAMP(timezone=True), nullable=True),
    Column("suspended_at", TIMESTAMP(timezone=True), nullable=True),
    Column("suspended_reason", Text, nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

portal_grants = Table(
    "portal_grants",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("portal_user_id", UUID(as_uuid=True), nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("asset_id", UUID(as_uuid=True), nullable=True),
    Column("actions", ARRAY(Text), nullable=False),
    Column("access_days", Integer, nullable=False),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
    Column("renewed_at", TIMESTAMP(timezone=True), nullable=True),
    Column("renewed_by", UUID(as_uuid=True), nullable=True),
    Column("revoked_at", TIMESTAMP(timezone=True), nullable=True),
    Column("revoked_by", UUID(as_uuid=True), nullable=True),
    Column("revoked_reason", Text, nullable=True),
    Column("created_by", UUID(as_uuid=True), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)
