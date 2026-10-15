"""HTTP routes for the audit module.

AUDIT-01 ships no HTTP surface — the writer is an internal interface (``api.AuditApi``) used by
AUDIT-02. The read endpoints (activity feed, timeline, verification) arrive with AUDIT-04. The
module registry requires this router to exist, so it is declared empty for now.
"""

from fastapi import APIRouter

router = APIRouter(tags=["audit"])
