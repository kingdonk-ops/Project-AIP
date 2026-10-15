"""Business logic for upload sessions (UPLOADS-01).

A session is the only way in. The server issues a short-lived presigned POST into a tenant-prefixed
quarantine key, and the signed policy — not the app — enforces the key, the content length and the
content type, so the bytes never pass through the API. The quarantine key carries no user-supplied
text: it is ``tenant/<tenantId>/quarantine/<token>`` where ``token`` is 128 random bits (base64url),
built through the one object-key builder (``tenant_key``). ``filename`` is display-only.

Each operation runs in one ``with_tenant`` transaction; rows of another tenant are invisible under
RLS and surface as 404, never 403.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.uploads import repository as repo
from aip.modules.uploads.platform_limits import PRESIGN_TTL_S, classify_declared
from aip.modules.uploads.schemas import SessionCreate, SessionCreated, SessionStatus
from aip.platform.capabilities import ObjectNotFoundError, PresignedPost, get_object_store
from aip.platform.capabilities.keys import ObjectKey, tenant_key
from aip.platform.context import RequestContext, get_context, new_request_id
from aip.platform.db.errors import NotFoundError
from aip.platform.db.session import with_tenant
from aip.platform.http import DomainError

__all__ = ["AdminCheck", "UploadSessionService", "build_post_policy", "quarantine_token"]

# Decides whether the caller holds ``uploads.admin`` on a session's project (supplied by the route).
type AdminCheck = Callable[[UUID], Awaitable[bool]]

# A refusal code from the platform-limit check -> the HTTP status the API returns for it.
_STATUS_FOR: Final[Mapping[str, int]] = {
    "INVALID_SIZE": 400,
    "UNSUPPORTED_TYPE": 415,
    "USE_MULTIPART": 413,
}
_MAX_OPEN_SESSIONS: Final = 20
_SSE_HEADER: Final = "x-amz-server-side-encryption"
_SSE_KMS_KEY_HEADER: Final = "x-amz-server-side-encryption-aws-kms-key-id"
_SSE_CONTEXT_HEADER: Final = "x-amz-server-side-encryption-context"


def quarantine_token() -> str:
    """128 random bits as 22 base64url characters (no padding): the only variable part of a key."""
    return base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")


def _encryption_context(tenant_id: UUID) -> str:
    """The SSE-KMS encryption context (ADR 0006): base64 of a compact JSON object."""
    raw = json.dumps({"tenant_id": str(tenant_id)}, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def build_post_policy(
    declared_mime: str,
    size_bytes: int,
    *,
    kms_key_id: str | None = None,
    tenant_id: UUID | None = None,
) -> tuple[dict[str, str], list[object]]:
    """Return the ``(fields, conditions)`` for the presigned POST.

    The conditions pin the content length to ``[1, size_bytes]`` and the ``Content-Type`` to
    ``declared_mime``; ``generate_presigned_post`` pins the key itself. When ``kms_key_id`` is set
    (ADR 0006), SSE-KMS with the tenant encryption context is required too, so an upload that omits
    or changes those headers is rejected by the store.
    """
    fields: dict[str, str] = {"Content-Type": declared_mime}
    conditions: list[object] = [
        ["content-length-range", 1, size_bytes],
        ["eq", "$Content-Type", declared_mime],
    ]
    if kms_key_id is not None:
        context = _encryption_context(tenant_id) if tenant_id is not None else ""
        fields[_SSE_HEADER] = "aws:kms"
        fields[_SSE_KMS_KEY_HEADER] = kms_key_id
        conditions.append(["eq", f"${_SSE_HEADER}", "aws:kms"])
        conditions.append(["eq", f"${_SSE_KMS_KEY_HEADER}", kms_key_id])
        if context:
            fields[_SSE_CONTEXT_HEADER] = context
            conditions.append(["eq", f"${_SSE_CONTEXT_HEADER}", context])
    return fields, conditions


async def _resolve_kms_key_ref(conn: AsyncConnection) -> str | None:
    """The tenant's KMS key reference for SSE-KMS (ADR 0006), or ``None`` when none is provisioned.

    TENANCY-05 provisions the per-tenant KMS key, and the key reference is not yet exposed through
    the tenancy published interface (``TenantView`` carries no key references) — reaching into the
    ``tenants`` table here would break the module boundary. Until that seam exists, this returns
    ``None`` and the presign omits the SSE-KMS conditions, so uploads still enforce the key, size
    and content-type. Wiring it is tracked as UPLOADS-07.
    """
    return None


def _require_actor(ctx: RequestContext) -> UUID:
    if ctx.actor_id is None:  # the route is authenticated(), so this should not happen
        raise NotFoundError("no actor in context")
    return ctx.actor_id


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


class UploadSessionService:
    async def create_session(self, body: SessionCreate) -> SessionCreated:
        """Create a session and presign the quarantine POST. The caller has already passed the
        ``uploads.create`` policy check on ``body.project_id`` (enforced in the route)."""
        code = classify_declared(body.declared_mime, body.size_bytes)
        if code is not None:
            raise DomainError(_STATUS_FOR[code], code)

        ctx = get_context()
        actor = _require_actor(ctx)
        async with _tx() as conn:
            if body.client_request_id is not None:
                existing = await repo.find_by_client_request_id(conn, actor, body.client_request_id)
                if existing is not None:
                    return await self._reissue(conn, existing)

            if await repo.count_active_for_user(conn, actor) >= _MAX_OPEN_SESSIONS:
                raise DomainError(429, "TOO_MANY_SESSIONS")

            kms_key_id = await _resolve_kms_key_ref(conn)
            key = tenant_key(ctx.tenant_id, "quarantine", quarantine_token())
            now = datetime.now(UTC)
            expires_at = now + timedelta(seconds=PRESIGN_TTL_S)
            row = await repo.insert_session(
                conn,
                {
                    "id": UUID(new_request_id()),
                    "tenant_id": ctx.tenant_id,
                    "project_id": body.project_id,
                    "requested_by": actor,
                    "declared_filename": body.filename,
                    "declared_mime": body.declared_mime,
                    "declared_size_bytes": body.size_bytes,
                    "mode": "single",
                    "quarantine_key": key,
                    "client_file_hash": body.sha256,
                    "status": "requested",
                    "client_request_id": body.client_request_id,
                    "expires_at": expires_at,
                },
            )
            post = await self._presign(
                key,
                declared_mime=body.declared_mime,
                size_bytes=body.size_bytes,
                kms_key_id=kms_key_id,
                tenant_id=ctx.tenant_id,
            )
        return SessionCreated(
            session_id=row["id"], url=post.url, fields=dict(post.fields), expires_at=expires_at
        )

    async def _reissue(self, conn: AsyncConnection, existing: repo.Row) -> SessionCreated:
        """Idempotent replay of a ``clientRequestId``: same row and key, a fresh presign and TTL.

        The existing session's own declared type and size are authoritative, so a replay can never
        loosen the signed policy. A session already past the upload stage cannot be reissued.
        """
        if existing["status"] not in repo.OPEN_STATUSES:
            raise DomainError(409, "SESSION_NOT_OPEN")
        key = ObjectKey(existing["quarantine_key"])
        expires_at = datetime.now(UTC) + timedelta(seconds=PRESIGN_TTL_S)
        await repo.touch_expiry(conn, existing["id"], expires_at)
        kms_key_id = await _resolve_kms_key_ref(conn)
        post = await self._presign(
            key,
            declared_mime=existing["declared_mime"],
            size_bytes=int(existing["declared_size_bytes"]),
            kms_key_id=kms_key_id,
            tenant_id=existing["tenant_id"],
        )
        return SessionCreated(
            session_id=existing["id"], url=post.url, fields=dict(post.fields), expires_at=expires_at
        )

    @staticmethod
    async def _presign(
        key: ObjectKey,
        *,
        declared_mime: str,
        size_bytes: int,
        kms_key_id: str | None,
        tenant_id: UUID,
    ) -> PresignedPost:
        fields, conditions = build_post_policy(
            declared_mime, size_bytes, kms_key_id=kms_key_id, tenant_id=tenant_id
        )
        store = get_object_store()
        return await store.presign_post(
            key, expires_s=PRESIGN_TTL_S, fields=fields, conditions=conditions
        )

    async def confirm(self, session_id: UUID) -> SessionStatus:
        """Confirm the upload landed. Only the requester may call it; anyone else gets 404."""
        ctx = get_context()
        actor = _require_actor(ctx)
        async with _tx() as conn:
            session = await repo.get_for_requester(conn, session_id, actor)
            if session is None:
                raise NotFoundError(f"upload session {session_id} not found")
            if session["status"] not in repo.OPEN_STATUSES:
                raise DomainError(409, "SESSION_NOT_OPEN")
            store = get_object_store()
            try:
                head = await store.head(ObjectKey(session["quarantine_key"]))
            except ObjectNotFoundError:
                raise DomainError(409, "OBJECT_MISSING") from None
            if head.size_bytes > int(session["declared_size_bytes"]):
                raise DomainError(422, "SIZE_MISMATCH")
            row = await repo.set_status(conn, session_id, "uploaded")
        return SessionStatus(status=row["status"], reject_reason=row["reject_reason"])

    async def get_status(self, session_id: UUID, *, is_admin: AdminCheck) -> SessionStatus:
        """Return a session's status to its requester, or to a holder of ``uploads.admin`` in scope.

        Anyone else gets 404, so a session's existence is never leaked. ``is_admin`` is the route's
        policy check for ``uploads.admin`` against the session's own project scope, called only for
        a non-requester so a requester never needs the extra permission.
        """
        ctx = get_context()
        actor = _require_actor(ctx)
        async with _tx() as conn:
            session = await repo.get_session(conn, session_id)
            if session is None:
                raise NotFoundError(f"upload session {session_id} not found")
            if session["requested_by"] != actor and not await is_admin(session["project_id"]):
                raise NotFoundError(f"upload session {session_id} not found")
        return SessionStatus(status=session["status"], reject_reason=session["reject_reason"])

    async def expire_stale_sessions(self, now: datetime) -> int:
        """Mark ``requested`` sessions past their TTL as ``expired`` (scheduled by UPLOADS-02)."""
        async with _tx() as conn:
            return await repo.expire_stale(conn, now)
