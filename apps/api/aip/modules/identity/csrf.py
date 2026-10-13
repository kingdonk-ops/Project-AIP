"""CSRF protection for cookie-authenticated requests (IDENTITY-03).

Pure ASGI middleware. For POST, PUT, PATCH and DELETE under ``/api/`` from a browser holding the
session cookie, ``Origin`` must equal ``APP_ORIGIN`` and ``X-CSRF-Token`` must equal the
``__Host-aip_csrf`` cookie (``hmac.compare_digest``); otherwise 403 ``CSRF_FAILED``.

- ``POST /api/v1/auth/login/start`` is checked for ``Origin`` only (no session exists yet); a
  request without ``Origin`` is not a browser form post and passes.
- ``POST /api/v1/auth/oidc/backchannel-logout`` is exempt: server to server, authenticated by
  the signed logout token.
- Bearer-token requests (IDENTITY-06 API clients) without the session cookie are exempt: no
  ambient credential. With the cookie present the CSRF check still applies.
- A request without the session cookie carries no ambient credential, so there is nothing to
  forge; the route's own authentication still applies.
"""

from __future__ import annotations

import hmac
from http.cookies import CookieError, SimpleCookie
from typing import Final

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from aip.modules.identity.sessions import CSRF_COOKIE, SID_COOKIE

__all__ = ["CSRF_HEADER", "CsrfMiddleware", "csrf_ok"]

CSRF_HEADER: Final = "x-csrf-token"
UNSAFE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOGIN_START: Final = "/api/v1/auth/login/start"
BACKCHANNEL_LOGOUT: Final = "/api/v1/auth/oidc/backchannel-logout"


def _cookies(headers: Headers) -> dict[str, str]:
    raw = headers.get("cookie")
    if not raw:
        return {}
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(raw)
    except CookieError:
        return {}
    return {name: morsel.value for name, morsel in jar.items()}


def csrf_ok(method: str, path: str, headers: Headers, app_origin: str) -> bool:
    """True when the request may proceed (see the module docstring for the rules)."""
    if method.upper() not in UNSAFE_METHODS or not path.startswith("/api/"):
        return True
    if path == BACKCHANNEL_LOGOUT:
        return True
    origin = headers.get("origin")
    if path == LOGIN_START:
        return origin is None or origin == app_origin
    cookies = _cookies(headers)
    if SID_COOKIE not in cookies:
        return True  # no ambient credential (anonymous, or a Bearer API client)
    expected = cookies.get(CSRF_COOKIE, "")
    sent = headers.get(CSRF_HEADER, "")
    return (
        origin == app_origin
        and bool(expected)
        and hmac.compare_digest(sent.encode(), expected.encode())
    )


class CsrfMiddleware:
    def __init__(self, app: ASGIApp, *, app_origin: str) -> None:
        self.app = app
        self.app_origin = app_origin.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not csrf_ok(
            scope["method"], scope["path"], Headers(scope=scope), self.app_origin
        ):
            response = JSONResponse(
                {"detail": {"code": "CSRF_FAILED", "message": "request origin not verified"}},
                status_code=403,
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
