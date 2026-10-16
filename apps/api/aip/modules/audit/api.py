"""Published interface of the audit module (AUDIT-01).

Other modules may import only this file. ``AuditApi.append`` is the writer side used by AUDIT-02's
outbox consumer: it opens its own ``aip_audit_writer`` transaction (never the caller's ``aip_app``
connection, because only the writer role may touch ``audit_log``) and appends to the tenant's
hash chain. ``AuditEntryIn`` is the input model.

AUDIT-02: modules never call ``append`` for their own events: the outbox writer audits every
domain event automatically. ``record_security_event`` (input ``SecurityEventInput``) publishes
a security event that has no domain event (for example a sensitive read) through the outbox,
on the caller's ``with_tenant`` connection, so it commits with the caller's work.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.audit.repository import append_audit_entries
from aip.modules.audit.schemas import AuditEntryIn
from aip.platform.context import new_request_id
from aip.platform.db.session import audit_writer_tenant
from aip.platform.events import Aggregate, emit

__all__ = ["AuditApi", "AuditEntryIn", "SecurityEventInput"]

DEFAULT_STREAM = "audit"


class SecurityEventInput(BaseModel):
    """A security event with no domain event of its own (``record_security_event``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str = Field(min_length=1, max_length=200)
    target_ref: str | None = Field(default=None, max_length=500)
    auth_strength: str | None = Field(default=None, max_length=50)
    source_ip: str | None = Field(default=None, max_length=64)
    device: str | None = Field(default=None, max_length=500)
    detail: dict[str, Any] | None = None


class AuditApi:
    """The operations the audit module offers to other modules."""

    async def append(
        self,
        tenant_id: UUID,
        entries: Sequence[AuditEntryIn],
        *,
        stream: str = DEFAULT_STREAM,
    ) -> list[int]:
        """Append ``entries`` to the tenant's chain and return each entry's ``seq``.

        Opens a dedicated ``aip_audit_writer`` transaction bound to ``tenant_id``; redelivery of an
        entry with an already-seen ``source_event_id`` is a no-op that returns the stored ``seq``.
        """
        async with audit_writer_tenant(tenant_id) as conn:
            return await append_audit_entries(conn, tenant_id, stream, entries)

    async def record_security_event(self, conn: AsyncConnection, event: SecurityEventInput) -> UUID:
        """Publish ``audit.security_event`` on the caller's ``with_tenant`` connection.

        The outbox writer stores it in ``security_audit_events`` with the request's actor; it is
        redacted like every other event. Returns the outbox event id.
        """
        from aip.modules.audit.events import SecurityEventRecorded  # its events.py owns it

        payload = SecurityEventRecorded.model_validate(event.model_dump()).model_dump(
            mode="json", exclude_none=True
        )
        aggregate = Aggregate("security_event", UUID(new_request_id()))
        return await emit(conn, "audit.security_event", 1, aggregate, payload)
