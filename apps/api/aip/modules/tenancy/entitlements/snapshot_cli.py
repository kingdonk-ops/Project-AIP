"""The scheduled entitlement run for named tenants (ENT-01, ADR 0008 A, ADR 0023 point 5).

    uv run python -m aip.modules.tenancy.entitlements.snapshot_cli --period 2026-10 \\
        --tenant 00000000-0000-4000-8000-00000000000a [--tenant ...] [--db-estimate due|always|skip]

Schedule it daily (OPS-13). Each run, for each tenant, through ``DATABASE_URL`` as ``aip_app`` (RLS
on, one tenant per transaction):

1. remove expired overrides, each with a ``tenant.entitlements_changed`` audit event;
2. upsert the month's ``tenant_usage`` row from the registered usage sources;
3. on estimate days only (Sunday and the last day of the month, UTC; ``--db-estimate due``, the
   default), estimate each tenant's database size; on other days the row keeps its last estimate.
   ``always`` forces an estimate, ``skip`` never takes one.

The estimate method and source come from ``ENTITLEMENTS_DB_ESTIMATE_METHOD`` (``per_tenant``, the
default, or ``single_pass``) and ``ENTITLEMENTS_DB_ESTIMATE_URL`` (for example a read replica); see
``db_estimate``. ``--db-method`` and ``--db-url`` override them for one run.

Tenants are named explicitly: the runtime role cannot list tenants (RLS on ``tenants``).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.tenancy.entitlements.db_estimate import (
    DbEstimateConfigError,
    DbEstimateMethod,
    DbEstimator,
    PerTenantEstimator,
    SinglePassEstimator,
    configured_method,
    configured_url,
    db_estimate_due,
)
from aip.modules.tenancy.entitlements.service import EntitlementService
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import app_engine_for, with_tenant

__all__ = ["RunResult", "check_settings", "main", "open_estimator", "parse_period", "run"]

DbEstimateMode = Literal["due", "always", "skip"]


def parse_period(raw: str) -> date:
    """``YYYY-MM`` as the first day of that month."""
    try:
        year, month = raw.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        raise argparse.ArgumentTypeError(f"period must be YYYY-MM, not {raw!r}") from None


@dataclass(frozen=True, slots=True)
class RunResult:
    expired: dict[UUID, int]
    estimated: bool


async def run(
    service: EntitlementService,
    tenants: Sequence[UUID],
    period: date,
    *,
    estimator: DbEstimator | None,
    db_estimate: DbEstimateMode = "due",
) -> RunResult:
    """Sweep and snapshot each tenant; estimate database size when due (module docstring)."""
    today = service.clock().date()
    estimate = estimator is not None and (
        db_estimate == "always" or (db_estimate == "due" and db_estimate_due(today))
    )
    sizes = await estimator.estimate(tenants) if estimate and estimator is not None else {}
    expired: dict[UUID, int] = {}
    for tenant_id in tenants:
        expired[tenant_id] = await service.sweep_expired_overrides(tenant_id)
        await service.snapshot_usage(
            tenant_id, period, db_bytes=sizes.get(tenant_id), measure_db=False
        )
    return RunResult(expired, estimate)


def check_settings(method: DbEstimateMethod, url: str | None) -> None:
    """Raise ``DbEstimateConfigError`` when ``method`` cannot run with ``url``."""
    if method == "single_pass" and url is None:
        raise DbEstimateConfigError(
            "single_pass needs its own ENTITLEMENTS_DB_ESTIMATE_URL (a cross-tenant read-only "
            "role, which needs owner approval); it never runs on the app connection"
        )


@asynccontextmanager
async def open_estimator(method: DbEstimateMethod, url: str | None) -> AsyncIterator[DbEstimator]:
    """The estimator for ``method`` and ``url``, with any extra connection closed on exit."""
    check_settings(method, url)
    if method == "single_pass" and url is not None:
        yield SinglePassEstimator(url)
        return
    if url is None:
        yield PerTenantEstimator(with_tenant)
        return
    async with app_engine_for(url) as engine:

        @asynccontextmanager
        async def on_replica(tenant_id: UUID) -> AsyncIterator[AsyncConnection]:
            async with with_tenant(tenant_id, engine=engine) as conn:
                yield conn

        yield PerTenantEstimator(on_replica)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Entitlement run: overrides, usage, database size."
    )
    parser.add_argument("--period", required=True, type=parse_period, help="YYYY-MM")
    parser.add_argument("--tenant", required=True, action="append", type=UUID, dest="tenants")
    parser.add_argument("--db-estimate", choices=("due", "always", "skip"), default="due")
    parser.add_argument("--db-method", choices=("per_tenant", "single_pass"), default=None)
    parser.add_argument("--db-url", default=None, help="read the estimate from this database")
    args = parser.parse_args(argv)

    try:
        method = configured_method(args.db_method)
        url = configured_url(args.db_url)
        if args.db_estimate != "skip":
            check_settings(method, url)
    except DbEstimateConfigError as exc:
        print(f"entitlements: {exc}", file=sys.stderr)
        return 2

    async def _main() -> RunResult:
        service = EntitlementService()
        try:
            if args.db_estimate == "skip":
                return await run(service, args.tenants, args.period, estimator=None)
            async with open_estimator(method, url) as estimator:
                return await run(
                    service,
                    args.tenants,
                    args.period,
                    estimator=estimator,
                    db_estimate=args.db_estimate,
                )
        finally:
            await dispose_engine()

    result = asyncio.run(_main())
    size = f"database size estimated ({method})" if result.estimated else "database size kept"
    for tenant_id, count in result.expired.items():
        print(
            f"entitlements: tenant {tenant_id}: usage {args.period:%Y-%m}, {size}, "
            f"{count} expired overrides"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
