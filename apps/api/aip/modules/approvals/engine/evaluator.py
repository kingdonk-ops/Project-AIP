"""The pure workflow evaluator (APPROVALS-01): no database, clock or randomness.

``available_transitions`` is a UI hint only (which buttons to show); the authoritative check, with
guards and the policy service, is APPROVALS-02. ``apply_transition`` decides whether ``action`` is
legal from ``state`` and where it leads. Both trust a spec that passed ``validate_spec``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aip.modules.approvals.schemas import TransitionSpec, WorkflowDefinitionSpec

__all__ = [
    "TransitionApplied",
    "TransitionError",
    "TransitionRejected",
    "apply_transition",
    "available_transitions",
]

TransitionError = Literal["INVALID_TRANSITION", "UNKNOWN_STATE"]


@dataclass(frozen=True, slots=True)
class TransitionApplied:
    from_state: str
    to_state: str
    transition: TransitionSpec
    ok: Literal[True] = True


@dataclass(frozen=True, slots=True)
class TransitionRejected:
    error: TransitionError
    ok: Literal[False] = False


def available_transitions(
    spec: WorkflowDefinitionSpec, state: str, granted_permissions: frozenset[str] | set[str]
) -> list[str]:
    """The actions from ``state`` whose permission is granted, in spec order."""
    return [
        t.action
        for t in spec.transitions
        if t.from_state == state and t.required_permission in granted_permissions
    ]


def apply_transition(
    spec: WorkflowDefinitionSpec, state: str, action: str
) -> TransitionApplied | TransitionRejected:
    """Where ``action`` from ``state`` leads, or why it cannot be taken."""
    if all(s.code != state for s in spec.states):
        return TransitionRejected("UNKNOWN_STATE")
    for t in spec.transitions:
        if t.from_state == state and t.action == action:
            return TransitionApplied(from_state=state, to_state=t.to_state, transition=t)
    return TransitionRejected("INVALID_TRANSITION")
