"""SQLAlchemy Core declarations for the terminology dictionary (TERMS-01, ADR 0002).

Created only by the Alembic revision ``202610141200_terms_tables``; ``aip-db check-schema``
compares these declarations with the migrated database. Every table is tenant-scoped with FORCE
ROW LEVEL SECURITY; rows of the platform tenant (the nil UUID, ADR 0028) are readable by every
tenant and writable only by ``aip_owner``. ``aip_app`` has no DELETE (soft delete) and only
SELECT on ``term_key`` (the platform key catalogue).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata


def _id_and_tenant() -> list[Column[Any]]:
    return [
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("tenant_id", UUID(as_uuid=True), nullable=False),
    ]


def _timestamps() -> list[Column[Any]]:
    return [
        Column(
            "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
        ),
        Column(
            "updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
        ),
        Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    ]


term_key = Table(
    "term_key",
    metadata,
    *_id_and_tenant(),
    Column("key", Text, nullable=False),
    Column("module_id", Text, nullable=False),
    Column("default_locale", Text, nullable=False, server_default=text("'en-AU'")),
    Column("default_text", Text, nullable=False),
    Column("description", Text, nullable=True),
    *_timestamps(),
)

term_pack = Table(
    "term_pack",
    metadata,
    *_id_and_tenant(),
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("active_version_id", UUID(as_uuid=True), nullable=True),
    *_timestamps(),
)

# Append-only in use (aip_app has no UPDATE); the template's updated_at/deleted_at stay unused.
term_pack_version = Table(
    "term_pack_version",
    metadata,
    *_id_and_tenant(),
    Column("pack_id", UUID(as_uuid=True), nullable=False),
    Column("version", Integer, nullable=False),
    Column("contents", JSONB, nullable=False),
    Column("contents_sha256", Text, nullable=False),
    Column("change_summary", JSONB, nullable=True),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    *_timestamps(),
)

term_override = Table(
    "term_override",
    metadata,
    *_id_and_tenant(),
    Column("level", Text, nullable=False),
    Column("client_org_id", UUID(as_uuid=True), nullable=True),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("key", Text, nullable=False),
    Column("locale", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    *_timestamps(),
)

glossary_entry = Table(
    "glossary_entry",
    metadata,
    *_id_and_tenant(),
    Column("term", Text, nullable=False),
    Column("abbreviation", Text, nullable=True),
    Column("definition", Text, nullable=False),
    Column("neutral_concept_code", Text, nullable=True),
    Column("locale", Text, nullable=False),
    *_timestamps(),
)

term_alias = Table(
    "term_alias",
    metadata,
    *_id_and_tenant(),
    Column("alias", Text, nullable=False),
    Column("target_type", Text, nullable=False),
    Column("target_code", Text, nullable=False),
    Column("locale", Text, nullable=False),
    *_timestamps(),
)

locale_settings = Table(
    "locale_settings",
    metadata,
    *_id_and_tenant(),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("locale", Text, nullable=False, server_default=text("'en-AU'")),
    Column("date_format", Text, nullable=True),
    Column("number_format", Text, nullable=True),
    Column("unit_system", Text, nullable=False, server_default=text("'metric'")),
    Column("unit_overrides", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("timezone", Text, nullable=True),
    *_timestamps(),
)
