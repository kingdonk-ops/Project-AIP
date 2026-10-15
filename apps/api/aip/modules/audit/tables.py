"""SQLAlchemy Core declarations for the audit store (AUDIT-01, ADR 0002).

Created only by the Alembic revision ``202610151900_audit_log_chain``; ``aip-db check-schema``
compares these declarations with the migrated database.

``audit_log`` is append-only (ADR 0002 / DATABASE-05): corrections are new rows carrying
``supersedes_id``, never edits, so there is no ``updated_at`` and no ``deleted_at`` — the
soft-delete convention does not apply to this table, by design. It is **not** range-partitioned:
the tamper-evident chain needs a table-wide ``UNIQUE (tenant_id, stream, seq)`` and a partial
``UNIQUE (tenant_id, source_event_id)``, and a native partition's unique indexes would have to
include the partition key, which these do not. The monthly "segments" of ADR 0021 are therefore
logical: they are recorded in ``audit_chain_checkpoints`` and a retention job (AUDIT-05) removes an
old segment's rows, rather than dropping a partition. See ADR 0031.

``audit_chain_heads`` and ``audit_chain_checkpoints`` are writer-maintained bookkeeping, keyed on
natural columns rather than a surrogate uuid (an intentional, task-specified deviation from the
uuid-PK convention); both still carry ``tenant_id`` and FORCE RLS.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    LargeBinary,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.types import UserDefinedType

from aip.platform.db.metadata import metadata


class Ltree(UserDefinedType[str]):
    """Postgres ``ltree`` (asset subtree paths), declared for ``aip-db check-schema``."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "ltree"


audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("stream", Text, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("project_id", Uuid, nullable=True),
    Column("asset_id", Uuid, nullable=True),
    Column("asset_path", Ltree(), nullable=True),
    Column("actor_id", Uuid, nullable=True),
    Column("on_behalf_of_id", Uuid, nullable=True),
    Column("auth_strength", Text, nullable=True),
    Column("source_module", Text, nullable=True),
    Column("record_table", Text, nullable=True),
    Column("record_id", Uuid, nullable=True),
    Column("event_type", Text, nullable=False),
    Column("summary_key", Text, nullable=True),
    Column("payload", JSONB, nullable=True),
    Column("reason_for_change", Text, nullable=True),
    Column("flags", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("source_ip", INET, nullable=True),
    Column("device", Text, nullable=True),
    Column("source_event_id", Uuid, nullable=True),
    Column("supersedes_id", Uuid, nullable=True),
    Column("prev_hash", LargeBinary, nullable=False),
    Column("hash", LargeBinary, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)

audit_chain_heads = Table(
    "audit_chain_heads",
    metadata,
    Column("tenant_id", Uuid, primary_key=True),
    Column("stream", Text, primary_key=True),
    Column("last_seq", BigInteger, nullable=False, server_default=text("0")),
    Column("last_hash", LargeBinary, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)

audit_chain_checkpoints = Table(
    "audit_chain_checkpoints",
    metadata,
    Column("tenant_id", Uuid, primary_key=True),
    Column("stream", Text, primary_key=True),
    Column("segment", Text, primary_key=True),
    Column("last_seq", BigInteger, nullable=False),
    Column("last_hash", LargeBinary, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)
