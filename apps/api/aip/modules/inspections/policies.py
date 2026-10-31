"""Pure inspection rules (INSPECTIONS-01): the permission codes and the re-inspect rule.

Authorisation is evaluated only through the policy service and RLS, deny by default; the lifecycle
permissions are the ``approvals.inspection.*`` codes the approvals transition service checks. No
database or request context here (ADR 0004).
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "CREATE_PERMISSION",
    "RECORD_TYPE",
    "REINSPECTABLE_STATES",
    "VIEW_PERMISSION",
    "can_reinspect",
]

RECORD_TYPE: Final = "inspection"  # the approvals record type and definition key family
VIEW_PERMISSION: Final = "inspection.view"
CREATE_PERMISSION: Final = "inspection.create"

# APPROVALS-09: Performed is the lifecycle's done state (not terminal); a re-inspection is a new
# inspection. Moving the original to Superseded is INSPECTIONS-09.
REINSPECTABLE_STATES: Final = frozenset({"performed"})


def can_reinspect(state: str) -> bool:
    return state in REINSPECTABLE_STATES
