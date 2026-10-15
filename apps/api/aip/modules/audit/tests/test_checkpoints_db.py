"""ADR 0021 monthly segment checkpoints (AUDIT-01).

Proves the chain is sealed in monthly segments so an old segment's rows can be removed (by the
AUDIT-05 retention job) and the remainder still verifies from the removed segment's checkpoint,
while tampering with a retained row is still caught.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from sqlalchemy import select
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import FreshDb

from aip.modules.audit.chain_hash import compute_hash
from aip.modules.audit.repository import append_audit_entries
from aip.modules.audit.schemas import AuditEntryIn
from aip.modules.audit.tables import audit_chain_checkpoints

from .conftest import Writer, db_connection
from .test_repository_db import _chain_entry, _rows

SEPT = datetime(2026, 9, 15, 8, 0, 0, tzinfo=UTC)
OCT = datetime(2026, 10, 15, 8, 0, 0, tzinfo=UTC)


def _entry(n: int, when: datetime) -> AuditEntryIn:
    return AuditEntryIn(
        event_type="widget.created",
        occurred_at=when,
        source_module="widgets",
        payload={"after": {"n": n}},
    )


async def test_segment_checkpoints_seal_each_month(writer: Writer) -> None:
    async with writer.tenant(TENANT_A_ID) as conn:
        await append_audit_entries(
            conn, TENANT_A_ID, "audit", [_entry(1, SEPT), _entry(2, SEPT), _entry(3, SEPT)]
        )
        await append_audit_entries(
            conn, TENANT_A_ID, "audit", [_entry(4, OCT), _entry(5, OCT), _entry(6, OCT)]
        )
    async with writer.tenant(TENANT_A_ID) as conn:
        rows = await _rows(conn)
        checkpoints = {
            r["segment"]: (r["last_seq"], bytes(r["last_hash"]))
            for r in (
                await conn.execute(
                    select(audit_chain_checkpoints).order_by(audit_chain_checkpoints.c.segment)
                )
            ).mappings()
        }
    by_seq = {r["seq"]: r for r in rows}
    assert set(checkpoints) == {"2026-09", "2026-10"}
    assert checkpoints["2026-09"] == (3, bytes(by_seq[3]["hash"]))
    assert checkpoints["2026-10"] == (6, bytes(by_seq[6]["hash"]))


async def test_old_segment_can_be_removed_and_rest_verifies_from_checkpoint(
    writer: Writer, migrated_db: FreshDb
) -> None:
    async with writer.tenant(TENANT_A_ID) as conn:
        await append_audit_entries(
            conn, TENANT_A_ID, "audit", [_entry(1, SEPT), _entry(2, SEPT), _entry(3, SEPT)]
        )
        await append_audit_entries(
            conn, TENANT_A_ID, "audit", [_entry(4, OCT), _entry(5, OCT), _entry(6, OCT)]
        )

    # The AUDIT-05 retention job deletes an old segment; here a superuser stands in, lifting the
    # append-only trigger only to remove September, and keeping its checkpoint.
    async with db_connection(migrated_db.superuser_url) as su:
        await su.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        await su.execute(
            "DELETE FROM audit_log WHERE tenant_id = $1 AND occurred_at < $2",
            TENANT_A_ID,
            OCT.replace(day=1),
        )
        await su.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")

    async with writer.tenant(TENANT_A_ID) as conn:
        retained = await _rows(conn)
        sept_cp = (
            await conn.execute(
                select(
                    audit_chain_checkpoints.c.last_seq, audit_chain_checkpoints.c.last_hash
                ).where(audit_chain_checkpoints.c.segment == "2026-09")
            )
        ).one()

    assert [r["seq"] for r in retained] == [4, 5, 6]
    # Verification starts from the removed segment's checkpoint.
    prev = bytes(sept_cp[1])
    assert sept_cp[0] == 3
    for row in retained:
        assert bytes(row["prev_hash"]) == prev
        assert bytes(row["hash"]) == compute_hash(prev, _chain_entry(row))
        prev = bytes(row["hash"])

    # Tampering with a retained row is still caught: its stored hash no longer matches.
    tampered = dataclasses.replace(_chain_entry(retained[1]), payload={"after": {"n": 999}})
    assert compute_hash(bytes(retained[0]["hash"]), tampered) != bytes(retained[1]["hash"])
