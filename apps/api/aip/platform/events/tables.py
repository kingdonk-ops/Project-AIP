"""SQLAlchemy Core declaration of the ``domain_events`` outbox (ARCH-05) and the
``platform_event_status`` catalogue table (ARCH-06); ADR 0002/0003.

Created only by their Alembic revisions (``202610131000_domain_events`` and
``202610150900_event_catalogue``); ``aip-db check-schema`` compares these declarations with the
migrated database. ``domain_events`` is append-only (no ``updated_at``/``deleted_at``): ``aip_app``
inserts and reads, ``aip_jobs`` updates only the publish and backoff columns, and the
ARCH-07 dead-letter functions alone set the discard columns. ``platform_event_status`` is a
global catalogue table (no ``tenant_id``, no RLS; on the schema-guard allow-list).
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

__all__ = ["domain_events", "platform_event_status"]

domain_events = Table(
    "domain_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("asset_id", UUID(as_uuid=True), nullable=True),
    Column("event_name", Text, nullable=False),
    Column("event_version", Integer, nullable=False),
    Column("aggregate_type", Text, nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("actor_id", UUID(as_uuid=True), nullable=True),
    Column("occurred_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("published_at", TIMESTAMP(timezone=True), nullable=True),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("dead_lettered_at", TIMESTAMP(timezone=True), nullable=True),
    Column("last_error", Text, nullable=True),
    # ARCH-07: dispatch backoff and the operator's discard decision.
    Column("next_attempt_at", TIMESTAMP(timezone=True), nullable=True),
    Column("discarded_at", TIMESTAMP(timezone=True), nullable=True),
    Column("discarded_by", UUID(as_uuid=True), nullable=True),
    Column("discard_reason", Text, nullable=True),
)

# ARCH-06: the catalogue's deprecation flag per event version. Global (no tenant_id, no RLS).
platform_event_status = Table(
    "platform_event_status",
    metadata,
    Column("event_name", Text, primary_key=True),
    Column("event_version", Integer, primary_key=True),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("deprecated_at", TIMESTAMP(timezone=True), nullable=True),
    Column("deprecated_by", UUID(as_uuid=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
)
