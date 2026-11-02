"""Pure inspection rules: the permission codes, the re-inspect rule (INSPECTIONS-01), and who may
save answers in which state plus when a failed answer is announced (INSPECTIONS-02, ADR 0041 §6).

Authorisation is evaluated only through the policy service and RLS, deny by default; the lifecycle
permissions are the ``approvals.inspection.*`` codes the approvals transition service checks. No
database or request context here (ADR 0004).
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "CREATE_PERMISSION",
    "ITP_MANAGE_PERMISSION",
    "ITP_SIGN_PERMISSION",
    "ITP_WAIVE_PERMISSION",
    "RECORD_TYPE",
    "REINSPECTABLE_STATES",
    "RESPOND_PERMISSION",
    "RESPOND_STATES",
    "REVIEW_EDIT_PERMISSION",
    "REVIEW_EDIT_STATES",
    "VIEW_PERMISSION",
    "can_reinspect",
    "emits_answer_failed",
    "permissions_to_respond",
]

RECORD_TYPE: Final = "inspection"  # the approvals record type and definition key family
VIEW_PERMISSION: Final = "inspection.view"
CREATE_PERMISSION: Final = "inspection.create"
RESPOND_PERMISSION: Final = "inspection.respond"
REVIEW_EDIT_PERMISSION: Final = "approvals.inspection.review"  # "Edit Inspection during Review"
ITP_MANAGE_PERMISSION: Final = "itp.manage"  # set up steps, mark a step ready (INSPECTIONS-03)
ITP_SIGN_PERMISSION: Final = "itp.sign"  # start, reopen, release, witness, reject
ITP_WAIVE_PERMISSION: Final = "itp.waive"  # waive a witness point after its notice period

# APPROVALS-09: Performed is the lifecycle's done state (not terminal); a re-inspection is a new
# inspection. Moving the original to Superseded is INSPECTIONS-09.
REINSPECTABLE_STATES: Final = frozenset({"performed"})


def can_reinspect(state: str) -> bool:
    return state in REINSPECTABLE_STATES


# ADR 0041 §6: the person doing the inspection answers in these states (``inspection.respond``) ...
RESPOND_STATES: Final = frozenset({"in_progress", "inspector_review", "rework_required"})
# ... and in supervisor review only a supervisor who may edit during review. Every other state,
# including ``in_progress_sitesync`` (checked out to SiteSync), takes no answers on the web.
REVIEW_EDIT_STATES: Final = frozenset({"supervisor_review"})


def permissions_to_respond(state: str) -> tuple[str, ...] | None:
    """The permissions a caller needs to save answers in ``state``; ``None`` when nobody may."""
    if state in RESPOND_STATES:
        return (RESPOND_PERMISSION,)
    if state in REVIEW_EDIT_STATES:
        return (RESPOND_PERMISSION, REVIEW_EDIT_PERMISSION)
    return None


def emits_answer_failed(previous_failed: bool | None, failed: bool) -> bool:
    """Announce a failed answer only when it newly fails: the field had no answer (``None``) or
    its previous answer passed. Re-saving a failing value announces nothing."""
    return failed and previous_failed is not True
