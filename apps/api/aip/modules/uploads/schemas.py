"""Pydantic request/response models for upload sessions (UPLOADS-01).

JSON is camelCase (``declaredMime``, ``sizeBytes``, ``clientRequestId``). ``filename`` is
display-only: it is stored and echoed but never used to derive the type, key or path, so a value
like ``../../etc/passwd.jpg`` is accepted and simply travels as a label. The declared MIME and size
are checked against the platform limits in the service (not here), so the exact refusal — 400, 413
or 415 — is a stable domain code rather than a 422 schema error.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = [
    "FileDownloadUrl",
    "SessionCreate",
    "SessionCreated",
    "SessionStatus",
    "UploadErrorBody",
]

# S3's single-object ceiling (5 TiB). Larger declared sizes are a schema error; the single-part
# vs multipart cut (100 MiB) is a domain decision made in the service (413 USE_MULTIPART).
_MAX_DECLARED_SIZE = 5 * 1024**4


def _lower(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


# A minimal, safe MIME token: ``type/subtype`` with the characters RFC 6838 allows in each part.
_MIME_TOKEN = r"[a-z0-9][a-z0-9!#$&^_.+-]*"
DeclaredMime = Annotated[
    str,
    BeforeValidator(_lower),
    Field(min_length=3, max_length=255, pattern=rf"^{_MIME_TOKEN}/{_MIME_TOKEN}$"),
]
# Display-only; slashes and dots are fine because it is never used as a path.
Filename = Annotated[str, Field(min_length=1, max_length=255)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="ignore"
    )


class SessionCreate(_Model):
    project_id: UUID
    filename: Filename
    declared_mime: DeclaredMime
    size_bytes: int = Field(ge=0, le=_MAX_DECLARED_SIZE)
    sha256: Sha256 | None = None
    client_request_id: UUID | None = None


class SessionCreated(_Out):
    session_id: UUID
    url: str
    fields: dict[str, str]
    expires_at: datetime


class SessionStatus(_Out):
    status: str
    reject_reason: str | None = None
    # The released, clean stored file; set once ``status`` is ``released`` (UPLOADS-08).
    file_id: UUID | None = None


class FileDownloadUrl(_Out):
    """A short-lived presigned GET for a released (clean) file."""

    url: str
    expires_in_s: int


class UploadErrorBody(_Out):
    """A domain error: a stable ``code`` (``UNSUPPORTED_TYPE``, ``USE_MULTIPART``, ...)."""

    code: str
