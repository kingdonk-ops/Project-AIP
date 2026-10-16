"""Write one outbox event into the audit chains (AUDIT-02 step 2).

Called by the catch-all subscriber in ``events.py``. It opens its own ``aip_audit_writer``
transaction for the event's tenant (never the subscribers' ``aip_app`` connection: only the writer
role may insert into the chains) and appends the mapped entries, both streams in that one
transaction. An exception propagates to the dispatcher, which records the failure and retries the
event, so a lost audit write never goes unnoticed. ``source_event_id`` makes a redelivery a no-op.
"""

from __future__ import annotations

from aip.modules.audit.mapping import map_event
from aip.modules.audit.repository import append_audit_entries, append_security_events
from aip.platform.db.session import audit_writer_tenant
from aip.platform.events.subscribers import DomainEvent

__all__ = ["write_event"]

AUDIT_STREAM = "audit"


async def write_event(event: DomainEvent) -> None:
    mapped = map_event(event)
    async with audit_writer_tenant(event.tenant_id) as conn:
        if mapped.audit is not None:
            await append_audit_entries(conn, event.tenant_id, AUDIT_STREAM, [mapped.audit])
        if mapped.security is not None:
            await append_security_events(conn, event.tenant_id, [mapped.security])
