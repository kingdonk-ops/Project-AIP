"""The hashed contract of a ``security_audit_events`` row (AUDIT-02).

The security stream reuses :func:`chain_hash.compute_hash` unchanged. A row is rendered into a
:class:`chain_hash.ChainEntry` with ``stream = "security"`` and these fields:

    tenant_id, seq, occurred_at, event_type, actor_id, auth_strength, source_event_id, and
    payload = {"target_ref": target_ref, "detail": detail}

Every other ``ChainEntry`` field is null (or ``()`` for flags). As in ``audit_log``, ``source_ip``
and ``device`` are stored for querying but are not hashed. The verifier (AUDIT-03) uses this same
function, so its rendering must never change for an existing row. Like ``chain_hash`` it imports
nothing from ``aip.platform``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aip.modules.audit.chain_hash import ChainEntry

__all__ = ["SECURITY_STREAM", "security_chain_entry"]

SECURITY_STREAM = "security"


def security_chain_entry(row: Mapping[str, Any]) -> ChainEntry:
    """The ``ChainEntry`` hashed for a security row (stored, or about to be written)."""
    return ChainEntry(
        tenant_id=row["tenant_id"],
        stream=SECURITY_STREAM,
        seq=row["seq"],
        occurred_at=row["occurred_at"],
        event_type=row["event_type"],
        actor_id=row.get("actor_id"),
        auth_strength=row.get("auth_strength"),
        payload={"target_ref": row.get("target_ref"), "detail": row.get("detail")},
        source_event_id=row.get("source_event_id"),
    )
