"""APPROVALS-04: the pure route plan (groups and ``next_action``)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from aip.modules.approvals.routes_engine.route_plan import (
    Activate,
    Complete,
    PlanStep,
    RouteShapeError,
    StepStatus,
    Wait,
    first_group,
    groups,
    next_action,
)

S1, S2, S3 = UUID(int=1), UUID(int=2), UUID(int=3)


def _route(
    s1: StepStatus = "pending", s2: StepStatus = "waiting", s3: StepStatus = "waiting"
) -> list[PlanStep]:
    """``[{1, serial, U1}, {2, parallel, role QA}, {2, parallel, team Client}]``."""
    return [
        PlanStep(S1, 1, "serial", s1),
        PlanStep(S2, 2, "parallel", s2),
        PlanStep(S3, 2, "parallel", s3),
    ]


def test_steps_sharing_an_order_form_one_group() -> None:
    assert [[s.id for s in g] for g in groups(_route())] == [[S1], [S2, S3]]
    assert first_group(_route()) == 1


def test_groups_follow_step_order_not_list_order() -> None:
    steps = [PlanStep(S2, 5, "serial"), PlanStep(S1, 2, "serial")]
    assert [[s.id for s in g] for g in groups(steps)] == [[S1], [S2]]
    assert first_group(steps) == 2


def test_serial_steps_sharing_an_order_are_refused() -> None:
    with pytest.raises(RouteShapeError):
        groups([PlanStep(S1, 1, "serial"), PlanStep(S2, 1, "parallel")])
    with pytest.raises(RouteShapeError):
        groups([])


def test_a_lone_parallel_step_is_a_group_of_one() -> None:
    assert len(groups([PlanStep(S1, 1, "parallel")])) == 1


def test_approving_the_first_group_activates_the_next() -> None:
    assert next_action(_route(), S1, "approve") == Activate(2)


def test_a_parallel_group_waits_for_every_step() -> None:
    steps = _route(s1="approved", s2="pending", s3="pending")
    assert next_action(steps, S2, "approve") == Wait()
    steps = _route(s1="approved", s2="approved", s3="pending")
    assert next_action(steps, S3, "approve") == Complete("approved")


def test_the_first_rejection_rejects_the_route_and_skips_the_rest() -> None:
    steps = _route(s1="approved", s2="pending", s3="pending")
    assert next_action(steps, S2, "reject") == Complete("rejected", (S3,))
    # A rejection in the first group skips the waiting later groups too.
    assert next_action(_route(), S1, "reject") == Complete("rejected", (S2, S3))


def test_only_a_pending_step_can_be_decided() -> None:
    with pytest.raises(ValueError, match="not a pending step"):
        next_action(_route(), S2, "approve")
    with pytest.raises(ValueError, match="not a pending step"):
        next_action(_route(), uuid4(), "approve")
