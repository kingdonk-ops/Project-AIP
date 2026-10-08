"""FastAPI dependency ``require_active_tenant`` (TENANCY-01 step 3, ADR 0005).

The tenant comes only from the verified principal that identity's resolver hands to the request
context middleware (ARCH-04): the session row for staff, field and portal users, the ES256 JWT
``tid`` for API clients. Never from a header, path or raw Keycloak claim.

Order, failing closed at each step:

1. no request context (no principal) -> 401 ``NOT_AUTHENTICATED``, before any query;
2. a tenant id that is not a non-nil UUID -> 401 ``TENANT_INVALID``, before any query (the
   middleware already rejects such principals; this is the second check);
3. load the tenant inside ``with_tenant(tenant_id)``: missing or soft-deleted -> 401
   ``TENANT_UNKNOWN``; not ``active`` -> 403 with the status code from ``service``;
4. for the rest of the request, the context also carries ``tenant_slug`` and ``region_code``.

Errors are ``HTTPException`` with ``detail = {"code", "message"}``; they never name the tenant.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from aip.modules.tenancy.schemas import TenantView
from aip.modules.tenancy.service import (
    TenantAccessError,
    TenantLoader,
    TenantService,
    resolve_active,
)
from aip.platform.context import ContextMissingError, get_context, use_context

__all__ = ["get_tenant_service", "parse_tenant_id", "require_active_tenant"]


def parse_tenant_id(raw: object) -> UUID:
    """``raw`` as a tenant UUID, or ``TenantAccessError`` (401) for anything else or nil."""
    value: UUID | None = None
    if isinstance(raw, UUID):
        value = raw
    elif isinstance(raw, str):
        try:
            value = UUID(raw)
        except ValueError:
            value = None
    if value is None or value.int == 0:
        raise TenantAccessError(401, "TENANT_INVALID", "not authenticated for a valid tenant")
    return value


def get_tenant_service(request: Request) -> TenantLoader:
    """The app's ``TenantService`` (tests override this dependency)."""
    service: TenantLoader | None = getattr(request.app.state, "tenancy_service", None)
    if service is None:
        service = TenantService()
        request.app.state.tenancy_service = service
    return service


def _http(exc: TenantAccessError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
    )


async def require_active_tenant(
    tenants: Annotated[TenantLoader, Depends(get_tenant_service)],
) -> AsyncIterator[TenantView]:
    """Yield the caller's active tenant; 401/403 otherwise (see the module docstring)."""
    try:
        ctx = get_context()
    except ContextMissingError:
        raise HTTPException(
            status_code=401, detail={"code": "NOT_AUTHENTICATED", "message": "not authenticated"}
        ) from None
    try:
        tenant_id = parse_tenant_id(ctx.tenant_id)
        tenant = await resolve_active(tenants, tenant_id)
    except TenantAccessError as exc:
        raise _http(exc) from None
    enriched = dataclasses.replace(ctx, tenant_slug=tenant.slug, region_code=tenant.region_code)
    with use_context(enriched):
        yield tenant
