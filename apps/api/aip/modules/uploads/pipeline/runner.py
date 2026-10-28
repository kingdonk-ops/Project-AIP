"""The stateful scan pipeline (UPLOADS-02 steps 3-5): the entry point the worker calls.

``run_scan_pipeline`` runs inside the job's ``with_tenant`` transaction. It loads the session,
streams the quarantine object once (hashing as it goes), runs the pure stage reducer, writes one
``scan_results`` row per stage, and then either releases the object or rejects the session — all in
the one transaction, so a released file, its ``stored_files`` row and the ``upload.completed`` event
commit together (exactly once per session). It fails closed: a scan that could not complete raises
so the job retries, and only the last attempt turns that into a ``rejected`` / ``scan_error``.

The pipeline is the only code that calls ``release``; it is not exported from ``api.py`` and no
controller can reach it.
"""

from __future__ import annotations

import hashlib
import os
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.uploads import repository as repo
from aip.modules.uploads.events import UPLOAD_COMPLETED, UPLOAD_REJECTED
from aip.platform.capabilities import ObjectNotFoundError, get_object_store
from aip.platform.capabilities.keys import ObjectKey, tenant_key
from aip.platform.context import get_context, new_request_id
from aip.platform.events.outbox import Aggregate, emit

from .clamav_client import ClamdSettings
from .magic_bytes import stored_mime
from .reducer import ScanInput, ScanVerdict, run_scan

__all__ = ["clamd_settings_from_env", "run_scan_pipeline"]

# Terminal states: a redelivered or doubly-enqueued job finds the session already decided and
# no-ops, so release happens at most once (the spec's "enqueue twice -> one stored_files row").
_DECIDED = frozenset({"released", "rejected", "expired", "aborted"})
_SINGLE_PART_MAX = 100 * 1024 * 1024  # mirrors platform_limits.SINGLE_PART_MAX_BYTES


def clamd_settings_from_env() -> ClamdSettings:
    """clamd settings from the environment (the compose ``clamav`` service by default)."""
    return ClamdSettings(
        host=os.getenv("CLAMD_HOST", "clamav"),
        port=int(os.getenv("CLAMD_PORT", "3310")),
        timeout_s=float(os.getenv("CLAMD_TIMEOUT_S", "60")),
    )


async def run_scan_pipeline(
    conn: AsyncConnection,
    session_id: UUID,
    *,
    is_last_attempt: bool,
    clamd: ClamdSettings | None = None,
) -> str:
    """Scan the session's quarantine object and release or reject it; return a short status string.

    Raises on a scan ``error`` (so the job retries) unless this is the last attempt, when the
    session is rejected as ``scan_error`` instead.
    """
    clamd = clamd if clamd is not None else clamd_settings_from_env()
    # ``stored_files`` is project-scoped (ACCESS-03) and fails closed without a principal. A scan is
    # background work, so it acts as the tenant-wide system principal, set on the job's transaction
    # (the tenant is already set by the worker's ``with_tenant``).
    await conn.execute(text("SELECT set_config('app.principal_kind', 'system', true)"))
    session = await repo.get_session(conn, session_id)
    if session is None:
        return "missing"
    if session["status"] in _DECIDED:
        return f"noop:{session['status']}"

    await repo.set_status(conn, session_id, "scanning")

    store = get_object_store()
    try:
        data = await store.get(ObjectKey(session["quarantine_key"]))
    except ObjectNotFoundError:
        return await _reject(conn, session, "object_missing")
    sha256 = hashlib.sha256(data).hexdigest()

    verdict = await run_scan(
        ScanInput(
            data=data,
            declared_mime=str(session["declared_mime"]),
            declared_size=int(session["declared_size_bytes"]),
            platform_max=_SINGLE_PART_MAX,
        ),
        clamd,
    )
    await _record_stages(conn, session, verdict)

    if verdict.outcome == "pass":
        return await _release(conn, session, verdict, data=data, sha256=sha256)
    if verdict.outcome == "fail":
        return await _reject(conn, session, verdict.results[-1].stage)
    # ``error``: fail closed. Retry until the last attempt, then reject so the session is not stuck.
    if not is_last_attempt:
        raise ScanError(f"scan did not complete for session {session_id}")
    return await _reject(conn, session, "scan_error")


class ScanError(RuntimeError):
    """A scan could not complete; raised to make the worker retry (fail-closed)."""


async def _record_stages(conn: AsyncConnection, session: repo.Row, verdict: ScanVerdict) -> None:
    """Append one append-only ``scan_results`` row per stage that ran."""
    for result in verdict.results:
        await repo.insert_scan_result(
            conn,
            {
                "id": UUID(new_request_id()),
                "tenant_id": session["tenant_id"],
                "session_id": session["id"],
                "file_id": None,
                "stage": result.stage,
                "outcome": result.outcome,
                "signature_db_version": result.detail.get("signature_db_version"),
                "detail": result.detail or None,
            },
        )


async def _release(
    conn: AsyncConnection,
    session: repo.Row,
    verdict: ScanVerdict,
    *,
    data: bytes,
    sha256: str,
) -> str:
    """Private: copy the clean object into tenant storage and record it, in the one transaction."""
    ctx = get_context()
    file_id = UUID(new_request_id())
    released_key = tenant_key(ctx.tenant_id, "files", str(file_id))
    detected_mime = stored_mime(verdict.detected_mime, str(session["declared_mime"]))

    store = get_object_store()
    # No server-side copy on the ObjectStore protocol: re-put the bytes already read. KMS key ref is
    # still None until UPLOADS-07 (mirrors service._resolve_kms_key_ref).
    await store.put(released_key, data, content_type=detected_mime, kms_key_id=None)

    await repo.insert_stored_file(
        conn,
        {
            "id": file_id,
            "tenant_id": session["tenant_id"],
            "project_id": session["project_id"],
            "uploaded_by": session["requested_by"],
            "scan_status": "clean",
            "preview_status": "none",
            "detected_mime": detected_mime,
            "size_bytes": len(data),
            "sha256": sha256,
            "storage_key": released_key,
            "source": "upload",
            "filename": session["declared_filename"],
        },
    )
    await repo.set_released(conn, session["id"], file_id)
    await emit(
        conn,
        UPLOAD_COMPLETED,
        1,
        Aggregate("upload_session", session["id"]),
        {
            "sessionId": session["id"],
            "fileId": file_id,
            "projectId": session["project_id"],
            "detectedMime": detected_mime,
            "sizeBytes": len(data),
            "sha256": sha256,
        },
    )
    # Drop the quarantine copy now that the clean object is stored. The object store is not part of
    # the transaction; the rare window (a concurrent cancel rolling back the release after this
    # delete) is backstopped by the OPS-06 quarantine lifecycle rule.
    await store.delete(ObjectKey(session["quarantine_key"]))
    return f"released:{file_id}"


async def _reject(conn: AsyncConnection, session: repo.Row, reason: str) -> str:
    """Reject the session, emit ``upload.rejected`` and keep the quarantine object for review."""
    await repo.set_status(conn, session["id"], "rejected", reject_reason=reason)
    await emit(
        conn,
        UPLOAD_REJECTED,
        1,
        Aggregate("upload_session", session["id"]),
        {
            "sessionId": session["id"],
            "projectId": session["project_id"],
            "reason": reason,
        },
    )
    return f"rejected:{reason}"
