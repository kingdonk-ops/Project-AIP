"""Published interface of the audit module (AUDIT-01).

Other modules may import only this file. ``AuditApi.append`` is the writer side used by AUDIT-02's
outbox consumer: it opens its own ``aip_audit_writer`` transaction (never the caller's ``aip_app``
connection, because only the writer role may touch ``audit_log``) and appends to the tenant's
hash chain. ``AuditEntryIn`` is the input model.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from aip.modules.audit.repository import append_audit_entries
from aip.modules.audit.schemas import AuditEntryIn
from aip.platform.db.session import audit_writer_tenant

__all__ = ["AuditApi", "AuditEntryIn"]

DEFAULT_STREAM = "audit"


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
