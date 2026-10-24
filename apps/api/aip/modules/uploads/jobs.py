"""The scheduled upload-session expiry job (OPS-17 Part B, review 11 M9; UPLOADS-01 step 7).

``uploads.expire_sessions`` marks ``requested`` sessions whose presign TTL has passed as
``expired``. The OPS-13 scheduled-job trigger fans it out per active tenant (see the uploads
manifest ``[[schedules]]``), and each run executes in the job's ``with_tenant`` transaction as
``aip_app`` (OPS-17 Part A), so it only touches its own tenant's sessions. Idempotent: a session
already past ``requested`` is not matched, so a rerun in the same window is a no-op.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.ops import api as ops

from . import repository as repo

__all__ = ["EXPIRE_SESSIONS", "expire_sessions"]

EXPIRE_SESSIONS = "uploads.expire_sessions"


async def expire_sessions(conn: AsyncConnection, job: ops.JobView) -> str | None:
    """Expire this tenant's stale upload sessions in the job's transaction; return the count."""
    del job  # the tenant comes from the job's with_tenant context
    expired = await repo.expire_stale(conn, datetime.now(UTC))
    return f"expired:{expired}"


if EXPIRE_SESSIONS not in ops.registered_types():
    ops.register(EXPIRE_SESSIONS, expire_sessions, queue="default", timeout_s=60, max_attempts=1)
