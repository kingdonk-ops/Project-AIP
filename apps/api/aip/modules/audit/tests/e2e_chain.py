"""End-to-end chain check against a running stack (AUDIT-01).

    python -m aip.modules.audit.tests.e2e_chain

Appends three entries for the kaefer-demo tenant through ``AuditApi.append`` (writing as
``aip_audit_writer`` via ``DATABASE_AUDIT_WRITER_URL``), then reads them back with a plain
``SELECT ... ORDER BY seq`` and recomputes the chain with ``chain_hash`` — the same code an offline
verifier uses. Exits non-zero unless all three hashes reproduce and the chain head equals hash #3.

Env:
- ``DATABASE_AUDIT_WRITER_URL`` (required): the ``aip_audit_writer`` URL.
- ``AIP_E2E_TENANT_ID`` (optional): the kaefer-demo tenant id; defaults to the test fixture id.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from aip.modules.audit.api import AuditApi, AuditEntryIn
from aip.modules.audit.chain_hash import GENESIS_PREV_HASH, ChainEntry, compute_hash
from aip.modules.audit.tables import audit_chain_heads, audit_log
from aip.platform.db.engine import dispose_audit_writer_engine
from aip.platform.db.session import audit_writer_tenant

DEFAULT_TENANT = UUID("00000000-0000-4000-8000-00000000000a")  # kaefer-demo fixture id


def _row_to_entry(row: dict[str, Any]) -> ChainEntry:
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


async def run(tenant_id: UUID) -> int:
    try:
        return await _run(tenant_id)
    finally:
        await dispose_audit_writer_engine()


async def _run(tenant_id: UUID) -> int:
    now = datetime.now(UTC)
    entries = [
        AuditEntryIn(
            event_type="widget.created",
            occurred_at=now,
            source_module="widgets",
            summary_key="audit.widget.created",
            payload={"after": {"n": n}},
        )
        for n in range(3)
    ]
    await AuditApi().append(tenant_id, entries)

    async with audit_writer_tenant(tenant_id) as conn:
        rows = [
            dict(r)
            for r in (await conn.execute(select(audit_log).order_by(audit_log.c.seq))).mappings()
        ]
        head = (
            await conn.execute(
                select(audit_chain_heads.c.last_seq, audit_chain_heads.c.last_hash).where(
                    audit_chain_heads.c.tenant_id == tenant_id,
                    audit_chain_heads.c.stream == "audit",
                )
            )
        ).one()

    prev = GENESIS_PREV_HASH
    for row in rows:
        if bytes(row["prev_hash"]) != prev or bytes(row["hash"]) != compute_hash(
            prev, _row_to_entry(row)
        ):
            print(f"FAIL: chain broken at seq {row['seq']}")
            return 1
        prev = bytes(row["hash"])

    if len(rows) < 3:
        print(f"FAIL: expected at least 3 entries, found {len(rows)}")
        return 1
    if bytes(head[1]) != bytes(rows[-1]["hash"]) or head[0] != rows[-1]["seq"]:
        print("FAIL: chain head does not match the last row")
        return 1

    print(f"OK: {len(rows)} entries verify and the head matches hash #{rows[-1]['seq']}")
    return 0


def main() -> int:
    if not os.environ.get("DATABASE_AUDIT_WRITER_URL"):
        print("DATABASE_AUDIT_WRITER_URL is not set", file=sys.stderr)
        return 2
    tenant = UUID(os.environ.get("AIP_E2E_TENANT_ID", str(DEFAULT_TENANT)))
    return asyncio.run(run(tenant))


if __name__ == "__main__":
    sys.exit(main())
