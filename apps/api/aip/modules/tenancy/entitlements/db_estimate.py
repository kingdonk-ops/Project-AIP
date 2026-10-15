"""When and how the tenant database-size estimate runs (ENT-01, ADR 0008 adjustment A as amended).

**When.** The estimate feeds the month's true-up invoice (ENT-02) and the 80%/95% warnings, and a
tenant moves through a 20 GB block over months, so it runs **weekly (Sunday) and on the last day of
the month** (UTC dates), not nightly. ``db_estimate_due`` decides. The nightly command still sweeps
expired overrides and snapshots the cheap usage figures every run; on other days it keeps the last
estimate.

**How** (``ENTITLEMENTS_DB_ESTIMATE_METHOD``):

- ``per_tenant`` (default): for each tenant, a ``with_tenant`` transaction as ``aip_app`` sums
  ``pg_column_size`` over that tenant's rows in every tenant table it may read (RLS stays on).
  Work grows with tenants x tables.
- ``single_pass`` (option 3): one ``GROUP BY tenant_id`` scan per table for all tenants at once,
  in a read-only transaction that returns only ``(tenant_id, bytes)``. It must read across tenants,
  so it needs a role that bypasses RLS, which the platform's rules do not allow today: it stays off
  until the owner approves such a role (an ADR), and it refuses to run without its own
  ``ENTITLEMENTS_DB_ESTIMATE_URL``.

**Where** (``ENTITLEMENTS_DB_ESTIMATE_URL``, option 4): when set, the estimate reads from that
database (for example an RDS read replica) instead of the primary. With ``per_tenant`` the URL logs
in as ``aip_app`` on the replica, so RLS still applies and no new role is needed. Results are always
written to the primary through the normal ``with_tenant`` path.

Both methods measure the same thing (``row-bytes-v1``: row data only, no indexes or free space).
"""

from __future__ import annotations

import calendar
import os
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import date
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from aip.modules.tenancy.entitlements.usage import estimate_db_bytes, tenant_tables

__all__ = [
    "METHOD_ENV",
    "URL_ENV",
    "DbEstimateConfigError",
    "DbEstimateMethod",
    "DbEstimator",
    "PerTenantEstimator",
    "SinglePassEstimator",
    "configured_method",
    "configured_url",
    "db_estimate_due",
    "estimate_all_tenants",
]

METHOD_ENV = "ENTITLEMENTS_DB_ESTIMATE_METHOD"
URL_ENV = "ENTITLEMENTS_DB_ESTIMATE_URL"
ESTIMATE_WEEKDAY = calendar.SUNDAY

DbEstimateMethod = Literal["per_tenant", "single_pass"]
TenantConnect = Callable[[UUID], AbstractAsyncContextManager[AsyncConnection]]


class DbEstimateConfigError(RuntimeError):
    """The estimate settings are inconsistent (for example ``single_pass`` without its own URL)."""


def db_estimate_due(day: date) -> bool:
    """Whether ``day`` (a UTC date) is an estimate day: a Sunday or the last day of its month."""
    last = calendar.monthrange(day.year, day.month)[1]
    return day.weekday() == ESTIMATE_WEEKDAY or day.day == last


def configured_method(raw: str | None = None) -> DbEstimateMethod:
    value = (os.environ.get(METHOD_ENV, "") if raw is None else raw).strip() or "per_tenant"
    if value not in ("per_tenant", "single_pass"):
        raise DbEstimateConfigError(
            f"{METHOD_ENV} must be per_tenant or single_pass, not {value!r}"
        )
    return value  # pyright: ignore[reportReturnType]


def configured_url(raw: str | None = None) -> str | None:
    value = (os.environ.get(URL_ENV, "") if raw is None else raw).strip()
    return value or None


class DbEstimator(Protocol):
    async def estimate(self, tenants: Sequence[UUID]) -> dict[UUID, int]: ...


class PerTenantEstimator:
    """One RLS-bound transaction per tenant on ``connect`` (the primary, or a replica's aip_app)."""

    def __init__(self, connect: TenantConnect) -> None:
        self._connect = connect

    async def estimate(self, tenants: Sequence[UUID]) -> dict[UUID, int]:
        sizes: dict[UUID, int] = {}
        for tenant_id in tenants:
            async with self._connect(tenant_id) as conn:
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                sizes[tenant_id] = await estimate_db_bytes(conn, tenant_id)
        return sizes


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def estimate_all_tenants(conn: AsyncConnection) -> dict[UUID, int]:
    """Bytes per tenant over every readable tenant table, one scan per table (row-bytes-v1)."""
    sizes: dict[UUID, int] = {}
    for table in await tenant_tables(conn):
        rows = await conn.execute(
            text(
                f"SELECT t.tenant_id, coalesce(sum(pg_column_size(t.*)), 0) FROM {_quote(table)} t "
                "GROUP BY t.tenant_id"
            )
        )
        for tenant_id, size in rows.all():
            sizes[tenant_id] = sizes.get(tenant_id, 0) + int(size)
    return sizes


class SinglePassEstimator:
    """Option 3: all tenants at once, cross-tenant and read-only (needs owner approval)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @classmethod
    def from_url(cls, url: str) -> SinglePassEstimator:
        async_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return cls(create_async_engine(async_url, pool_size=1, max_overflow=0))

    async def estimate(self, tenants: Sequence[UUID]) -> dict[UUID, int]:
        async with self.engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            sizes = await estimate_all_tenants(conn)
            await conn.rollback()
        wanted = set(tenants)
        return {tenant_id: sizes.get(tenant_id, 0) for tenant_id in wanted}
