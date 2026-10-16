"""AUDIT-02 unit tests: mapping a domain event to audit and security entries, and redaction."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from tests.conftest import ALICE_ID, TENANT_A_ID

from aip.modules.audit.mapping import map_event, streams_for
from aip.modules.audit.redact import REDACTED, redact
from aip.platform.events.subscribers import DomainEvent

OCCURRED = datetime(2026, 10, 16, 1, 2, 3, tzinfo=UTC)
PROJECT = UUID("0192f0c1-0000-7000-8000-0000000000aa")


def owners(name: str, version: int) -> str | None:
    """The event registry's owning module, as the projects module registers its events."""
    return "projects" if name.startswith("project.") else None


def event(name: str, payload: dict[str, Any], **over: Any) -> DomainEvent:
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": TENANT_A_ID,
        "project_id": PROJECT,
        "asset_id": None,
        "event_name": name,
        "event_version": 1,
        "aggregate_type": "project",
        "aggregate_id": PROJECT,
        "payload": MappingProxyType(payload),
        "actor_id": ALICE_ID,
        "occurred_at": OCCURRED,
        "attempts": 1,
    }
    values.update(over)
    return DomainEvent(**values)


def test_a_domain_event_maps_to_the_audit_stream() -> None:
    e = event("project.updated", {"before": {"name": "A"}, "after": {"name": "B"}, "code": "P1"})
    mapped = map_event(e, owner_of=owners)
    assert mapped.security is None
    entry = mapped.audit
    assert entry is not None
    assert entry.source_module == "projects"
    assert entry.summary_key == "audit.summary.project.updated"
    assert entry.payload == {"before": {"name": "A"}, "after": {"name": "B"}}
    assert (entry.record_table, entry.record_id) == ("project", PROJECT)
    assert (entry.project_id, entry.actor_id, entry.source_event_id) == (PROJECT, ALICE_ID, e.id)
    assert (entry.event_type, entry.occurred_at) == ("project.updated", OCCURRED)


def test_without_before_and_after_the_payload_is_kept_with_flags_and_reason() -> None:
    e = event("site.updated", {"code": "S1", "flags": ["backdated"], "reason": "Typo in name"})
    entry = map_event(e, owner_of=owners).audit
    assert entry is not None
    assert entry.payload == {"code": "S1", "flags": ["backdated"], "reason": "Typo in name"}
    assert (entry.flags, entry.reason_for_change) == (["backdated"], "Typo in name")
    assert entry.source_module == "site"  # unregistered: the name prefix


def test_auth_events_go_to_the_security_stream_only() -> None:
    e = event(
        "auth.login.failed",
        {
            "sourceIp": "203.0.113.7",
            "device": "Firefox 131",
            "authStrength": "pwd",
            "reason": "bad",
        },
        aggregate_type="user",
        aggregate_id=ALICE_ID,
    )
    mapped = map_event(e)
    assert mapped.audit is None
    sec = mapped.security
    assert sec is not None
    assert (sec.event_type, sec.source_ip, sec.device, sec.auth_strength) == (
        "auth.login.failed",
        "203.0.113.7",
        "Firefox 131",
        "pwd",
    )
    assert sec.target_ref == f"user:{ALICE_ID}"
    assert (sec.actor_id, sec.source_event_id) == (ALICE_ID, e.id)


def test_streams_by_event_name() -> None:
    assert streams_for("project.created") == {"audit"}
    for name in (
        "auth.login.failed",
        "session.revoked",
        "access.role.assigned",
        "permission.granted",
        "export.started",
        "audit.security_event",
    ):
        assert streams_for(name) == {"security"}, name
    assert streams_for("user.deactivated") == {"audit", "security"}
    assert streams_for("authority.changed") == {"audit"}  # a prefix, not a substring


def test_user_deactivated_goes_to_both_streams() -> None:
    mapped = map_event(event("user.deactivated", {"userId": str(ALICE_ID)}, aggregate_type="user"))
    assert mapped.audit is not None and mapped.security is not None


def test_a_recorded_security_event_takes_its_type_and_target_from_the_payload() -> None:
    e = event(
        "audit.security_event",
        {
            "eventType": "access.sensitive_read",
            "targetRef": "inspection:42",
            "detail": {"why": "x"},
        },
    )
    sec = map_event(e).security
    assert sec is not None
    assert (sec.event_type, sec.target_ref, sec.detail) == (
        "access.sensitive_read",
        "inspection:42",
        {"why": "x"},
    )


def test_an_invalid_source_ip_is_dropped_not_stored() -> None:
    sec = map_event(event("auth.logout", {"sourceIp": "not-an-ip"})).security
    assert sec is not None and sec.source_ip is None


def test_secrets_are_redacted_before_mapping() -> None:
    e = event("project.updated", {"after": {"password": "hunter2", "name": "B"}, "before": {}})
    entry = map_event(e).audit
    assert entry is not None and entry.payload == {
        "before": {},
        "after": {"password": REDACTED, "name": "B"},
    }


def test_redact_replaces_secret_keys_at_any_depth() -> None:
    value = {"a": {"password": "x", "nested": [{"api_token": "y"}]}, "name": "ok"}
    assert redact(value) == {
        "a": {"password": "[redacted]", "nested": [{"api_token": "[redacted]"}]},
        "name": "ok",
    }


def test_redact_matches_every_listed_key_ignoring_case() -> None:
    keys = ["Password", "client_SECRET", "refreshToken", "otp", "recovery_codes", "PRIVATE_KEY"]
    keys += ["apiKey", "x_api_key", "Authorization", "credentials", "sessionCookie"]
    assert redact({k: "v" for k in keys}) == {k: REDACTED for k in keys}
    kept = {"footprint": 1, "hotpath": 2, "keyring": 3, "tokenizer_version": 4}
    assert redact(kept) == {**kept, "tokenizer_version": 4}
    assert redact({"note": "my password is x"}) == {"note": "my password is x"}  # keys, not values


def test_redact_covers_name_value_pairs() -> None:
    pairs = [{"name": "password", "value": "x"}, {"key": "colour", "value": "red"}]
    assert redact({"fields": pairs}) == {
        "fields": [{"name": "password", "value": REDACTED}, {"key": "colour", "value": "red"}]
    }
