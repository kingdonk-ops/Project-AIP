"""Published interface of the uploads module (UPLOADS-01 step 8).

Other modules may import only this file. It exposes the two operations other code needs — starting
a session and reading its status — without reaching into the service, repository or tables.
``create_session`` presigns the quarantine POST; ``get_session_status`` is requester-or-admin
bound (the admin check is supplied by the caller, as the HTTP route does).
"""

from __future__ import annotations

from uuid import UUID

from aip.modules.uploads.schemas import SessionCreate, SessionCreated, SessionStatus
from aip.modules.uploads.service import AdminCheck, UploadSessionService

__all__ = [
    "SessionCreate",
    "SessionCreated",
    "SessionStatus",
    "create_session",
    "get_session_status",
]


async def create_session(body: SessionCreate) -> SessionCreated:
    """Start an upload session and presign the quarantine POST (``uploads.create`` is enforced by
    the route; call this only after that check)."""
    return await UploadSessionService().create_session(body)


async def get_session_status(session_id: UUID, *, is_admin: AdminCheck) -> SessionStatus:
    """The session's status for its requester, or a holder of ``uploads.admin`` on its project."""
    return await UploadSessionService().get_status(session_id, is_admin=is_admin)
