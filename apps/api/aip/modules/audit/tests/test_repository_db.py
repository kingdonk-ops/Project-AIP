"""Integration tests for the chain writer (AUDIT-01). Real Postgres, real roles."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID

from aip.modules.audit.chain_hash import GENESIS_PREV_HASH, ChainEntry, compute_hash
from aip.modules.audit.repository import append_audit_entries
from aip.modules.audit.schemas import AuditEntryIn
from aip.modules.audit.tables import audit_chain_heads, audit_log

from .conftest import Writer

OCCURRED = datetime(2026, 10, 7, 1, 2, 3, 4, tzinfo=UTC)


def _entry(n: int, **over: object) -> AuditEntryIn:
    data: dict[str, object] = {
        "event_type": "widget.created",
        "occurred_at": OCCURRED,
        "actor_id": ALICE_ID,
        "source_module": "widgets",
        "record_table": "widgets",
        "summary_key": "audit.widget.created",
        "payload": {"after": {"n": n}},
    }
    data.update(over)
    return AuditEntryIn.model_validate(data)


async def _rows(conn: AsyncConnection) -> list[dict[str, Any]]:
    stmt = select(audit_log).order_by(audit_log.c.seq)
    return [dict(r) for r in (await conn.execute(stmt)).mappings().all()]


def _chain_entry(row: dict[str, Any]) -> ChainEntry:
    return ChainEntry(
        tenant_id=row["tenant_id"],
        stream=row["stream"],
        seq=row["seq"],
        occurred_at=row["occurred_at"],
        event_type=row["event_type"],
        actor_id=row["actor_id"],
        on_behalf_of_id=row["on_behalf_of_id"],
        auth_strength=row["auth_strength"],
        source_module=row["source_module"],
        record_table=row["record_table"],
        record_id=row["record_id"],
        summary_key=row["summary_key"],
        payload=row["payload"],
        reason_for_change=row["reason_for_change"],
        flags=row["flags"],
        project_id=row["project_id"],
        asset_id=row["asset_id"],
        source_event_id=row["source_event_id"],
        supersedes_id=row["supersedes_id"],
    )


def _assert_valid_chain(rows: list[dict[str, Any]]) -> None:
    """Every row's hash recomputes, and each prev_hash links to the previous row's hash."""
    prev = GENESIS_PREV_HASH
    for row in rows:
        assert bytes(row["prev_hash"]) == prev, f"seq {row['seq']} prev_hash broken"
        recomputed = compute_hash(prev, _chain_entry(row))
        assert bytes(row["hash"]) == recomputed, f"seq {row['seq']} hash mismatch"
        prev = bytes(row["hash"])


async def test_single_append_assigns_seq_one_and_genesis_prev_hash(writer: Writer) -> None:
    async with writer.tenant(TENANT_A_ID) as conn:
        seqs = await append_audit_entries(conn, TENANT_A_ID, "audit", [_entry(1)])
    assert seqs == [1]
    async with writer.tenant(TENANT_A_ID) as conn:
        rows = await _rows(conn)
    assert [r["seq"] for r in rows] == [1]
    assert bytes(rows[0]["prev_hash"]) == GENESIS_PREV_HASH  # type: ignore[arg-type]
    _assert_valid_chain(rows)


async def test_concurrent_appends_are_gap_free_and_chain_valid(writer: Writer) -> None:
    async def one_batch(base: int) -> list[int]:
        async with writer.tenant(TENANT_A_ID) as conn:
            return await append_audit_entries(
                conn, TENANT_A_ID, "audit", [_entry(base * 10 + i) for i in range(5)]
            )

    results = await asyncio.gather(*(one_batch(b) for b in range(20)))

    all_seqs = sorted(s for batch in results for s in batch)
    assert all_seqs == list(range(1, 101)), "seq must be gap-free 1..100 with no duplicates"
    # Each batch of 5 got five consecutive seqs (the head lock kept batches from interleaving).
    for batch in results:
        assert batch == list(range(batch[0], batch[0] + 5))
    async with writer.tenant(TENANT_A_ID) as conn:
        rows = await _rows(conn)
    assert [r["seq"] for r in rows] == list(range(1, 101))
    _assert_valid_chain(rows)


async def test_chains_are_independent_per_tenant(writer: Writer) -> None:
    async with writer.tenant(TENANT_A_ID) as conn:
        assert await append_audit_entries(conn, TENANT_A_ID, "audit", [_entry(1), _entry(2)]) == [
            1,
            2,
        ]
    async with writer.tenant(TENANT_B_ID) as conn:
        assert await append_audit_entries(conn, TENANT_B_ID, "audit", [_entry(9)]) == [1]
    async with writer.tenant(TENANT_A_ID) as conn:
        a_rows = await _rows(conn)
        assert [r["seq"] for r in a_rows] == [1, 2]
        _assert_valid_chain(a_rows)
    async with writer.tenant(TENANT_B_ID) as conn:
        b_rows = await _rows(conn)
        assert [r["seq"] for r in b_rows] == [1]
        _assert_valid_chain(b_rows)


async def test_redelivered_source_event_id_is_a_noop_returning_the_first_seq(
    writer: Writer,
) -> None:
    sid = UUID("00000000-0000-4000-8000-00000000e001")
    async with writer.tenant(TENANT_A_ID) as conn:
        first = await append_audit_entries(
            conn, TENANT_A_ID, "audit", [_entry(1, source_event_id=sid)]
        )
    async with writer.tenant(TENANT_A_ID) as conn:
        again = await append_audit_entries(
            conn, TENANT_A_ID, "audit", [_entry(1, source_event_id=sid)]
        )
    assert first == again == [1]
    async with writer.tenant(TENANT_A_ID) as conn:
        count = (await conn.execute(select(func.count()).select_from(audit_log))).scalar_one()
        head = (
            await conn.execute(
                select(audit_chain_heads.c.last_seq).where(
                    audit_chain_heads.c.tenant_id == TENANT_A_ID,
                    audit_chain_heads.c.stream == "audit",
                )
            )
        ).scalar_one()
    assert count == 1
    assert head == 1


async def test_repeated_source_event_id_within_one_batch_dedupes(writer: Writer) -> None:
    sid = UUID("00000000-0000-4000-8000-00000000e777")
    async with writer.tenant(TENANT_A_ID) as conn:
        seqs = await append_audit_entries(
            conn,
            TENANT_A_ID,
            "audit",
            [_entry(1, source_event_id=sid), _entry(2), _entry(1, source_event_id=sid)],
        )
    assert seqs == [1, 2, 1]
    async with writer.tenant(TENANT_A_ID) as conn:
        rows = await _rows(conn)
    assert [r["seq"] for r in rows] == [1, 2]


async def test_tenant_isolation_for_app_reads(writer: Writer, tenant_db: object) -> None:
    from tests.fixtures.postgres import TenantDb

    assert isinstance(tenant_db, TenantDb)
    async with writer.tenant(TENANT_A_ID) as conn:
        await append_audit_entries(conn, TENANT_A_ID, "audit", [_entry(1), _entry(2)])
    async with writer.tenant(TENANT_B_ID) as conn:
        await append_audit_entries(conn, TENANT_B_ID, "audit", [_entry(9)])

    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        a_count = (await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar_one()
    assert a_count == 2
    async with tenant_db.no_tenant() as conn:
        none_count = (await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar_one()
    assert none_count == 0
