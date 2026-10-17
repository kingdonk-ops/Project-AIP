"""``requires_flag``: hide a route while its release flag is off for the tenant (ARCH-08).

::

    @router.get("/bim/models", dependencies=[Depends(requires("bim.model.view")),
                                             Depends(requires_flag("bim"))])

It answers 404 (the route looks absent) unless the caller's tenant, from the verified request
context, has the flag on AND the ``EntitlementCheck`` allows it. It is not an access declaration:
the route still declares ``requires()`` or ``authenticated()``. An unknown flag fails at import.

``EntitlementCheck`` is the hook for what the tenant paid for (ADR 0008). The platform may not
import ``aip.modules`` (import-linter), so ``aip.main`` sets ``app.state.flag_entitlements`` to
tenancy's ``FlagEntitlements`` (flag ``x`` needs ``feature.x``) whenever the tenancy module is
enabled. Only an app built without tenancy (test fixtures) falls back to ``AllowAllEntitlements``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from fastapi import HTTPException, Request

from aip.platform.context import ContextMissingError, get_context
from aip.platform.db.session import with_tenant
from aip.platform.flags.service import FlagService, check_flag

__all__ = ["AllowAllEntitlements", "EntitlementCheck", "get_flag_entitlements", "requires_flag"]


class EntitlementCheck(Protocol):
    async def allows(self, tenant_id: UUID, flag: str) -> bool:
        """Whether the tenant is entitled to the feature behind ``flag``."""
        ...


class AllowAllEntitlements:
    """The default hook: every tenant is entitled (ENT-01's own route gates still apply)."""

    async def allows(self, tenant_id: UUID, flag: str) -> bool:
        return True


def get_flag_entitlements(request: Request) -> EntitlementCheck:
    check: EntitlementCheck | None = getattr(request.app.state, "flag_entitlements", None)
    return AllowAllEntitlements() if check is None else check


def requires_flag(flag: str) -> Callable[[Request], Awaitable[None]]:
    """A dependency that answers 404 unless ``flag`` is on and entitled for the caller's tenant."""
    check_flag(flag)  # UnknownFlagError at import, not at request time

    async def dependency(request: Request) -> None:
        try:
            ctx = get_context()
        except ContextMissingError:
            raise HTTPException(status_code=401, detail="Not authenticated") from None
        async with with_tenant(ctx) as conn:
            enabled = await FlagService().is_enabled(conn, flag)
        if not enabled or not await get_flag_entitlements(request).allows(ctx.tenant_id, flag):
            raise HTTPException(status_code=404, detail="Not Found")

    return dependency
