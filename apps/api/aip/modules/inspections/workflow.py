"""The ``inspection`` record type's hooks into approvals (INSPECTIONS-01 step 6, ADR 0035).

- The record resolver returns ``RecordRef(project_id)`` for a live inspection visible on the
  caller's connection, else ``None``, so ``POST /api/v1/approvals/instances`` binds an inspection
  only to its own project (ADR 0035 §6).
- The guard facts provider returns read-only JSON facts ``{kind, assetId, projectId, source}`` plus
  the answer facts (INSPECTIONS-02) ``{answeredCount, missingRequiredCount, invalidCount,
  failedCount}``, computed on the current answers with the FORMS-02 evaluator. INSPECTIONS-10
  guards the submit transitions with them; INSPECTIONS-03 adds step facts.

``install`` registers both, replacing any stand-in (approvals' dev ``demo`` fallback, or a test's);
``__init__`` calls it at import, before ``create_app`` runs.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.api import (
    RecordRef,
    register_guard_context_provider,
    register_record_resolver,
    unregister_guard_context_provider,
    unregister_record_resolver,
)
from aip.modules.inspections import repository as repo
from aip.modules.inspections.policies import RECORD_TYPE
from aip.modules.inspections.responses import answer_facts

__all__ = ["facts", "facts_of", "install", "resolve"]


async def resolve(conn: AsyncConnection, record_id: UUID) -> RecordRef | None:
    row = await repo.get_inspection(conn, record_id)
    return None if row is None else RecordRef(project_id=row["project_id"])


def facts_of(row: dict[str, Any]) -> dict[str, Any]:
    """The guard facts of an inspection row: plain JSON, uuids as strings."""
    project_id = row["project_id"]
    return {
        "kind": row["kind"],
        "assetId": str(row["asset_id"]),
        "projectId": None if project_id is None else str(project_id),
        "source": row["source"],
    }


async def facts(conn: AsyncConnection, record_id: UUID) -> dict[str, Any]:
    row = await repo.get_inspection(conn, record_id)
    if row is None:
        return {}
    return {**facts_of(row), **await answer_facts(conn, row)}


def install() -> None:
    """Register the resolver and facts provider for ``inspection`` (idempotent)."""
    unregister_record_resolver(RECORD_TYPE)
    unregister_guard_context_provider(RECORD_TYPE)
    register_record_resolver(RECORD_TYPE, resolve)
    register_guard_context_provider(RECORD_TYPE, facts)
