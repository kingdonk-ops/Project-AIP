"""SQLAlchemy Core declarations for the ops job records (OPS-01, ADR 0002).

Created only by the Alembic revision ``202610080510_ops_jobs``; ``aip-db check-schema`` compares
these declarations with the migrated database. ``jobs`` is tenant-scoped with soft delete;
``job_events`` is append-only (no ``updated_at``/``deleted_at``; UPDATE and DELETE are revoked).
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

jobs = Table(
    "jobs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("job_type", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'queued'")),
    Column("idempotency_key", Text, nullable=True),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("result_ref", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("requested_by", UUID(as_uuid=True), nullable=True),
    Column("procrastinate_job_id", BigInteger, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

job_events = Table(
    "job_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("job_id", UUID(as_uuid=True), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("from_status", Text, nullable=True),
    Column("to_status", Text, nullable=False),
    Column("detail", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("occurred_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
)
