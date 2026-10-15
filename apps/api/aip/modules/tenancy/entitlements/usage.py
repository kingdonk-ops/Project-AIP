"""Usage figures for entitlements (ENT-01 step 5, ADR 0008 adjustment A).

- ``UsageSource``: a module that can count something for a tenant registers one (identity: active
  users per class; uploads: stored bytes). Sources run on the caller's ``with_tenant`` connection,
  so they see only that tenant's rows. None are registered yet; until then the figures are 0.
- ``estimate_db_bytes``: the tenant's share of the shared database, as the sum of
  ``pg_column_size`` over its rows in every table that has a ``tenant_id`` column and that the
  connection's role may read (partitions are counted through their parent, never twice). Method
  ``row-bytes-v1``: row data only, without indexes, TOAST overhead or free space, so it
  understates the on-disk size; the plan-and-usage page says so.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "DB_ESTIMATE_METHOD",
    "UsageFigures",
    "UsageSource",
    "clear_usage_sources",
    "collect_usage",
    "estimate_db_bytes",
    "register_usage_source",
    "tenant_tables",
    "usage_sources",
]

DB_ESTIMATE_METHOD = "row-bytes-v1"


@dataclass(frozen=True, slots=True)
class UsageFigures:
    """What one source counted. Figures a source does not know stay ``None`` / empty."""

    active_users: Mapping[str, int] = field(default_factory=dict[str, int])
    storage_bytes: int | None = None
    jobs_count: int | None = None
    ai_spend_cents: int | None = None


class UsageSource(Protocol):
    async def collect(self, conn: AsyncConnection, tenant_id: UUID) -> UsageFigures: ...


_sources: list[UsageSource] = []


def register_usage_source(source: UsageSource) -> None:
    if source not in _sources:
        _sources.append(source)


def usage_sources() -> tuple[UsageSource, ...]:
    return tuple(_sources)


def clear_usage_sources() -> None:
    """Forget every registered source (tests)."""
    _sources.clear()


async def collect_usage(
    conn: AsyncConnection, tenant_id: UUID, sources: tuple[UsageSource, ...] | None = None
) -> UsageFigures:
    """Every source's figures for ``tenant_id``, added together."""
    users: dict[str, int] = {}
    storage = jobs = ai = 0
    for source in usage_sources() if sources is None else sources:
        figures = await source.collect(conn, tenant_id)
        for user_class, count in figures.active_users.items():
            users[user_class] = users.get(user_class, 0) + count
        storage += figures.storage_bytes or 0
        jobs += figures.jobs_count or 0
        ai += figures.ai_spend_cents or 0
    return UsageFigures(users, storage, jobs, ai)


_TENANT_TABLES = text(
    """
    SELECT c.relname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p')
       AND NOT c.relispartition
       AND has_table_privilege(c.oid, 'SELECT')
     ORDER BY c.relname
    """
)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def tenant_tables(conn: AsyncConnection) -> list[str]:
    """Every table with a ``tenant_id`` column the connection may read (partitions via parents)."""
    return list((await conn.execute(_TENANT_TABLES)).scalars().all())


async def estimate_db_bytes(conn: AsyncConnection, tenant_id: UUID) -> int:
    """The estimated bytes of ``tenant_id``'s rows (method ``DB_ESTIMATE_METHOD``)."""
    total = 0
    for table in await tenant_tables(conn):
        size = await conn.execute(
            text(
                f"SELECT coalesce(sum(pg_column_size(t.*)), 0) FROM {_quote(table)} t "
                "WHERE t.tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        )
        total += int(size.scalar_one())
    return total
