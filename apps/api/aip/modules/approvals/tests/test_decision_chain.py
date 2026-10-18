"""APPROVALS-02: the per-instance decision hash chain (pure, no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from aip.modules.approvals.decision_chain import (
    ChainBroken,
    ChainOk,
    entry_hash,
    genesis_hash,
    sha256_hex,
    verify_chain,
)

TENANT = UUID("00000000-0000-4000-8000-00000000000a")
INSTANCE = UUID("00000000-0000-4000-8000-0000000001a1")
ACTOR = UUID("00000000-0000-4000-8000-0000000a11ce")
T0 = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)


def entry(seq: int, prev_hash: str, **changes: Any) -> dict[str, Any]:
    e: dict[str, Any] = {
        "tenant_id": TENANT,
        "instance_id": INSTANCE,
        "seq": seq,
        "from_state": "draft",
        "to_state": "submitted",
        "action": "submit",
        "actor_id": ACTOR,
        "on_behalf_of": None,
        "comment": "ok",
        "auth_strength": "password",
        "ip_address": "203.0.113.7",
        "guard_result": {"passed": True, "guard": {"==": [1, 1]}, "factsHash": "ab" * 32},
        "step_id": None,
        "created_at": T0 + timedelta(minutes=seq),
        "prev_hash": prev_hash,
        "status": "applied",
        "countersigns_id": None,
        "assurance_level": 1,
        "assurance_method": "password",
        "authenticated_at": None,
        "device_id": None,
        "id": UUID(int=seq + 100),
        "supersedes_id": None,
        **changes,
    }
    e["entry_hash"] = entry_hash(e)
    return e


def chain(n: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    prev = genesis_hash(INSTANCE)
    for seq in range(1, n + 1):
        e = entry(seq, prev)
        entries.append(e)
        prev = e["entry_hash"]
    return entries


def test_key_order_does_not_change_the_hash() -> None:
    e = entry(1, genesis_hash(INSTANCE))
    reordered = dict(reversed(list(e.items())))
    assert entry_hash(reordered) == entry_hash(e)
    assert len(entry_hash(e)) == 64


def test_any_change_to_a_field_changes_the_hash() -> None:
    e = entry(1, genesis_hash(INSTANCE))
    assert entry_hash({**e, "comment": "ok."}) != entry_hash(e)
    assert entry_hash({**e, "assurance_method": "totp"}) != entry_hash(e)
    assert entry_hash({**e, "status": "pending_countersign"}) != entry_hash(e)
    assert entry_hash({**e, "id": UUID(int=1)}) != entry_hash(e)
    assert entry_hash({**e, "supersedes_id": UUID(int=2)}) != entry_hash(e)


def test_the_genesis_hash_is_derived_from_the_instance() -> None:
    assert genesis_hash(INSTANCE) == sha256_hex(f"genesis:{INSTANCE}")


def test_an_intact_chain_and_an_empty_chain_verify() -> None:
    assert verify_chain(chain(3)) == ChainOk()
    assert verify_chain([]) == ChainOk()


def test_an_altered_entry_breaks_the_chain_at_its_seq() -> None:
    e1, e2, e3 = chain(3)
    assert verify_chain([e1, {**e2, "comment": "changed"}, e3]) == ChainBroken(broken_at_seq=2)


def test_a_rehashed_entry_still_breaks_the_next_link() -> None:
    e1, e2, e3 = chain(3)
    forged = {**e2, "comment": "changed"}
    forged["entry_hash"] = entry_hash(forged)
    assert verify_chain([e1, forged, e3]) == ChainBroken(broken_at_seq=3)


def test_a_missing_entry_breaks_the_chain() -> None:
    e1, _, e3 = chain(3)
    assert verify_chain([e1, e3]) == ChainBroken(broken_at_seq=3)
