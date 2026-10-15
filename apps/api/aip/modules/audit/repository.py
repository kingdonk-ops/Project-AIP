"""The chain writer for the audit store (AUDIT-01).

``append_audit_entries`` is the only way rows reach ``audit_log``. It runs in one transaction on a
connection from ``audit_writer_tenant`` (role ``aip_audit_writer``, tenant bound), locks the
tenant/stream head ``FOR UPDATE`` so appends serialise, assigns a gap-free ``seq``, computes each
hash with ``chain_hash.compute_hash`` (never in SQL), inserts the rows, and advances the head and
the monthly checkpoints (ADR 0021). Re-inserting an already-seen ``source_event_id`` is a no-op
that returns the existing ``seq``, so redelivery from the outbox (AUDIT-02) is safe.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.audit.chain_hash import GENESIS_PREV_HASH, ChainEntry, compute_hash
from aip.modules.audit.schemas import AuditEntryIn
from aip.modules.audit.tables import audit_chain_checkpoints, audit_chain_heads, audit_log
from aip.platform.context import new_request_id

__all__ = ["append_audit_entries"]


def _uuid7() -> UUID:
    """A UUIDv7 id generated in the app (ADR 0002 / ARCH-04)."""
    return UUID(new_request_id())


def _segment(entry: AuditEntryIn) -> str:
    """The monthly segment label (UTC ``YYYY-MM``) an entry belongs to (ADR 0021)."""
    return entry.occurred_at.astimezone(UTC).strftime("%Y-%m")


async def _lock_head(conn: AsyncConnection, tenant_id: UUID, stream: str) -> tuple[int, bytes]:
    """Return the locked ``(last_seq, last_hash)`` for the chain, creating a genesis head if new."""
    select_head = (
        select(audit_chain_heads.c.last_seq, audit_chain_heads.c.last_hash)
        .where(
            audit_chain_heads.c.tenant_id == tenant_id,
            audit_chain_heads.c.stream == stream,
        )
        .with_for_update()
    )
    row = (await conn.execute(select_head)).first()
    if row is None:
        await conn.execute(
            pg_insert(audit_chain_heads)
            .values(tenant_id=tenant_id, stream=stream, last_seq=0, last_hash=GENESIS_PREV_HASH)
            .on_conflict_do_nothing(index_elements=["tenant_id", "stream"])
        )
        # Re-select FOR UPDATE: if a concurrent appender inserted first, block on its row instead.
        row = (await conn.execute(select_head)).one()
    return int(row[0]), bytes(row[1])


async def _existing_seqs(
    conn: AsyncConnection, tenant_id: UUID, source_event_ids: set[UUID]
) -> dict[UUID, int]:
    """Map each already-stored ``source_event_id`` (per tenant) to its ``seq``."""
    if not source_event_ids:
        return {}
    stmt = select(audit_log.c.source_event_id, audit_log.c.seq).where(
        audit_log.c.tenant_id == tenant_id,
        audit_log.c.source_event_id.in_(source_event_ids),
    )
    return {row[0]: int(row[1]) for row in (await conn.execute(stmt)).all()}


def _row(
    tenant_id: UUID, stream: str, seq: int, entry: AuditEntryIn, prev_hash: bytes, row_hash: bytes
) -> dict[str, Any]:
    return {
        "id": _uuid7(),
        "tenant_id": tenant_id,
        "stream": stream,
        "seq": seq,
        "project_id": entry.project_id,
        "asset_id": entry.asset_id,
        "asset_path": entry.asset_path,
        "actor_id": entry.actor_id,
        "on_behalf_of_id": entry.on_behalf_of_id,
        "auth_strength": entry.auth_strength,
        "source_module": entry.source_module,
        "record_table": entry.record_table,
        "record_id": entry.record_id,
        "event_type": entry.event_type,
        "summary_key": entry.summary_key,
        "payload": entry.payload,
        "reason_for_change": entry.reason_for_change,
        "flags": list(entry.flags),
        "source_ip": entry.source_ip,
        "device": entry.device,
        "source_event_id": entry.source_event_id,
        "supersedes_id": entry.supersedes_id,
        "prev_hash": prev_hash,
        "hash": row_hash,
        "occurred_at": entry.occurred_at,
    }


def _chain_entry(tenant_id: UUID, stream: str, seq: int, entry: AuditEntryIn) -> ChainEntry:
    return ChainEntry(
        tenant_id=tenant_id,
        stream=stream,
        seq=seq,
        occurred_at=entry.occurred_at,
        event_type=entry.event_type,
        actor_id=entry.actor_id,
        on_behalf_of_id=entry.on_behalf_of_id,
        auth_strength=entry.auth_strength,
        source_module=entry.source_module,
        record_table=entry.record_table,
        record_id=entry.record_id,
        summary_key=entry.summary_key,
        payload=entry.payload,
        reason_for_change=entry.reason_for_change,
        flags=entry.flags,
        project_id=entry.project_id,
        asset_id=entry.asset_id,
        source_event_id=entry.source_event_id,
        supersedes_id=entry.supersedes_id,
    )


async def _update_checkpoints(
    conn: AsyncConnection,
    tenant_id: UUID,
    stream: str,
    segments: dict[str, tuple[int, bytes]],
) -> None:
    """Advance the closing ``(last_seq, last_hash)`` of each touched monthly segment (ADR 0021)."""
    rows = [
        {
            "tenant_id": tenant_id,
            "stream": stream,
            "segment": segment,
            "last_seq": last_seq,
            "last_hash": last_hash,
        }
        for segment, (last_seq, last_hash) in segments.items()
    ]
    stmt = pg_insert(audit_chain_checkpoints).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "stream", "segment"],
        set_={
            "last_seq": stmt.excluded.last_seq,
            "last_hash": stmt.excluded.last_hash,
            "updated_at": func.now(),
        },
        where=stmt.excluded.last_seq > audit_chain_checkpoints.c.last_seq,
    )
    await conn.execute(stmt)


async def append_audit_entries(
    conn: AsyncConnection,
    tenant_id: UUID,
    stream: str,
    entries: Sequence[AuditEntryIn],
) -> list[int]:
    """Append ``entries`` to the ``(tenant_id, stream)`` chain; return each entry's ``seq``.

    Runs on an ``aip_audit_writer`` connection already bound to ``tenant_id`` (its transaction and
    ``app.tenant_id`` set by ``audit_writer_tenant``). Entries are appended in order; an entry whose
    ``source_event_id`` already exists is skipped and reports the stored ``seq`` (idempotent
    redelivery). The returned list is aligned with ``entries``.
    """
    if not entries:
        return []

    last_seq, last_hash = await _lock_head(conn, tenant_id, stream)
    existing = await _existing_seqs(
        conn, tenant_id, {e.source_event_id for e in entries if e.source_event_id is not None}
    )

    result: list[int] = []
    rows: list[dict[str, Any]] = []
    segments: dict[str, tuple[int, bytes]] = {}
    running_seq, running_hash = last_seq, last_hash
    for entry in entries:
        sid = entry.source_event_id
        if sid is not None and sid in existing:
            result.append(existing[sid])
            continue
        running_seq += 1
        row_hash = compute_hash(running_hash, _chain_entry(tenant_id, stream, running_seq, entry))
        rows.append(_row(tenant_id, stream, running_seq, entry, running_hash, row_hash))
        segments[_segment(entry)] = (running_seq, row_hash)
        if sid is not None:
            existing[sid] = running_seq  # dedupe a repeat within this same batch
        running_hash = row_hash
        result.append(running_seq)

    if not rows:
        return result

    await conn.execute(insert(audit_log), rows)
    await conn.execute(
        audit_chain_heads.update()
        .where(
            audit_chain_heads.c.tenant_id == tenant_id,
            audit_chain_heads.c.stream == stream,
        )
        .values(last_seq=running_seq, last_hash=running_hash)
    )
    await _update_checkpoints(conn, tenant_id, stream, segments)
    return result
