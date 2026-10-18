"""API edge hardening (SECURITY-11 Part B, review 11 M2).

ADR 0026 routes ``/api/*`` from the ALB straight to the API, past the web nginx, so the API sets
its own edge limits:

- :class:`BodySizeLimitMiddleware` answers 413 to a request body over :data:`MAX_BODY_BYTES`. A
  declared ``Content-Length`` over the cap is refused before anything is read; a chunked (or
  understated) body is counted as it streams and refused at the first chunk past the cap, so it is
  never buffered whole. Files never pass through the API (presigned POST to the object store), so
  1 MiB is plenty for JSON.
- :class:`SecurityHeadersMiddleware` adds :data:`SECURITY_HEADERS` to every HTTP response (any
  status, any route), keeping a value a route set itself.
"""

from __future__ import annotations

from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "MAX_BODY_BYTES",
    "SECURITY_HEADERS",
    "BodySizeLimitMiddleware",
    "BodyTooLarge",
    "SecurityHeadersMiddleware",
]

MAX_BODY_BYTES: Final = 1024 * 1024

# JSON responses never need framing or sniffing; HSTS matches the web nginx (two years, subdomains).
SECURITY_HEADERS: Final[dict[str, str]] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}

_TOO_LARGE: Final = "request body too large"


class BodyTooLarge(HTTPException):
    """Raised from ``receive`` once the body passes the cap.

    An ``HTTPException`` so FastAPI's body parsing re-raises it (it turns other exceptions into
    400) and the exception middleware answers 413; :class:`BodySizeLimitMiddleware` also catches it
    for a route that streams the body itself.
    """

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=_TOO_LARGE)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                too_large = int(declared) > self.max_bytes
            except ValueError:
                too_large = False  # the server rejects a malformed length before the app
            if too_large:
                await _too_large(scope, receive, send)
                return

        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge:
            if started:
                raise
            await _too_large(scope, receive, send)


async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
    headers = {"Connection": "close"}
    response = JSONResponse({"detail": _TOO_LARGE}, status_code=413, headers=headers)
    await response(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
