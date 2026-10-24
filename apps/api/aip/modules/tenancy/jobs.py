"""The scheduled entitlement run as a fanned-out job (OPS-17 Part B, review 11 M9).

``tenancy.entitlement_snapshot`` does one tenant's periodic entitlement work — the same two
steps ``snapshot_cli`` runs, now reachable through the OPS-13 trigger, not explicit tenant ids:

1. sweep expired overrides, each with its ``tenant.entitlements_changed`` audit event;
2. upsert the current month's ``tenant_usage`` row from the registered usage sources.

The OPS-13 trigger fans it out per active tenant (see the manifest ``[[schedules]]``). The database
size estimate stays with ``snapshot_cli`` (it needs estimate-day logic and an optional replica
connection); this job never measures the database (``measure_db=False``), so the row keeps its last
estimate. ``EntitlementService`` binds each step to the tenant with its own ``with_tenant``, so the
job's handler context only needs to carry the tenant id.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.ops import api as ops
from aip.modules.tenancy.entitlements.service import EntitlementService

__all__ = ["ENTITLEMENT_SNAPSHOT", "snapshot_entitlements"]

ENTITLEMENT_SNAPSHOT = "tenancy.entitlement_snapshot"


async def snapshot_entitlements(conn: AsyncConnection, job: ops.JobView) -> str | None:
    """Sweep expired overrides and snapshot usage for the job's tenant; return the sweep count."""
    del conn  # EntitlementService binds each step to the tenant itself
    service = EntitlementService()
    period = datetime.now(UTC).date().replace(day=1)
    swept = await service.sweep_expired_overrides(job.tenant_id)
    await service.snapshot_usage(job.tenant_id, period, measure_db=False)
    return f"swept:{swept}"


if ENTITLEMENT_SNAPSHOT not in ops.registered_types():
    ops.register(
        ENTITLEMENT_SNAPSHOT, snapshot_entitlements, queue="default", timeout_s=120, max_attempts=1
    )
