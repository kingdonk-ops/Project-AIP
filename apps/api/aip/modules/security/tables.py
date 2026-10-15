"""SQLAlchemy Core declarations for the security tables (SECURITY-02, ADR 0002).

Created only by the Alembic revision ``202610151900_security_tables``; ``aip-db check-schema``
compares these declarations with the migrated database. Every table is tenant-scoped with FORCE
ROW LEVEL SECURITY.

- Mutable, soft delete (``aip_app`` has no DELETE): ``control_records``, ``access_reviews``,
  ``data_map_entries``, ``breach_incidents``.
- Append-only evidence, partitioned by month on ``created_at`` (``aip_app`` has only SELECT and
  INSERT; UPDATE, DELETE and TRUNCATE are revoked from every runtime role):
  ``evidence_items``, ``restore_test_records``, ``provenance_entries``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Column, Date, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

__all__ = [
    "access_reviews",
    "breach_incidents",
    "control_records",
    "data_map_entries",
    "evidence_items",
    "provenance_entries",
    "restore_test_records",
]


def _created_at(*, primary_key: bool = False) -> Column[Any]:
    return Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        primary_key=primary_key,
        server_default=text("now()"),
    )


def _mutable_timestamps() -> list[Column[Any]]:
    return [
        _created_at(),
        Column(
            "updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
        ),
        Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    ]


control_records = Table(
    "control_records",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("control_key", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("framework_mappings", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("owner_user_id", UUID(as_uuid=True), nullable=True),
    Column("status", Text, nullable=False, server_default=text("'specified'")),
    Column("evidence_source", Text, nullable=True),
    *_mutable_timestamps(),
)

evidence_items = Table(
    "evidence_items",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("control_id", UUID(as_uuid=True), nullable=False),
    Column("evidence_type", Text, nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=True),
    Column("storage_key", Text, nullable=True),
    Column("content_hash", Text, nullable=True),
    Column("collected_at", TIMESTAMP(timezone=True), nullable=False),
    Column("period_start", Date, nullable=True),
    Column("period_end", Date, nullable=True),
    _created_at(primary_key=True),
)

access_reviews = Table(
    "access_reviews",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("quarter", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("snapshot", JSONB, nullable=False),
    Column("decisions", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("signed_off_by", UUID(as_uuid=True), nullable=True),
    Column("signed_off_at", TIMESTAMP(timezone=True), nullable=True),
    *_mutable_timestamps(),
)

restore_test_records = Table(
    "restore_test_records",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("environment", Text, nullable=False),
    Column("backup_taken_at", TIMESTAMP(timezone=True), nullable=False),
    Column("restore_started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("restore_completed_at", TIMESTAMP(timezone=True), nullable=True),
    Column("rpo_achieved_seconds", Integer, nullable=True),
    Column("rto_achieved_seconds", Integer, nullable=True),
    Column("result", Text, nullable=False),
    Column("evidence_item_id", UUID(as_uuid=True), nullable=True),
    Column("performed_by", UUID(as_uuid=True), nullable=True),
    _created_at(primary_key=True),
)

data_map_entries = Table(
    "data_map_entries",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("data_category", Text, nullable=False),
    Column("classification", Text, nullable=False),
    Column("system_location", Text, nullable=False),
    Column("region", Text, nullable=False),
    Column("purpose", Text, nullable=False),
    Column("retention_rule", Text, nullable=False),
    Column("sub_processor", Text, nullable=True),
    *_mutable_timestamps(),
)

breach_incidents = Table(
    "breach_incidents",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("detected_at", TIMESTAMP(timezone=True), nullable=False),
    Column("description", Text, nullable=False),
    Column("data_categories", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("individuals_affected", Integer, nullable=True),
    Column("serious_harm_likely", Boolean, nullable=True),
    Column("assessment_due_at", TIMESTAMP(timezone=True), nullable=False),
    Column("oaic_notified_at", TIMESTAMP(timezone=True), nullable=True),
    Column("individuals_notified_at", TIMESTAMP(timezone=True), nullable=True),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    *_mutable_timestamps(),
)

provenance_entries = Table(
    "provenance_entries",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("feature", Text, nullable=False),
    Column("reference_source", Text, nullable=False),
    Column("own_spec_path", Text, nullable=False),
    Column("author", Text, nullable=False),
    Column("legal_review_ref", Text, nullable=True),
    Column("recorded_at", TIMESTAMP(timezone=True), nullable=False),
    _created_at(primary_key=True),
)
