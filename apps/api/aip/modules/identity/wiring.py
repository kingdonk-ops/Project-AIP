"""How ``aip.main`` installs IDENTITY-03 sessions on the app.

``install_sessions(app, ...)`` adds, inside the request-id middleware and outside the request
context middleware: ``CsrfMiddleware`` then ``SessionMiddleware``. It also registers the 401
``SESSION_EXPIRED`` handler (both cookies of the presented audience cleared, IDENTITY-10) and wires
revocation: the Redis cache purge
after commit and the Keycloak revocation job. It returns the ``PrincipalResolver`` the app should
use: the session, with the test header stub as fallback only under ``AIP_ENV=test`` +
``AUTH_TEST_STUB=1``.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aip.modules.identity import jobs, sessions
from aip.modules.identity.csrf import CsrfMiddleware
from aip.modules.identity.principal import PrincipalResolver, SessionExpiredError
from aip.modules.identity.session_store import (
    RedisSessionCache,
    SessionCache,
    SessionMiddleware,
    SessionPrincipalResolver,
    SessionStore,
    presented_audience,
)
from aip.modules.identity.settings import portal_origin

__all__ = ["add_session_middleware", "install_session_errors", "session_resolver"]


def _session_expired_response() -> JSONResponse:
    response = JSONResponse(
        {"detail": {"code": "SESSION_EXPIRED", "message": "your session has ended"}},
        status_code=401,
    )
    sessions.clear_session_cookies(response, audience=presented_audience() or "app")
    response.headers["Cache-Control"] = "no-store"
    return response


def install_session_errors(app: FastAPI) -> None:
    @app.exception_handler(SessionExpiredError)
    async def session_expired(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: SessionExpiredError
    ) -> JSONResponse:
        return _session_expired_response()


def session_resolver(fallback: PrincipalResolver | None) -> SessionPrincipalResolver:
    return SessionPrincipalResolver(fallback)


def add_session_middleware(
    app: FastAPI, *, store: SessionStore | None = None, resolve_sessions: bool = True
) -> SessionStore:
    """Add CSRF and (unless ``resolve_sessions`` is False) session middleware; CSRF is always added.

    Call before the request-id middleware is added.
    """
    if store is None:
        redis_url = os.environ.get("REDIS_URL")
        cache: SessionCache | None = RedisSessionCache.from_url(redis_url) if redis_url else None
        store = SessionStore(cache)
    sessions.on_revoked(purge=store.cache.delete, enqueue=jobs.enqueue_keycloak_revocation)
    app.state.identity_session_store = store
    if resolve_sessions:
        app.add_middleware(SessionMiddleware, store=store)
    app.add_middleware(
        CsrfMiddleware,
        app_origin=os.environ.get("APP_ORIGIN", "http://localhost:8080"),
        portal_origin=portal_origin(),
    )

    return store
