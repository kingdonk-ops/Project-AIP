"""The ``demo`` workflow spec used across the approvals tests (APPROVALS-01)."""

from __future__ import annotations

import copy
from typing import Any


def demo_spec() -> dict[str, Any]:
    """``draft -> submitted -> approved | rejected``, with ``resubmit`` from ``rejected``."""
    return copy.deepcopy(_DEMO)


def transition(action: str, src: str, dst: str, **extra: Any) -> dict[str, Any]:
    return {
        "action": action,
        "from": src,
        "to": dst,
        "requiredPermission": f"approvals.demo.{action}",
        "guard": None,
        "sideEffects": [],
        "critical": False,
        "labelKey": f"approvals.demo.action.{action}",
        **extra,
    }


_DEMO: dict[str, Any] = {
    "states": [
        {"code": "draft", "labelKey": "approvals.demo.state.draft"},
        {"code": "submitted", "labelKey": "approvals.demo.state.submitted"},
        {"code": "approved", "labelKey": "approvals.demo.state.approved", "terminal": True},
        {"code": "rejected", "labelKey": "approvals.demo.state.rejected"},
    ],
    "initial": "draft",
    "transitions": [
        transition("submit", "draft", "submitted"),
        transition("approve", "submitted", "approved", critical=True),
        transition("reject", "submitted", "rejected"),
        transition("resubmit", "rejected", "submitted"),
    ],
}
