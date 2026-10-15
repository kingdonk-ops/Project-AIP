"""Tenant feature-flag settings API (ARCH-08).

Mounted by ``aip.main`` under ``/api/v1`` when ``tenant.flags.manage`` is in the permission
catalogue (the tenancy module declares it).

- ``GET /settings/flags``: every known flag's effective value for the caller's tenant. Any signed-in
  user may read it, because the web nav uses it to show or hide deferred modules.
- ``PUT /settings/flags/{flag}`` with ``{"enabled": bool}`` (``tenant.flags.manage``): set the
  tenant's value; a change emits ``platform.flag.changed`` in the same transaction. 404 for an
  unknown flag.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, StrictBool
from pydantic.alias_generators import to_camel

from aip.platform.access import authenticated, requires
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant
from aip.platform.flags.service import FlagService, UnknownFlagError, check_flag

__all__ = ["FLAGS_MANAGE_PERMISSION", "create_router"]

FLAGS_MANAGE_PERMISSION = "tenant.flags.manage"


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class FeatureFlag(_Model):
    flag: str
    enabled: bool


class FeatureFlags(_Model):
    flags: list[FeatureFlag]


class FeatureFlagPut(_Model):
    enabled: StrictBool


def create_router() -> APIRouter:
    router = APIRouter(prefix="/settings/flags", tags=["platform"])

    @router.get("", response_model=FeatureFlags, dependencies=[Depends(authenticated())])
    async def list_flags() -> FeatureFlags:  # pyright: ignore[reportUnusedFunction]
        async with with_tenant(get_context()) as conn:
            values = await FlagService().all(conn)
        return FeatureFlags(
            flags=[FeatureFlag(flag=flag, enabled=enabled) for flag, enabled in values.items()]
        )

    @router.put(
        "/{flag}",
        response_model=FeatureFlag,
        dependencies=[Depends(requires(FLAGS_MANAGE_PERMISSION))],
    )
    async def set_flag(  # pyright: ignore[reportUnusedFunction]
        flag: Annotated[str, Path(max_length=63)], body: FeatureFlagPut
    ) -> FeatureFlag:
        try:
            check_flag(flag)
        except UnknownFlagError:
            raise HTTPException(status_code=404, detail="unknown feature flag") from None
        async with with_tenant(get_context()) as conn:
            change = await FlagService().set(conn, flag, body.enabled)
        return FeatureFlag(flag=change.flag, enabled=change.enabled)

    return router
