"""Domain event to audit entries (AUDIT-02 step 3).

``map_event`` turns one outbox event into an ``audit_log`` entry, a ``security_audit_events``
entry, or both, after redacting secrets (``redact``):

- **Stream:** names starting ``auth.``, ``session.``, ``access.``, ``permission.`` or ``export.``,
  and ``audit.security_event`` (``AuditApi.record_security_event``), go to the security stream
  only; ``user.deactivated`` goes to both; everything else to ``audit_log``. Security events are
  never in ``audit_log``, so they never show in project timelines.
- **Audit entry:** actor, project and asset from the envelope; ``source_module`` is the module that
  registered the event (else the name's first segment); ``record_table``/``record_id`` are the
  event's aggregate; ``summary_key = audit.summary.<event_name>``; ``payload`` is ``{before,
  after}`` when either is present, else the whole payload; ``flags`` from ``payload.flags``;
  ``reason_for_change`` from ``payload.reason``.
- **Security entry:** ``sourceIp`` (kept only if it parses as an IP address), ``device`` and
  ``authStrength`` from the payload; ``target_ref`` from ``payload.targetRef``, else
  ``<aggregate_type>:<aggregate_id>``; ``detail`` is the payload. For ``audit.security_event`` the
  type, target and detail are the recorded ones.

``source_event_id`` is always the event id, which makes redelivery a no-op in both chains.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from aip.modules.audit.redact import redact
from aip.modules.audit.schemas import AuditEntryIn, SecurityEventIn
from aip.platform.events.subscribers import DomainEvent

__all__ = ["RECORDED_SECURITY_EVENT", "Mapped", "OwnerLookup", "map_event", "streams_for"]

RECORDED_SECURITY_EVENT: Final = "audit.security_event"
SECURITY_PREFIXES: Final = ("auth.", "session.", "access.", "permission.", "export.")
BOTH_STREAMS: Final = frozenset({"user.deactivated"})

OwnerLookup = Callable[[str, int], str | None]


@dataclass(frozen=True, slots=True)
class Mapped:
    audit: AuditEntryIn | None
    security: SecurityEventIn | None


def streams_for(event_name: str) -> frozenset[str]:
    """``{"audit"}``, ``{"security"}`` or both, by event name."""
    if event_name in BOTH_STREAMS:
        return frozenset({"audit", "security"})
    if event_name == RECORDED_SECURITY_EVENT or event_name.startswith(SECURITY_PREFIXES):
        return frozenset({"security"})
    return frozenset({"audit"})


def registry_owner(event_name: str, version: int) -> str | None:
    """The module that registered the event (ARCH-06), or ``None`` if it is not registered."""
    from aip.platform.events.registry import registry

    spec = registry.spec(event_name, version)
    return spec.owner if spec is not None else None


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _ip(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _audit_entry(
    event: DomainEvent, payload: Mapping[str, Any], owner_of: OwnerLookup
) -> AuditEntryIn:
    if "before" in payload or "after" in payload:
        body: dict[str, Any] = {k: payload[k] for k in ("before", "after") if k in payload}
    else:
        body = dict(payload)
    flags = payload.get("flags")
    return AuditEntryIn(
        event_type=event.event_name,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        source_module=owner_of(event.event_name, event.event_version)
        or event.event_name.split(".")[0],
        record_table=event.aggregate_type,
        record_id=event.aggregate_id,
        summary_key=f"audit.summary.{event.event_name}",
        payload=body,
        reason_for_change=_str(payload.get("reason")),
        flags=[f for f in flags if isinstance(f, str)] if isinstance(flags, list) else [],
        project_id=event.project_id,
        asset_id=event.asset_id,
        source_event_id=event.id,
    )


def _security_entry(event: DomainEvent, payload: Mapping[str, Any]) -> SecurityEventIn:
    recorded = event.event_name == RECORDED_SECURITY_EVENT
    detail = payload.get("detail") if recorded else dict(payload)
    return SecurityEventIn(
        event_type=(_str(payload.get("eventType")) if recorded else None) or event.event_name,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        target_ref=_str(payload.get("targetRef")) or f"{event.aggregate_type}:{event.aggregate_id}",
        auth_strength=_str(payload.get("authStrength")),
        source_ip=_ip(payload.get("sourceIp")),
        device=_str(payload.get("device")),
        detail=detail if isinstance(detail, dict) else None,
        source_event_id=event.id,
    )


def map_event(event: DomainEvent, *, owner_of: OwnerLookup = registry_owner) -> Mapped:
    """The audit and/or security entry for ``event``, secrets redacted."""
    payload: dict[str, Any] = redact(dict(event.payload))
    streams = streams_for(event.event_name)
    return Mapped(
        audit=_audit_entry(event, payload, owner_of) if "audit" in streams else None,
        security=_security_entry(event, payload) if "security" in streams else None,
    )
