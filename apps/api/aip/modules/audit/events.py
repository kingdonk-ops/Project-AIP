"""Domain events the audit module publishes and subscribes to (via the outbox, ADR 0003).

- ``audit.security_event`` v1 (AUDIT-02 step 6): a security event with no domain event of its own
  (for example a sensitive read), published by ``AuditApi.record_security_event`` so it gets the
  outbox's ordering and idempotency. The writer routes it to ``security_audit_events``.
- The catch-all subscriber ``write_audit_entries`` (``"*"``, AUDIT-02 step 2): every event of every
  loaded module goes into the audit chains (``writer.write_event``), after the event's own
  subscribers. Modules only emit; they never write audit rows themselves.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.audit.mapping import RECORDED_SECURITY_EVENT
from aip.modules.audit.writer import write_event
from aip.platform.events import register_event
from aip.platform.events.subscribers import ANY_EVENT, DomainEvent, subscriber

__all__ = ["SECURITY_EVENT_RECORDED", "SecurityEventRecorded", "write_audit_entries"]

SECURITY_EVENT_RECORDED = RECORDED_SECURITY_EVENT


class SecurityEventRecorded(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )

    event_type: str = Field(min_length=1, max_length=200)
    target_ref: str | None = Field(default=None, max_length=500)
    auth_strength: str | None = Field(default=None, max_length=50)
    source_ip: str | None = Field(default=None, max_length=64)
    device: str | None = Field(default=None, max_length=500)
    detail: dict[str, Any] | None = None


register_event(SECURITY_EVENT_RECORDED, 1, SecurityEventRecorded, "audit")


@subscriber(ANY_EVENT, 1)
async def write_audit_entries(conn: AsyncConnection, event: DomainEvent) -> None:
    """Append ``event`` to the audit chains (``conn``, the subscribers' one, is unused)."""
    await write_event(event)
