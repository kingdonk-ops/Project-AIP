"""Server-side access to clean stored files (UPLOADS-08, ADR 0036 point 4).

Other modules never touch the uploads tables or the object store for a file: report_engine stores a
rendered PDF with ``store_generated_file``, and data_io, report_engine and the evidence links read a
file with ``get_stored_file`` / ``open_stored_file``. Every function runs on the caller's
``with_tenant`` connection and principal, so tenant RLS and the ACCESS-03 project scope decide what
is visible; a worker handler must already act as the ``system`` principal (as the scan runner does).

Only ``clean`` files are ever handed out. Another tenant's, a deleted or a not-yet-clean file look
exactly the same to a caller: ``None`` from ``get_stored_file``, ``StoredFileNotFound`` from
``open_stored_file``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.capabilities import ObjectNotFoundError, get_object_store
from aip.platform.capabilities.keys import ObjectKey, tenant_key

from . import repository as repo
from .pipeline.magic_bytes import HEAD_BYTES, check_magic_bytes
from .platform_limits import SINGLE_PART_MAX_BYTES, is_allowed_type

__all__ = [
    "StoredFileConflict",
    "StoredFileIntegrityError",
    "StoredFileNotFound",
    "StoredFileRef",
    "generated_file_id",
    "get_stored_file",
    "open_stored_file",
    "store_generated_file",
]

# Namespace of the deterministic id of a generated file (uuid5 of "<tenant>:<idempotency key>").
_GENERATED_NS: Final = UUID("6f1c2a52-5b8e-4d0e-9a51-0c8e0b7e0808")
_MAX_FILENAME: Final = 255
_MAX_LABEL: Final = 200
_CURRENT_TENANT = text("SELECT current_setting('app.tenant_id', true)")


@dataclass(frozen=True)
class StoredFileRef:
    """A clean stored file, as other modules see it. ``filename`` is display-only."""

    id: UUID
    project_id: UUID | None
    filename: str | None
    content_type: str
    size_bytes: int
    sha256: str
    source: str  # upload | generated
    purpose: str | None
    created_at: datetime


class StoredFileNotFound(LookupError):
    """No clean file with that id is visible to the caller (missing, another tenant's, deleted,
    out of the principal's project scope, or not yet clean)."""


class StoredFileIntegrityError(RuntimeError):
    """The stored object's bytes no longer match the row's size or sha256."""


class StoredFileConflict(RuntimeError):
    """An idempotency key was reused for different bytes (or for a file since deleted)."""


def generated_file_id(tenant_id: UUID, idempotency_key: str) -> UUID:
    """The stable id (and so object key) of the file a job stores under ``idempotency_key``."""
    return uuid5(_GENERATED_NS, f"{tenant_id}:{idempotency_key}")


def _ref(row: repo.Row) -> StoredFileRef:
    return StoredFileRef(
        id=row["id"],
        project_id=row["project_id"],
        filename=row["filename"],
        content_type=row["detected_mime"],
        size_bytes=int(row["size_bytes"]),
        sha256=row["sha256"],
        source=row["source"],
        purpose=row["purpose"],
        created_at=row["created_at"],
    )


async def get_stored_file(conn: AsyncConnection, file_id: UUID) -> StoredFileRef | None:
    """The clean file ``file_id`` if the caller may see it, else ``None``."""
    row = await repo.get_clean_stored_file(conn, file_id)
    return None if row is None else _ref(row)


async def open_stored_file(conn: AsyncConnection, file_id: UUID) -> bytes:
    """The bytes of the clean file ``file_id``, verified against the row's size and sha256."""
    row = await repo.get_clean_stored_file(conn, file_id)
    if row is None:
        raise StoredFileNotFound(f"file {file_id} not found")
    try:
        data = await get_object_store().get(ObjectKey(row["storage_key"]))
    except ObjectNotFoundError:
        raise StoredFileIntegrityError(f"file {file_id} has no stored object") from None
    if len(data) != int(row["size_bytes"]) or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise StoredFileIntegrityError(f"file {file_id} does not match its recorded hash")
    return data


def _check_label(name: str, value: str, max_len: int) -> None:
    if not value or len(value) > max_len:
        raise ValueError(f"{name} must be 1-{max_len} characters")


def _check_generated(data: bytes, content_type: str) -> None:
    """A worker bug, not user input, so a plain ``ValueError``: the type must be one an upload could
    have, and the bytes must be that type (the same magic-bytes check a scan runs)."""
    if not 0 < len(data) <= SINGLE_PART_MAX_BYTES:
        raise ValueError(f"generated file must be 1-{SINGLE_PART_MAX_BYTES} bytes")
    if not is_allowed_type(content_type):
        raise ValueError(f"content type {content_type!r} is not allowed")
    magic = check_magic_bytes(data[:HEAD_BYTES], content_type)
    if magic.outcome != "pass":
        raise ValueError(f"bytes are not {content_type}: {magic.detail}")


async def store_generated_file(
    conn: AsyncConnection,
    *,
    data: bytes,
    filename: str,
    content_type: str,
    purpose: str,
    idempotency_key: str,
    project_id: UUID | None = None,
    created_by: UUID | None = None,
) -> StoredFileRef:
    """Store a worker-made file as a clean ``stored_files`` row in the caller's transaction.

    The id is derived from the tenant and ``idempotency_key``, so a retried job writes the same
    object key: a rolled-back attempt leaves nothing the retry does not overwrite. A replay with the
    same bytes returns the stored file; different bytes raise ``StoredFileConflict``.
    """
    content_type = content_type.strip().lower()
    _check_label("filename", filename, _MAX_FILENAME)
    _check_label("purpose", purpose, _MAX_LABEL)
    _check_label("idempotency_key", idempotency_key, _MAX_LABEL)
    _check_generated(data, content_type)
    sha256 = hashlib.sha256(data).hexdigest()

    existing = await repo.find_stored_file_by_idempotency_key(conn, idempotency_key)
    if existing is not None:
        if existing["deleted_at"] is not None or existing["sha256"] != sha256:
            raise StoredFileConflict(f"idempotency key {idempotency_key!r} names another file")
        return _ref(existing)

    tenant_id = UUID(str((await conn.execute(_CURRENT_TENANT)).scalar_one()))
    file_id = generated_file_id(tenant_id, idempotency_key)
    key = tenant_key(tenant_id, "files", str(file_id))
    # KMS key ref is still None until UPLOADS-07 (mirrors the scan runner's release).
    await get_object_store().put(key, data, content_type=content_type, kms_key_id=None)
    row = await repo.insert_stored_file(
        conn,
        {
            "id": file_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "uploaded_by": created_by,
            "scan_status": "clean",
            "preview_status": "none",
            "detected_mime": content_type,
            "size_bytes": len(data),
            "sha256": sha256,
            "storage_key": key,
            "source": "generated",
            "filename": filename,
            "purpose": purpose,
            "idempotency_key": idempotency_key,
        },
    )
    return _ref(row)
