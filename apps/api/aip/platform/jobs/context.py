"""``tenant_job``: run a job handler inside its payload's request context (ARCH-04, ADR 0003).

Job payloads carry ``tenant_id`` and optionally ``actor_id``, ``project_id`` and ``request_id``
(so the job's audit and events correlate with the request that enqueued it). The kwargs are
passed through to the handler unchanged.

A payload ``request_id`` is kept only when it matches ``SAFE_REQUEST_ID`` (the same rule the
HTTP middleware applies); otherwise the job gets a fresh ``job-<uuid4hex>`` id.

Jobs never inherit asset access: the job context's ``asset_path_scope`` is empty, which means
NO asset access (not unrestricted). A job that needs assets must be granted them explicitly.

``tenant_job`` never switches tenants: if a context is already set (e.g. a job invoked inline
from a request) and its tenant differs from the payload's, ``TenantMismatchError`` is raised
before the handler runs.
"""

from __future__ import annotations

import functools
import inspect
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast, overload
from uuid import UUID

from aip.platform.context.context import (
    SAFE_REQUEST_ID,
    ContextMissingError,
    RequestContext,
    get_context,
    use_context,
)

__all__ = ["TenantMismatchError", "context_from_payload", "tenant_job"]


class TenantMismatchError(ContextMissingError):
    """A job's payload tenant differs from the tenant context already set for this task."""


def _as_uuid(value: object, key: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            pass
    raise ContextMissingError(f"job payload {key!r} is not a UUID")


def _job_request_id(raw: object) -> str:
    if isinstance(raw, str) and SAFE_REQUEST_ID.fullmatch(raw):
        return raw
    return f"job-{uuid.uuid4().hex}"


def context_from_payload(payload: Mapping[str, Any]) -> RequestContext:
    """Build the context for a job, or raise ``ContextMissingError`` if ``tenant_id`` is absent."""
    raw_tenant = payload.get("tenant_id")
    if raw_tenant in (None, ""):
        raise ContextMissingError("job payload has no tenant_id")
    raw_actor = payload.get("actor_id")
    raw_project = payload.get("project_id")
    return RequestContext(
        tenant_id=_as_uuid(raw_tenant, "tenant_id"),
        actor_id=None if raw_actor in (None, "") else _as_uuid(raw_actor, "actor_id"),
        project_id=None if raw_project in (None, "") else _as_uuid(raw_project, "project_id"),
        request_id=_job_request_id(payload.get("request_id")),
    )


def _job_context(payload: Mapping[str, Any]) -> RequestContext:
    ctx = context_from_payload(payload)
    try:
        current = get_context()
    except ContextMissingError:
        return ctx
    if current.tenant_id != ctx.tenant_id:
        raise TenantMismatchError(
            "job payload tenant_id differs from the tenant context already set; refusing to switch"
        )
    return ctx


@overload
def tenant_job[R](fn: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]: ...
@overload
def tenant_job[R](fn: Callable[..., R]) -> Callable[..., R]: ...


def tenant_job(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a job handler (sync or async) so it runs inside its payload's tenant context."""
    if inspect.iscoroutinefunction(fn):
        async_fn = cast(Callable[..., Awaitable[Any]], fn)

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _job_context(kwargs)
            async with use_context(ctx):
                return await async_fn(*args, **kwargs)

        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = _job_context(kwargs)
        with use_context(ctx):
            return fn(*args, **kwargs)

    return sync_wrapper
