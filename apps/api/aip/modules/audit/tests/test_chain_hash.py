"""Unit tests for the pure hash-chain function (AUDIT-01). No database needed."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from aip.modules.audit.chain_hash import (
    GENESIS_PREV_HASH,
    HASH_SPEC_VERSION,
    ChainEntry,
    canonical_timestamp,
    compute_hash,
)

FIXTURE = Path(__file__).with_name("fixtures") / "chain-v1.json"


def _load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _entry_from_json(data: dict[str, Any]) -> ChainEntry:
    def u(key: str) -> UUID | None:
        value = data[key]
        return None if value is None else UUID(value)

    occurred = datetime.fromisoformat(data["occurred_at"].replace("Z", "+00:00"))
    return ChainEntry(
        tenant_id=UUID(data["tenant_id"]),
        stream=data["stream"],
        seq=data["seq"],
        occurred_at=occurred,
        event_type=data["event_type"],
        actor_id=u("actor_id"),
        on_behalf_of_id=u("on_behalf_of_id"),
        auth_strength=data["auth_strength"],
        source_module=data["source_module"],
        record_table=data["record_table"],
        record_id=u("record_id"),
        summary_key=data["summary_key"],
        payload=data["payload"],
        reason_for_change=data["reason_for_change"],
        flags=list(data["flags"]),
        project_id=u("project_id"),
        asset_id=u("asset_id"),
        source_event_id=u("source_event_id"),
        supersedes_id=u("supersedes_id"),
    )


def test_genesis_hash_matches_committed_golden_value() -> None:
    data = _load()
    assert data["hash_spec_version"] == HASH_SPEC_VERSION
    assert bytes.fromhex(data["genesis_prev_hash_hex"]) == GENESIS_PREV_HASH
    entry = _entry_from_json(data["entry"])
    assert compute_hash(GENESIS_PREV_HASH, entry).hex() == data["expected_hash_hex"]


def test_reordering_payload_keys_does_not_change_the_hash() -> None:
    data = _load()
    entry = _entry_from_json(data["entry"])
    reordered = dict(data["entry"])
    # Reverse the key order of both before/after blocks; JCS sorts keys, so the hash is identical.
    reordered["payload"] = {
        "after": dict(reversed(list(data["entry"]["payload"]["after"].items()))),
        "before": dict(reversed(list(data["entry"]["payload"]["before"].items()))),
    }
    assert compute_hash(GENESIS_PREV_HASH, _entry_from_json(reordered)) == compute_hash(
        GENESIS_PREV_HASH, entry
    )


def test_changing_one_payload_value_changes_the_hash() -> None:
    data = _load()
    base = compute_hash(GENESIS_PREV_HASH, _entry_from_json(data["entry"]))
    changed = dict(data["entry"])
    changed["payload"] = {
        "before": dict(data["entry"]["payload"]["before"]),
        "after": {**data["entry"]["payload"]["after"], "status": "closing"},
    }
    assert compute_hash(GENESIS_PREV_HASH, _entry_from_json(changed)) != base


def test_flag_order_does_not_change_the_hash() -> None:
    common = {
        "tenant_id": UUID("00000000-0000-4000-8000-00000000000a"),
        "stream": "audit",
        "seq": 7,
        "occurred_at": datetime(2026, 10, 7, 1, 2, 3, tzinfo=UTC),
        "event_type": "gate.override",
    }
    a = ChainEntry(**common, flags=["override", "force_unlock"])
    b = ChainEntry(**common, flags=["force_unlock", "override"])
    assert compute_hash(GENESIS_PREV_HASH, a) == compute_hash(GENESIS_PREV_HASH, b)


def test_occurred_at_renders_with_six_fractional_digits_and_z() -> None:
    assert (
        canonical_timestamp(datetime(2026, 10, 7, 1, 2, 3, 4, tzinfo=UTC))
        == "2026-10-07T01:02:03.000004Z"
    )


def test_occurred_at_is_normalised_to_utc() -> None:
    from datetime import timedelta, timezone

    sydney = timezone(timedelta(hours=11))
    local = datetime(2026, 10, 7, 12, 2, 3, 4, tzinfo=sydney)
    assert canonical_timestamp(local) == "2026-10-07T01:02:03.000004Z"


def test_prev_hash_participates_in_the_hash() -> None:
    entry = ChainEntry(
        tenant_id=UUID("00000000-0000-4000-8000-00000000000a"),
        stream="audit",
        seq=2,
        occurred_at=datetime(2026, 10, 7, 1, 2, 3, tzinfo=UTC),
        event_type="x",
    )
    assert compute_hash(GENESIS_PREV_HASH, entry) != compute_hash(b"\x01" * 32, entry)
