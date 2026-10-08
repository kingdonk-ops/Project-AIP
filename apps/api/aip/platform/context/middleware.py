"""Pure ASGI middleware that builds the ``RequestContext`` for each HTTP request.

It is deliberately not a ``BaseHTTPMiddleware``: that runs the endpoint in a separate task, so a
``ContextVar`` set here would not reach it. Here the downstream app is awaited in the same task,
inside ``use_context``.

Per request:

1. reuse the request id the outer ``RequestIdMiddleware`` (OPS-04) already set; standalone, read
   ``X-Request-Id`` when it is safe, otherwise generate a UUIDv7; echo it on every response;
2. ask the injected ``PrincipalResolver`` for the verified principal (ADR 0005);
3. if ``X-Project-Id`` is sent, require a valid UUID (400), an authenticated caller (401) and
   membership per the injected ``ProjectMembershipResolver`` (403); if either resolver raises,
   the error is logged with the request id and the request is rejected with 500 (still
   carrying ``X-Request-Id``);
4. run the app inside ``use_context``. With no principal, no context is set: anything that
   calls ``get_context()`` then raises ``ContextMissingError``, which the app maps to 401.
"""

from __future__ import annotations

import logging
from uuid import UUID

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aip.platform.context.context import (
    SAFE_REQUEST_ID,
    RequestContext,
    current_request_id,
    new_request_id,
    use_context,
)
from aip.platform.context.resolvers import Principal, PrincipalResolver, ProjectMembershipResolver

__all__ = ["REQUEST_ID_HEADER", "RequestContextMiddleware", "request_id_from"]

REQUEST_ID_HEADER = "x-request-id"
PROJECT_ID_HEADER = "x-project-id"

logger = logging.getLogger(__name__)


def request_id_from(headers: Headers) -> str:
    """The safe ``X-Request-Id`` sent by the caller, or a new UUIDv7."""
    given = headers.get(REQUEST_ID_HEADER)
    if given is not None and SAFE_REQUEST_ID.fullmatch(given):
        return given
    return new_request_id()


class RequestContextMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        principal_resolver: PrincipalResolver,
        membership_resolver: ProjectMembershipResolver,
    ) -> None:
        self.app = app
        self.principal_resolver = principal_resolver
        self.membership_resolver = membership_resolver

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = current_request_id() or request_id_from(headers)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        async def reject(status_code: int, detail: str) -> None:
            response = JSONResponse({"detail": detail}, status_code=status_code)
            await response(scope, receive, send_with_request_id)

        project_id: UUID | None = None
        raw_project = headers.get(PROJECT_ID_HEADER)
        if raw_project is not None:
            try:
                project_id = UUID(raw_project)
            except ValueError:
                await reject(400, "X-Project-Id must be a UUID")
                return

        principal: Principal | None
        try:
            principal = await self.principal_resolver.resolve(headers)
        except Exception:
            logger.exception("principal resolver failed (request_id=%s)", request_id)
            await reject(500, "Internal Server Error")
            return
        if principal is None:
            if project_id is not None:
                await reject(401, "Not authenticated")
                return
            await self.app(scope, receive, send_with_request_id)
            return

        if project_id is not None:
            try:
                is_member = await self.membership_resolver.is_member(
                    tenant_id=principal.tenant_id,
                    actor_id=principal.actor_id,
                    project_id=project_id,
                )
            except Exception:
                logger.exception("membership resolver failed (request_id=%s)", request_id)
                await reject(500, "Internal Server Error")
                return
            if not is_member:
                await reject(403, "Not a member of this project")
                return

        ctx = RequestContext(
            tenant_id=principal.tenant_id,
            project_id=project_id,
            actor_id=principal.actor_id,
            asset_path_scope=principal.asset_path_scope,
            request_id=request_id,
        )
        async with use_context(ctx):
            await self.app(scope, receive, send_with_request_id)
