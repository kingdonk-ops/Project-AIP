"""SQLAlchemy Core declaration of ``partition_settings`` (DATABASE-05, ADR 0002).

Created only by the Alembic revision ``202610141100_partition_functions``; ``aip-db check-schema``
compares this declaration with the migrated database. Global reference data (no ``tenant_id``, no
RLS; allow-listed in the schema guard): one row per partitioned append-only table, read by the
``ensure_partitions`` job as ``aip_jobs``.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Table, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP

from aip.platform.db.metadata import metadata

__all__ = ["partition_settings"]

partition_settings = Table(
    "partition_settings",
    metadata,
    Column("table_name", Text, primary_key=True),
    Column("partition_interval", Text, nullable=False),
    Column("months_ahead", Integer, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
)
