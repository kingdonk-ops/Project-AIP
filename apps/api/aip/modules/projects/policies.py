"""Authorisation and lifecycle rules for projects (PROJECTS-01).

Permissions are checked through the policy service (``requires`` on every route, plus
``assert_can(..., "project.archive")`` for an archive) and RLS; deny by default.

A project's status only moves forward, except that a project being closed can be reopened:
draft -> active -> closing -> archived, and closing -> active. The closeout gate is out of scope.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ALLOWED_TRANSITIONS", "can_transition"]

ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "draft": frozenset({"active"}),
    "active": frozenset({"closing"}),
    "closing": frozenset({"archived", "active"}),
    "archived": frozenset(),
}


def can_transition(current: str, new: str) -> bool:
    """Whether a project in ``current`` may move to ``new`` (staying put is not a transition)."""
    return new in ALLOWED_TRANSITIONS.get(current, frozenset())
