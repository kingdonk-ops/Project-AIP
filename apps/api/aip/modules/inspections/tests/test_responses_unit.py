"""INSPECTIONS-02 unit tests: the failed-answer rule, the editing rules and the answer body."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from aip.modules.inspections.policies import emits_answer_failed, permissions_to_respond
from aip.modules.inspections.schemas import ResponsesIn


def answer(**extra: Any) -> dict[str, Any]:
    return {"fieldKey": "dft", "value": 300, "clientId": str(uuid.uuid4()), **extra}


@pytest.mark.parametrize(
    ("previous", "failed", "emits"),
    [
        (None, True, True),  # no previous answer, now failing
        (True, True, False),  # re-saving a failing value
        (False, True, True),  # a pass followed by a new failure
        (True, False, False),  # a failure corrected
        (None, False, False),
        (False, False, False),
    ],
)
def test_only_a_newly_failed_answer_is_announced(
    previous: bool | None, failed: bool, emits: bool
) -> None:
    assert emits_answer_failed(previous, failed) is emits


@pytest.mark.parametrize("state", ["in_progress", "inspector_review", "rework_required"])
def test_the_inspector_states_need_only_respond(state: str) -> None:
    assert permissions_to_respond(state) == ("inspection.respond",)


def test_supervisor_review_also_needs_the_review_permission() -> None:
    needed = permissions_to_respond("supervisor_review")
    assert needed == ("inspection.respond", "approvals.inspection.review")


@pytest.mark.parametrize(
    "state",
    [
        "draft",
        "assignable",
        "assigned",
        "in_progress_go",
        "in_progress_sitesync",
        "clarification_required",
        "performed",
        "retired",
    ],
)
def test_every_other_state_takes_no_answers(state: str) -> None:
    assert permissions_to_respond(state) is None


def test_a_body_cannot_send_failed() -> None:
    with pytest.raises(ValidationError) as caught:
        ResponsesIn.model_validate({"answers": [answer(failed=False)]})
    assert any(e["loc"][-1] == "failed" for e in caught.value.errors())


@pytest.mark.parametrize("n", [0, 201])
def test_a_body_holds_one_to_two_hundred_answers(n: int) -> None:
    answers = [answer(fieldKey=f"f{i}") for i in range(n)]
    with pytest.raises(ValidationError):
        ResponsesIn.model_validate({"answers": answers})


def test_two_hundred_answers_are_accepted() -> None:
    answers = [answer(fieldKey=f"f{i}") for i in range(200)]
    assert len(ResponsesIn.model_validate({"answers": answers}).answers) == 200


@pytest.mark.parametrize("key", ["DFT-1", "1dft", "", "a" * 64])
def test_a_field_key_follows_the_form_key_pattern(key: str) -> None:
    with pytest.raises(ValidationError):
        ResponsesIn.model_validate({"answers": [answer(fieldKey=key)]})


def test_a_null_value_clears_the_answer() -> None:
    body = ResponsesIn.model_validate({"answers": [answer(value=None)]})
    assert body.answers[0].value is None


def test_value_is_required() -> None:
    body = answer()
    del body["value"]
    with pytest.raises(ValidationError):
        ResponsesIn.model_validate({"answers": [body]})
