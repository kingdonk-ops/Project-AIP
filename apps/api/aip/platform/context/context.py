"""The request context: tenant, project, actor and asset scope for the current unit of work.

One ``RequestContext`` lives in a module-level ``ContextVar``. Every service, repository, event
writer and job reads it with ``get_context()``; ``with_tenant(ctx)`` (ADR 0002) consumes it to set
``app.tenant_id`` for RLS. Because it is a ``ContextVar`` it follows ``await``, ``asyncio.gather``,
``asyncio.create_task``, ``loop.call_later`` and ``anyio.to_thread.run_sync`` (each copies the
current context when work is scheduled).
"""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType
from uuid import UUID

__all__ = [
    "SAFE_REQUEST_ID",
    "ContextMissingError",
    "RequestContext",
    "current_request_id",
    "get_context",
    "new_request_id",
    "run_with_context",
    "set_request_id",
    "use_context",
]

# An ltree path: dot-separated labels of letters, digits, underscore and hyphen (PostgreSQL 16+).
_LTREE_PATH = re.compile(r"^[A-Za-z0-9_-]{1,1000}(\.[A-Za-z0-9_-]{1,1000})*$")

# A request id is accepted from outside (X-Request-Id header, job payload) only when it matches
# this: it cannot forge log lines (no whitespace/newlines) or bloat headers (max 128 chars).
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class ContextMissingError(LookupError):
    """Raised when code that needs a tenant context runs outside one."""


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Who is acting, for which tenant/project, and which assets they may touch.

    ``asset_path_scope`` lists the ltree asset paths (and their subtrees) the actor may access.
    An EMPTY ``asset_path_scope`` means NO asset access - it is never "unrestricted". Code that
    filters by asset must deny when the scope is empty, not skip the filter.
    """

    tenant_id: UUID
    request_id: str
    project_id: UUID | None = None
    actor_id: UUID | None = None
    asset_path_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("tenant_id must be a UUID")
        if not self.request_id:
            raise ValueError("request_id must not be empty")
        for path in self.asset_path_scope:
            if not _LTREE_PATH.fullmatch(path):
                raise ValueError(f"asset_path_scope entry is not an ltree path: {path!r}")


_current: ContextVar[RequestContext] = ContextVar("aip_request_context")

# The request id of the current HTTP request, set by the outermost middleware (OPS-04) before any
# principal is known, so unauthenticated requests and log lines carry it too.
_request_id: ContextVar[str | None] = ContextVar("aip_request_id", default=None)


def new_request_id() -> str:
    """A new UUIDv7 (RFC 9562): 48-bit Unix ms timestamp, then random bits; sorts by time."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & 0xFFFF_FFFF_FFFF) << 80 | rand
    value = (value & ~(0xF << 76)) | (0x7 << 76)  # version 7
    value = (value & ~(0x3 << 62)) | (0x2 << 62)  # RFC 4122 variant
    return str(uuid.UUID(int=value))


def current_request_id() -> str | None:
    """The current request id: the request context's, else the HTTP request's, else ``None``."""
    ctx = _current.get(None)
    if ctx is not None:
        return ctx.request_id
    return _request_id.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    """Set the request id for the current task; reset with ``reset_request_id(token)``."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_context() -> RequestContext:
    """Return the current context, or raise ``ContextMissingError`` outside a scope."""
    try:
        return _current.get()
    except LookupError:
        raise ContextMissingError("no request context is set for this task") from None


class use_context:  # noqa: N801 - reads as a function at call sites
    """Set ``ctx`` for a ``with`` / ``async with`` block, then restore the previous one."""

    __slots__ = ("_ctx", "_token")

    def __init__(self, ctx: RequestContext) -> None:
        self._ctx = ctx
        self._token: Token[RequestContext] | None = None

    def __enter__(self) -> RequestContext:
        if self._token is not None:
            raise RuntimeError("use_context is not re-entrant; create a new one")
        self._token = _current.set(self._ctx)
        return self._ctx

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        token, self._token = self._token, None
        if token is not None:
            _current.reset(token)

    async def __aenter__(self) -> RequestContext:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.__exit__(exc_type, exc, tb)

    def __repr__(self) -> str:
        return f"use_context({self._ctx!r})"


async def run_with_context[**P, R](
    ctx: RequestContext,
    fn: Callable[P, Awaitable[R]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Await ``fn(*args, **kwargs)`` inside ``use_context(ctx)``. For jobs and tests."""
    async with use_context(ctx):
        return await fn(*args, **kwargs)
