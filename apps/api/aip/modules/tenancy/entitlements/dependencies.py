"""FastAPI helpers for entitlements (ENT-01 step 6, ADR 0023 point 3).

``requires_entitlement("feature.bim")`` is a route dependency::

    @router.get("/bim", dependencies=[Depends(requires("bim.model.view")),
                                      Depends(requires_entitlement("feature.bim"))])

It answers 403 ``{"code": "NOT_ENTITLED", "key": "feature.bim"}`` unless the caller's tenant (from
the verified request context, never the request) is entitled. It is not an access declaration: the
route still declares ``requires()`` or ``authenticated()``. A route is reachable only when the
entitlement allows it AND its release flag (ARCH-08) is on.

``ensure_within_limit`` raises 403 ``{"code": "LIMIT_REACHED", "gate", "limit", "current"}`` when a
``BLOCK`` limit would be exceeded; only paths that add something (an upload, a new project) call it,
so reads, exports and sign-off are never refused for a limit. The caller counts ``current``;
to keep concurrent adds from overshooting a ``BLOCK`` limit, count it under a lock (for
example in the same transaction as the insert, with the table's rows locked).

``FlagEntitlements`` is the ``EntitlementCheck`` that ``aip.main`` installs as
``app.state.flag_entitlements``: ``requires_flag("bim")`` then also needs ``feature.bim`` (review 11
M7). A flag with no ``feature.<flag>`` in any plan or add-on is never entitled, so it fails closed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request

from aip.modules.tenancy.entitlements.resolve import (
    InvalidEntitlementKey,
    LimitDecision,
    check_key,
)
from aip.modules.tenancy.entitlements.service import EntitlementService
from aip.platform.context import ContextMissingError, get_context
from aip.platform.http import DomainError

__all__ = [
    "FlagEntitlements",
    "ensure_within_limit",
    "get_entitlement_service",
    "requires_entitlement",
]


def _service_of(app: FastAPI) -> EntitlementService:
    service: EntitlementService | None = getattr(app.state, "entitlements", None)
    if service is None:
        service = EntitlementService()
        app.state.entitlements = service
    return service


def get_entitlement_service(request: Request) -> EntitlementService:
    """The app's ``EntitlementService`` (tests set ``app.state.entitlements`` with a fake clock)."""
    return _service_of(request.app)


class FlagEntitlements:
    """``requires_flag``'s entitlement hook: release flag ``x`` needs ``feature.x`` (ENT-01)."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    async def allows(self, tenant_id: UUID, flag: str) -> bool:
        try:
            ctx = get_context()
        except ContextMissingError:
            ctx = None
        project_id = ctx.project_id if ctx is not None and ctx.tenant_id == tenant_id else None
        decision = await _service_of(self._app).check(
            tenant_id, f"feature.{flag}", project_id=project_id
        )
        return decision.allowed


def requires_entitlement(feature_key: str) -> Callable[[Request], Awaitable[None]]:
    """A dependency that refuses with 403 ``NOT_ENTITLED`` unless the tenant has ``feature_key``."""
    if check_key(feature_key) != "feature":  # fails at import, not at request time
        raise InvalidEntitlementKey(feature_key)

    async def dependency(request: Request) -> None:
        try:
            ctx = get_context()
        except ContextMissingError:
            raise HTTPException(
                status_code=401,
                detail={"code": "NOT_AUTHENTICATED", "message": "not authenticated"},
            ) from None
        service = get_entitlement_service(request)
        decision = await service.check(ctx.tenant_id, feature_key, project_id=ctx.project_id)
        if not decision.allowed:
            raise DomainError(403, "NOT_ENTITLED", key=feature_key)

    return dependency


async def ensure_within_limit(
    service: EntitlementService, tenant_id: UUID, limit_key: str, current: int, adding: int = 1
) -> LimitDecision:
    """The decision for ``current + adding``; 403 ``LIMIT_REACHED`` if a ``BLOCK`` limit refuses."""
    decision = await service.check_limit(tenant_id, limit_key, current + adding)
    if not decision.allowed:
        raise DomainError(
            403, "LIMIT_REACHED", gate=limit_key, limit=decision.limit, current=current
        )
    return decision
