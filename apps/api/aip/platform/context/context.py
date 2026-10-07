"""The request context: tenant, project, actor and asset scope for the current unit of work.

One ``RequestContext`` lives in a module-level ``ContextVar``. Every service, repository, event
writer and job reads it with ``get_context()``; ``with_tenant(ctx)`` (ADR 0002) consumes it to set
``app.tenant_id`` for RLS. Because it is a ``ContextVar`` it follows ``await``, ``asyncio.gather``,
``asyncio.create_task``, ``loop.call_later`` and ``anyio.to_thread.run_sync`` (each copies the
current context when work is scheduled).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType
from uuid import UUID

__all__ = [
    "ContextMissingError",
    "RequestContext",
    "get_context",
    "run_with_context",
    "use_context",
]

# An ltree path: dot-separated labels of letters, digits, underscore and hyphen (PostgreSQL 16+).
_LTREE_PATH = re.compile(r"^[A-Za-z0-9_-]{1,1000}(\.[A-Za-z0-9_-]{1,1000})*$")


class ContextMissingError(LookupError):
    """Raised when code that needs a tenant context runs outside one."""


@dataclass(frozen=True, slots=True)
class RequestContext:
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
