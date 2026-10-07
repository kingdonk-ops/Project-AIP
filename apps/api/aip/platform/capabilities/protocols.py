"""Capability interfaces (STACK-02).

Calling code depends only on these protocols. Which library implements one is chosen by an
environment variable and one adapter file (see ``aip.platform.capabilities``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from aip.platform.capabilities.keys import ObjectKey


@dataclass(frozen=True)
class PresignedRequest:
    """A presigned URL plus the headers the client must send with it (they are signed)."""

    method: Literal["GET", "PUT"]
    url: str
    headers: Mapping[str, str] = field(default_factory=dict[str, str])


@runtime_checkable
class ObjectStore(Protocol):
    """Blob storage: AWS S3 in production, RustFS/MinIO on Coolify and in dev.

    ``kms_key_id`` is the tenant's KMS key (ADR 0006). When given, puts and presigned PUTs request
    SSE-KMS with that key. UPLOADS-01 makes it mandatory for tenant data.
    """

    async def put(
        self, key: ObjectKey, body: bytes, *, content_type: str, kms_key_id: str | None = None
    ) -> None: ...

    async def get(self, key: ObjectKey) -> bytes:
        """Return the object's bytes. Raises ``ObjectNotFoundError`` when there is none."""
        ...

    async def presign_put(
        self, key: ObjectKey, *, expires_s: int, kms_key_id: str | None = None
    ) -> PresignedRequest: ...

    async def presign_get(self, key: ObjectKey, *, expires_s: int) -> PresignedRequest: ...

    async def delete(self, key: ObjectKey) -> None:
        """Delete the object. Deleting a missing key is not an error."""
        ...


@runtime_checkable
class PdfRenderer(Protocol):
    """HTML to PDF (Gotenberg/Chromium)."""

    async def render_html(self, html: str, *, assets: Mapping[str, bytes] | None = None) -> bytes:
        """Render ``html`` (as ``index.html``) with optional sibling assets by file name.

        Raises ``RenderTimeoutError``, ``RenderTooLargeError`` or ``RenderError``.
        """
        ...


@dataclass(frozen=True)
class SealResult:
    key: ObjectKey
    sha256: str


@runtime_checkable
class Sealer(Protocol):
    """PAdES sealing of a stored PDF. Implementations dispatch a sandbox job (ADR 0003)."""

    async def seal_pdf(
        self, source: ObjectKey, *, dest: ObjectKey, reason: str, kms_key_id: str | None = None
    ) -> SealResult: ...


@dataclass(frozen=True)
class OcrResult:
    text: str
    pages: Sequence[str]


@runtime_checkable
class Ocr(Protocol):
    """Text extraction from a stored image or PDF. Implementations dispatch a sandbox job."""

    async def extract_text(
        self, source: ObjectKey, *, languages: Sequence[str] = ("eng",)
    ) -> OcrResult: ...


@runtime_checkable
class IdentityProvider(Protocol):
    """The Keycloak admin and broker calls the backend makes (ADR 0005).

    Browsers never hold Keycloak tokens. The backend creates invited users with required actions,
    ends Keycloak sessions on logout or revocation, and disables users on deprovisioning.
    """

    async def create_user(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        required_actions: Sequence[str],
        organization_id: str | None = None,
    ) -> str:
        """Create the user and send the required-actions email. Returns the Keycloak user id."""
        ...

    async def end_sessions(self, user_id: str) -> None: ...

    async def disable_user(self, user_id: str) -> None: ...

    async def idp_alias_for_email(self, email: str) -> str | None:
        """The brokered IdP alias for this email's domain, or ``None`` for local login."""
        ...


__all__ = [
    "IdentityProvider",
    "ObjectStore",
    "Ocr",
    "OcrResult",
    "PdfRenderer",
    "PresignedRequest",
    "SealResult",
    "Sealer",
]
