"""The ITP step machine as data (INSPECTIONS-03): pure, no I/O, stable codes.

Actions move a step without a sign-off:

- ``ready`` pending → ready (sets ``ready_at``; for a witness point this is when notice is given);
- ``start`` ready → in_progress, refused while any lower-``seq`` hold step is not released or
  waived (``BLOCKED_BY_HOLD``);
- ``reopen`` rejected → in_progress.

Sign-off decisions append an ``inspection_signoffs`` row:

- ``approve`` in_progress → released (hold, review and surveillance points);
- ``witnessed`` in_progress → released (witness points only);
- ``waived`` ready or in_progress → waived (witness points only, once ``ready_at + notice_hours``
  has passed, with a comment);
- ``reject`` in_progress → rejected (with a comment).

``approve``, ``witnessed`` and ``waived`` are refused while an NCR holds the step
(``STEP_ON_HOLD``) or an earlier hold point is open (``BLOCKED_BY_HOLD``: a waiver from ``ready``
must not jump a hold). Each decision names the identity assurance action it is checked against
(ADR 0010): a hold release is ``hold_point.release``, a witness ``witness.countersign``, any other
release or waiver ``itp.signoff``. ``reject`` is not critical: its row records the signer's
assurance under ``itp.reject``, which identity never checks.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, Literal

__all__ = [
    "ACTIONS",
    "CRITICAL_ACTION_CODES",
    "DECISIONS",
    "DONE_STATUSES",
    "POINT_TYPES",
    "REJECT_ACTION_CODE",
    "SIGNATORY_ROLES",
    "STATUSES",
    "STEP_SETUP_STATES",
    "Moved",
    "Refused",
    "Step",
    "action_code",
    "apply_action",
    "apply_decision",
    "blocked_by_hold",
    "is_open",
]

PointType = Literal["hold", "witness", "review", "surveillance"]
StepAction = Literal["ready", "start", "reopen"]
Decision = Literal["approve", "reject", "witnessed", "waived"]
SignatoryRole = Literal["inspector", "supervisor", "third_party"]

POINT_TYPES: Final = ("hold", "witness", "review", "surveillance")
STATUSES: Final = ("pending", "ready", "in_progress", "released", "waived", "rejected")
ACTIONS: Final = ("ready", "start", "reopen")
DECISIONS: Final = ("approve", "reject", "witnessed", "waived")
SIGNATORY_ROLES: Final = ("inspector", "supervisor", "third_party")  # no client: INSPECTIONS-05
DONE_STATUSES: Final = frozenset({"released", "waived"})

# The ITP lifecycle states in which steps may still be set up; afterwards they are fixed.
STEP_SETUP_STATES: Final = frozenset({"draft", "assignable", "assigned"})

REJECT_ACTION_CODE: Final = "itp.reject"
CRITICAL_ACTION_CODES: Final = frozenset(
    {"hold_point.release", "witness.countersign", "itp.signoff"}
)

_ACTION_MOVES: Final[dict[str, tuple[frozenset[str], str]]] = {
    "ready": (frozenset({"pending"}), "ready"),
    "start": (frozenset({"ready"}), "in_progress"),
    "reopen": (frozenset({"rejected"}), "in_progress"),
}
_RELEASING: Final = frozenset({"approve", "witnessed", "waived"})


@dataclass(frozen=True, slots=True)
class Step:
    """What the rules look at on one step."""

    seq: int
    point_type: str
    status: str
    held: bool = False
    ready_at: datetime | None = None
    notice_hours: int | None = None

    @classmethod
    def of(cls, row: Mapping[str, Any]) -> Step:
        return cls(
            seq=int(row["seq"]),
            point_type=str(row["point_type"]),
            status=str(row["status"]),
            held=row.get("hold_flag_issue_id") is not None,
            ready_at=row.get("ready_at"),
            notice_hours=row.get("notice_hours"),
        )


@dataclass(frozen=True, slots=True)
class Moved:
    """The step may move to ``to_status``; ``action_code`` is set for a sign-off decision."""

    to_status: str
    action_code: str | None = None

    @property
    def critical(self) -> bool:
        return self.action_code in CRITICAL_ACTION_CODES


@dataclass(frozen=True, slots=True)
class Refused:
    """The rule refuses: HTTP ``status_code`` with a stable ``code``."""

    status_code: int
    code: str


def is_open(status: str) -> bool:
    """A step still to be done: not released and not waived."""
    return status not in DONE_STATUSES


def blocked_by_hold(seq: int, steps: Iterable[Step]) -> bool:
    """A lower-``seq`` hold point is not released or waived yet."""
    return any(s.point_type == "hold" and s.seq < seq and is_open(s.status) for s in steps)


def action_code(point_type: str, decision: str) -> str:
    """The identity assurance action a decision on this point type is checked against."""
    if decision == "reject":
        return REJECT_ACTION_CODE
    if decision == "witnessed":
        return "witness.countersign"
    if decision == "approve" and point_type == "hold":
        return "hold_point.release"
    return "itp.signoff"


def apply_action(step: Step, action: str, steps: Iterable[Step]) -> Moved | Refused:
    """``ready``, ``start`` or ``reopen`` on ``step``; ``steps`` are the ITP's live steps."""
    move = _ACTION_MOVES.get(action)
    if move is None or step.status not in move[0]:
        return Refused(409, "INVALID_STEP_ACTION")
    if action == "start" and blocked_by_hold(step.seq, steps):
        return Refused(409, "BLOCKED_BY_HOLD")
    return Moved(move[1])


def _decision_target(step: Step, decision: str) -> str | None:
    """The status ``decision`` moves ``step`` to, or ``None`` when it does not apply."""
    witness = step.point_type == "witness"
    if decision == "approve" and not witness and step.status == "in_progress":
        return "released"
    if decision == "witnessed" and witness and step.status == "in_progress":
        return "released"
    if decision == "waived" and witness and step.status in ("ready", "in_progress"):
        return "waived"
    if decision == "reject" and step.status == "in_progress":
        return "rejected"
    return None


def apply_decision(
    step: Step,
    decision: str,
    *,
    comment: str | None,
    now: datetime,
    steps: Iterable[Step],
) -> Moved | Refused:
    """A sign-off ``decision`` on ``step`` at ``now``; ``steps`` are the ITP's live steps."""
    to_status = _decision_target(step, decision)
    if to_status is None:
        return Refused(409, "INVALID_STEP_ACTION")
    if decision in _RELEASING:
        if step.held:
            return Refused(409, "STEP_ON_HOLD")
        if blocked_by_hold(step.seq, steps):
            return Refused(409, "BLOCKED_BY_HOLD")
    if decision == "waived":
        notice = timedelta(hours=step.notice_hours or 0)
        if step.ready_at is None or now < step.ready_at + notice:
            return Refused(409, "NOTICE_NOT_ELAPSED")
    if decision in ("waived", "reject") and not (comment and comment.strip()):
        return Refused(422, "COMMENT_REQUIRED")
    return Moved(to_status, action_code(step.point_type, decision))
