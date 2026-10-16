"""``expect_audited``: assert an event reached the audit chains (AUDIT-02 step 7).

From AUDIT-02 on, a task's "audit events emitted" means the event is in ``audit_log`` (or, for
security events, ``security_audit_events``) after the dispatcher has run. Module tests call::

    async with with_tenant(TENANT_A_ID, engine=app_engine) as conn:
        await expect_audited(conn, "project.created", record_id=project_id)

``conn`` is an ``aip_app`` connection bound to the tenant (both tables are readable to ``aip_app``
under RLS). It lives here, outside ``aip/``, because modules may import only each other's ``api``.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = ["expect_audited"]

_AUDIT = text(
    "SELECT count(*) FROM audit_log WHERE event_type = :name"
    " AND (CAST(:record AS uuid) IS NULL OR record_id = CAST(:record AS uuid))"
)
_SECURITY = text("SELECT count(*) FROM security_audit_events WHERE event_type = :name")
_RECENT = {
    "audit": text("SELECT event_type FROM audit_log ORDER BY seq DESC LIMIT 10"),
    "security": text("SELECT event_type FROM security_audit_events ORDER BY seq DESC LIMIT 10"),
}


async def expect_audited(
    conn: AsyncConnection,
    event_name: str,
    *,
    record_id: UUID | None = None,
    stream: Literal["audit", "security"] = "audit",
    count: int = 1,
) -> None:
    """Fail unless ``stream`` holds exactly ``count`` ``event_name`` entries (for ``record_id``)."""
    if stream == "security" and record_id is not None:
        raise TypeError("security entries have a target_ref, not a record_id")
    if stream == "audit":
        params = {"name": event_name, "record": str(record_id) if record_id else None}
        found = (await conn.execute(_AUDIT, params)).scalar_one()
    else:
        found = (await conn.execute(_SECURITY, {"name": event_name})).scalar_one()
    if found != count:
        recent = [r[0] for r in (await conn.execute(_RECENT[stream])).all()]
        target = f" for record {record_id}" if record_id else ""
        raise AssertionError(
            f"expected {count} {stream} entr{'y' if count == 1 else 'ies'} of {event_name}{target},"
            f" found {found}; latest {stream} entries: {recent}"
        )
