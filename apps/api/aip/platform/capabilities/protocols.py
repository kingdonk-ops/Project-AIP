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


@dataclass(frozen=True)
class PresignedPost:
    """A presigned browser POST (RFC 1867 form upload): the form ``url`` and the ``fields`` the
    client must send verbatim. The signed policy (built by the caller as ``conditions``) pins the
    key, the content length and the content type, so the app is never in the byte path (UPLOADS-01).
    """

    url: str
    fields: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class ObjectHead:
    """The metadata of a stored object, from a ``head`` request (UPLOADS-01 confirm step)."""

    size_bytes: int
    content_type: str | None = None
    sse_kms_key_id: str | None = None


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

    async def head(self, key: ObjectKey) -> ObjectHead:
        """Return the object's metadata. Raises ``ObjectNotFoundError`` when there is none."""
        ...

    async def presign_put(
        self, key: ObjectKey, *, expires_s: int, kms_key_id: str | None = None
    ) -> PresignedRequest: ...

    async def presign_get(self, key: ObjectKey, *, expires_s: int) -> PresignedRequest: ...

    async def presign_post(
        self,
        key: ObjectKey,
        *,
        expires_s: int,
        fields: Mapping[str, str] | None = None,
        conditions: Sequence[object] | None = None,
    ) -> PresignedPost:
        """Presign a browser POST to ``key``.

        ``fields`` are form fields echoed back to the client; ``conditions`` is the S3 POST policy
        the server signs (the caller builds it, e.g. ``["content-length-range", 1, n]`` and
        ``["eq", "$Content-Type", mime]``). The key is always pinned to ``key``. Both adapters
        enforce ``1 <= expires_s <= 604800``.
        """
        ...

    async def delete(self, key: ObjectKey) -> None:
        """Delete the object. Deleting a missing key is not an error."""
        ...


@dataclass(frozen=True)
class PageOptions:
    """Paper size, orientation and margins for one PDF (REPORTS-02), all in millimetres.

    ``paper_width_mm`` x ``paper_height_mm`` is the portrait sheet (A4 is 210 x 297, A3 is
    297 x 420); ``landscape`` turns it.
    """

    paper_width_mm: float
    paper_height_mm: float
    landscape: bool
    margin_top_mm: float
    margin_right_mm: float
    margin_bottom_mm: float
    margin_left_mm: float


@runtime_checkable
class PdfRenderer(Protocol):
    """HTML to PDF (Gotenberg/Chromium)."""

    async def render_html(
        self,
        html: str,
        *,
        assets: Mapping[str, bytes] | None = None,
        page: PageOptions | None = None,
    ) -> bytes:
        """Render ``html`` (as ``index.html``) with optional sibling assets by file name, on the
        paper ``page`` describes (the renderer's own defaults when ``None``).

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
    "ObjectHead",
    "ObjectStore",
    "Ocr",
    "OcrResult",
    "PageOptions",
    "PdfRenderer",
    "PresignedPost",
    "PresignedRequest",
    "SealResult",
    "Sealer",
]


@dataclass(frozen=True)
class EmailMessage:
    """One transactional email (STACK-06). No attachments yet.

    ``tenant_id`` tags the message for delivery reporting (an SES message tag); ``idempotency_key``
    makes a repeated request queue one send. Neither the addresses nor the body are ever logged.
    """

    sender: str
    to: Sequence[str]
    subject: str
    text: str
    tenant_id: str
    idempotency_key: str
    html: str | None = None


@runtime_checkable
class Mailer(Protocol):
    """Sends transactional email: SMTP on Coolify and in dev (Mailpit), Amazon SES on AWS.

    Call it only from a worker job (``ops`` ``send_email``), never inside a request.
    """

    async def send(self, message: EmailMessage) -> str:
        """Send ``message``; return the provider's message id. Raises ``MailError``."""
        ...
