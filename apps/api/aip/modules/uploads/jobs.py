"""The scheduled upload-session expiry job (OPS-17 Part B, review 11 M9; UPLOADS-01 step 7).

``uploads.expire_sessions`` marks ``requested`` sessions whose presign TTL has passed as
``expired``. The OPS-13 scheduled-job trigger fans it out per active tenant (see the uploads
manifest ``[[schedules]]``), and each run executes in the job's ``with_tenant`` transaction as
``aip_app`` (OPS-17 Part A), so it only touches its own tenant's sessions. Idempotent: a session
already past ``requested`` is not matched, so a rerun in the same window is a no-op.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.ops import api as ops

from . import repository as repo
from .pipeline.runner import run_scan_pipeline

__all__ = ["EXPIRE_SESSIONS", "SCAN", "SCAN_MAX_ATTEMPTS", "expire_sessions", "scan"]

EXPIRE_SESSIONS = "uploads.expire_sessions"
SCAN = "uploads.scan"
# Total tries for a scan (1 = no retry). A scan that cannot complete fails closed by retrying, and
# the last attempt rejects as ``scan_error`` so a session is never left mid-scan.
SCAN_MAX_ATTEMPTS = 3


async def expire_sessions(conn: AsyncConnection, job: ops.JobView) -> str | None:
    """Expire this tenant's stale upload sessions in the job's transaction; return the count."""
    del job  # the tenant comes from the job's with_tenant context
    expired = await repo.expire_stale(conn, datetime.now(UTC))
    return f"expired:{expired}"


async def scan(conn: AsyncConnection, job: ops.JobView) -> str | None:
    """Scan one session's quarantine object in the job's transaction (release or reject)."""
    session_id = UUID(str(job.payload["session_id"]))
    is_last_attempt = job.attempts >= SCAN_MAX_ATTEMPTS
    return await run_scan_pipeline(conn, session_id, is_last_attempt=is_last_attempt)


if EXPIRE_SESSIONS not in ops.registered_types():
    ops.register(EXPIRE_SESSIONS, expire_sessions, queue="default", timeout_s=60, max_attempts=1)

if SCAN not in ops.registered_types():
    ops.register(SCAN, scan, queue="scan", timeout_s=120, max_attempts=SCAN_MAX_ATTEMPTS)
