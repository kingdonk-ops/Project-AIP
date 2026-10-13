"""SQLAlchemy Core declaration of the ``domain_events`` outbox (ARCH-05, ADR 0002/0003).

Created only by the Alembic revision ``202610131000_domain_events``; ``aip-db check-schema``
compares this declaration with the migrated database. The table is append-only (no
``updated_at``/``deleted_at``): ``aip_app`` inserts and reads, ``aip_jobs`` updates only the
publish columns.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

__all__ = ["domain_events"]

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
)
