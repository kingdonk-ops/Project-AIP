"""The pure rules of an approval route (APPROVALS-04): no database, clock or randomness.

A route is groups of steps ordered by ``step_order``. Steps that share an order form one group;
a group of more than one step must be all ``parallel`` (``RouteShapeError`` otherwise), and a lone
step may be either mode. Groups run one after another, and a group completes when **all** of its
steps approve.

``next_action(steps, step_id, decision)`` says what one decision on a ``pending`` step does:

- ``Activate(order)``: the decision completed its group; the next group becomes ``pending``;
- ``Wait()``: the group still has undecided steps;
- ``Complete("approved")``: the last group completed;
- ``Complete("rejected", skip)``: the first rejection rejects the whole route, and every undecided
  step (pending siblings and waiting later groups) becomes ``skipped``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import groupby
from typing import Literal
from uuid import UUID

__all__ = [
    "Activate",
    "Complete",
    "Decision",
    "PlanStep",
    "RouteShapeError",
    "StepMode",
    "StepStatus",
    "Wait",
    "first_group",
    "groups",
    "next_action",
]

StepMode = Literal["serial", "parallel"]
StepStatus = Literal["waiting", "pending", "approved", "rejected", "skipped"]
Decision = Literal["approve", "reject"]

_UNDECIDED: frozenset[str] = frozenset({"waiting", "pending"})


class RouteShapeError(ValueError):
    """The steps do not form a valid route (no steps, or serial steps sharing an order)."""


@dataclass(frozen=True, slots=True)
class PlanStep:
    id: UUID
    step_order: int
    mode: StepMode
    status: StepStatus | None = None


@dataclass(frozen=True, slots=True)
class Activate:
    order: int


@dataclass(frozen=True, slots=True)
class Wait:
    pass


@dataclass(frozen=True, slots=True)
class Complete:
    outcome: Literal["approved", "rejected"]
    skip: tuple[UUID, ...] = ()


def groups(steps: Sequence[PlanStep]) -> list[list[PlanStep]]:
    """The steps grouped by ``step_order``, in order; raises ``RouteShapeError`` for a bad shape."""
    if not steps:
        raise RouteShapeError("a route needs at least one step")
    ordered = sorted(steps, key=lambda s: s.step_order)
    result = [list(group) for _, group in groupby(ordered, key=lambda s: s.step_order)]
    for group in result:
        if len(group) > 1 and any(s.mode != "parallel" for s in group):
            raise RouteShapeError(f"steps sharing order {group[0].step_order} must all be parallel")
    return result


def first_group(steps: Sequence[PlanStep]) -> int:
    """The ``step_order`` of the group a new route activates."""
    return groups(steps)[0][0].step_order


def next_action(
    steps: Sequence[PlanStep], step_id: UUID, decision: Decision
) -> Activate | Wait | Complete:
    """What ``decision`` on pending step ``step_id`` does to the route (see the module doc)."""
    by_id = {s.id: s for s in steps}
    step = by_id.get(step_id)
    if step is None or step.status != "pending":
        raise ValueError(f"step {step_id} is not a pending step of this route")
    if decision == "reject":
        skip = tuple(s.id for s in steps if s.id != step_id and s.status in _UNDECIDED)
        return Complete("rejected", skip)
    after = [replace(s, status="approved") if s.id == step_id else s for s in steps]
    for group in groups(after):
        if group[0].step_order < step.step_order:
            continue
        if group[0].step_order == step.step_order:
            if any(s.status != "approved" for s in group):
                return Wait()
            continue
        return Activate(group[0].step_order)
    return Complete("approved")
