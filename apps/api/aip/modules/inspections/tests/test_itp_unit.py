"""INSPECTIONS-03 unit tests: the ITP step rules, the sign-off hash chain and the strict bodies."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from aip.modules.inspections.itp_rules import (
    Moved,
    Refused,
    Step,
    apply_action,
    apply_decision,
)
from aip.modules.inspections.schemas import ItpStepIn, SignoffIn
from aip.modules.inspections.signoff_chain import (
    ChainBroken,
    ChainOk,
    content_hash,
    entry_hash,
    genesis_hash,
    verify_chain,
)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def decide(step: Step, decision: str, comment: str | None = "ok") -> Moved | Refused:
    return apply_decision(step, decision, comment=comment, now=NOW, steps=[step])


# --- the rule table ------------------------------------------------------------------------------


def test_approving_a_hold_point_releases_it_as_a_hold_point_release() -> None:
    assert decide(Step(1, "hold", "in_progress"), "approve") == Moved(
        "released", "hold_point.release"
    )


@pytest.mark.parametrize(
    ("point_type", "decision"), [("witness", "approve"), ("review", "witnessed")]
)
def test_a_decision_for_another_point_type_is_invalid(point_type: str, decision: str) -> None:
    assert decide(Step(1, point_type, "in_progress"), decision) == Refused(
        409, "INVALID_STEP_ACTION"
    )


def test_the_other_decisions_name_their_assurance_action() -> None:
    assert decide(Step(1, "witness", "in_progress"), "witnessed") == Moved(
        "released", "witness.countersign"
    )
    assert decide(Step(1, "review", "in_progress"), "approve") == Moved("released", "itp.signoff")
    rejected = decide(Step(1, "hold", "in_progress"), "reject")
    assert rejected == Moved("rejected", "itp.reject")
    assert isinstance(rejected, Moved) and not rejected.critical


def test_a_witness_point_is_waived_only_after_its_notice() -> None:
    def witness(hours_ago: int) -> Step:
        return Step(
            1, "witness", "ready", ready_at=NOW - timedelta(hours=hours_ago), notice_hours=24
        )

    assert decide(witness(25), "waived") == Moved("waived", "itp.signoff")
    assert decide(witness(23), "waived") == Refused(409, "NOTICE_NOT_ELAPSED")


def test_a_held_step_cannot_be_released() -> None:
    held = Step(1, "hold", "in_progress", held=True)
    assert decide(held, "approve") == Refused(409, "STEP_ON_HOLD")
    assert decide(held, "reject") == Moved("rejected", "itp.reject")


@pytest.mark.parametrize("comment", [None, "", "   "])
def test_reject_and_waive_need_a_comment(comment: str | None) -> None:
    assert decide(Step(1, "hold", "in_progress"), "reject", comment) == Refused(
        422, "COMMENT_REQUIRED"
    )
    old_witness = Step(1, "witness", "ready", ready_at=NOW - timedelta(days=2), notice_hours=24)
    assert decide(old_witness, "waived", comment) == Refused(422, "COMMENT_REQUIRED")


def test_actions_move_through_the_statuses() -> None:
    assert apply_action(Step(1, "hold", "pending"), "ready", []) == Moved("ready")
    assert apply_action(Step(1, "hold", "ready"), "start", []) == Moved("in_progress")
    assert apply_action(Step(1, "hold", "rejected"), "reopen", []) == Moved("in_progress")
    assert apply_action(Step(1, "hold", "released"), "start", []) == Refused(
        409, "INVALID_STEP_ACTION"
    )


def test_a_later_step_waits_for_every_earlier_hold_point() -> None:
    steps = [
        Step(1, "hold", "released"),
        Step(2, "hold", "in_progress"),
        Step(3, "review", "ready"),
    ]
    assert apply_action(steps[2], "start", steps) == Refused(409, "BLOCKED_BY_HOLD")
    released = [steps[0], Step(2, "hold", "released"), steps[2]]
    assert apply_action(released[2], "start", released) == Moved("in_progress")


def test_a_witness_point_cannot_be_waived_past_an_open_hold() -> None:
    witness = Step(2, "witness", "ready", ready_at=NOW - timedelta(days=2), notice_hours=24)
    steps = [Step(1, "hold", "in_progress"), witness]
    assert apply_decision(witness, "waived", comment="x", now=NOW, steps=steps) == Refused(
        409, "BLOCKED_BY_HOLD"
    )


# --- the hash chain ------------------------------------------------------------------------------


def chain(n: int) -> list[dict[str, Any]]:
    inspection_id = uuid.uuid4()
    entries: list[dict[str, Any]] = []
    previous = genesis_hash(inspection_id)
    for seq in range(1, n + 1):
        entry: dict[str, Any] = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "inspection_id": inspection_id,
            "itp_step_id": uuid.uuid4(),
            "asset_id": uuid.uuid4(),
            "seq": seq,
            "signatory_role": "inspector",
            "signer_user_id": uuid.uuid4(),
            "decision": "approve",
            "action_code": "hold_point.release",
            "status": "applied",
            "countersigns_id": None,
            "auth_strength": "mfa",
            "assurance_level": 2,
            "assurance_method": "totp",
            "authenticated_at": NOW,
            "device_id": None,
            "eligibility_result": None,
            "content_hash": "c" * 64,
            "prev_hash": previous,
            "comment": "ok",
            "signed_at": NOW + timedelta(minutes=seq),
        }
        entry["entry_hash"] = entry_hash(entry)
        previous = entry["entry_hash"]
        entries.append(entry)
    return entries


def test_the_entry_hash_ignores_key_order_but_not_content() -> None:
    entry = chain(1)[0]
    reordered = dict(reversed(list(entry.items())))
    assert entry_hash(reordered) == entry_hash(entry)
    assert entry_hash({**entry, "comment": "ok."}) != entry_hash(entry)
    # created_at is set by the database and is not part of the hash.
    assert entry_hash({**entry, "created_at": NOW}) == entry_hash(entry)


def test_verify_chain_finds_the_altered_entry() -> None:
    entries = chain(3)
    assert verify_chain(entries) == ChainOk()
    entries[1] = {**entries[1], "decision": "reject"}
    assert verify_chain(entries) == ChainBroken(2)
    assert verify_chain([]) == ChainOk()


def test_the_first_entry_links_to_the_genesis_hash() -> None:
    entries = chain(2)
    entries[0] = {**entries[0], "prev_hash": "0" * 64}
    entries[0]["entry_hash"] = entry_hash(entries[0])
    assert verify_chain(entries) == ChainBroken(1)


def test_the_content_hash_covers_the_answers() -> None:
    inspection_id, revision_id, step_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first = content_hash(inspection_id, revision_id, step_id, {"dft": 300, "prep": "sa3"})
    assert content_hash(inspection_id, revision_id, step_id, {"prep": "sa3", "dft": 300}) == first
    assert content_hash(inspection_id, revision_id, step_id, {"dft": 301, "prep": "sa3"}) != first


# --- strict bodies -------------------------------------------------------------------------------


def test_a_client_signatory_is_refused() -> None:
    with pytest.raises(ValidationError):
        SignoffIn.model_validate({"decision": "approve", "signatoryRole": "client"})


def test_a_sign_off_cannot_claim_its_assurance() -> None:
    with pytest.raises(ValidationError):
        SignoffIn.model_validate(
            {"decision": "approve", "signatoryRole": "inspector", "assuranceLevel": 2}
        )


def test_notice_hours_belong_to_witness_points_only() -> None:
    body = {"seq": 1, "title": "Surface preparation", "pointType": "hold", "noticeHours": 24}
    with pytest.raises(ValidationError):
        ItpStepIn.model_validate(body)
    assert ItpStepIn.model_validate({**body, "pointType": "witness"}).notice_hours == 24
