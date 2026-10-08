"""Idempotent create for offline-created rows (DATABASE-04).

The table needs ``client_generated_id uuid`` and a unique index on
``(tenant_id, client_generated_id)`` (``render_template("tenant_table", ..., sync=True)``). A
replayed create returns the row the first call made, never a duplicate. The same client id in
another tenant is a different row: the index is per tenant and RLS hides the other tenant's rows.
"""

from __future__ import annotations

from typing import Any, NamedTuple
from uuid import uuid4

from sqlalchemy import Table, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.db._sql import as_dict

__all__ = ["IdempotentResult", "create_idempotent"]


class IdempotentResult(NamedTuple):
    row: dict[str, Any]
    created: bool  # False when an earlier call with the same client_generated_id made the row


async def create_idempotent(
    conn: AsyncConnection, table: Table, values: dict[str, Any]
) -> IdempotentResult:
    """Insert ``values`` unless ``(tenant_id, client_generated_id)`` exists; return that row.

    ``values`` must carry ``tenant_id`` (RLS rejects any other tenant) and
    ``client_generated_id``; ``id`` defaults to a new uuid4. If the existing row was soft-deleted
    it is still returned: the create already happened.
    """
    for required in ("tenant_id", "client_generated_id"):
        if values.get(required) is None:
            raise ValueError(f"create_idempotent needs {required}")
    stmt = (
        insert(table)
        .values({"id": uuid4(), **values})
        .on_conflict_do_nothing(index_elements=["tenant_id", "client_generated_id"])
        .returning(*table.c)
    )
    inserted = (await conn.execute(stmt)).first()
    if inserted is not None:
        return IdempotentResult(as_dict(inserted), True)
    existing = (
        await conn.execute(
            select(table).where(
                table.c.tenant_id == values["tenant_id"],
                table.c.client_generated_id == values["client_generated_id"],
            )
        )
    ).one()
    return IdempotentResult(as_dict(existing), False)
