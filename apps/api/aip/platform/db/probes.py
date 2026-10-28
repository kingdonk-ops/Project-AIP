"""Login probes for the worker heartbeat (TESTING-13, review 11 M10).

Each probe runs ``SELECT 1`` on one platform engine and reads no tenant data. They live here
because only ``aip.platform.db`` may open a connection straight off an engine (ADR 0002). The
engines refuse an owner, superuser or BYPASSRLS login on connect, so a probe also fails when a
deployment points a URL at the wrong role.
"""

from __future__ import annotations

from sqlalchemy import text

from aip.platform.db.engine import get_audit_writer_engine, get_jobs_engine

__all__ = ["probe_audit_writer", "probe_jobs"]

_SELECT_1 = text("SELECT 1")


async def probe_jobs() -> None:
    """Raise unless ``aip_jobs`` (``DATABASE_JOBS_URL``) can log in and run a query."""
    async with get_jobs_engine().connect() as conn:
        await conn.execute(_SELECT_1)


async def probe_audit_writer() -> None:
    """Raise unless ``aip_audit_writer`` (``DATABASE_AUDIT_WRITER_URL``) can log in."""
    async with get_audit_writer_engine().connect() as conn:
        await conn.execute(_SELECT_1)
