"""Published interface of the uploads module (UPLOADS-01 step 8).

Other modules may import only this file. It exposes the operations other code needs without
reaching into the service, repository or tables. ``create_session`` presigns the quarantine POST;
``get_session_status`` is requester-or-admin bound (the admin check is supplied by the caller, as
the HTTP route does).

UPLOADS-08 (ADR 0036 point 4) adds server-side file access on the caller's ``with_tenant``
connection: ``store_generated_file`` (a worker-made file becomes a clean stored file, idempotent on
its key), ``get_stored_file`` and ``open_stored_file`` (clean files visible to the caller only).
"""

from __future__ import annotations

from uuid import UUID

from aip.modules.uploads.schemas import SessionCreate, SessionCreated, SessionStatus
from aip.modules.uploads.service import AdminCheck, UploadSessionService
from aip.modules.uploads.stored_files import (
    StoredFileConflict,
    StoredFileIntegrityError,
    StoredFileNotFound,
    StoredFileRef,
    get_stored_file,
    open_stored_file,
    store_generated_file,
)

__all__ = [
    "SessionCreate",
    "SessionCreated",
    "SessionStatus",
    "StoredFileConflict",
    "StoredFileIntegrityError",
    "StoredFileNotFound",
    "StoredFileRef",
    "create_session",
    "get_session_status",
    "get_stored_file",
    "open_stored_file",
    "store_generated_file",
]


async def create_session(body: SessionCreate) -> SessionCreated:
    """Start an upload session and presign the quarantine POST (``uploads.create`` is enforced by
    the route; call this only after that check)."""
    return await UploadSessionService().create_session(body)


async def get_session_status(session_id: UUID, *, is_admin: AdminCheck) -> SessionStatus:
    """The session's status for its requester, or a holder of ``uploads.admin`` on its project."""
    return await UploadSessionService().get_status(session_id, is_admin=is_admin)
