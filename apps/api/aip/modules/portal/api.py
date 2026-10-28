"""Published interface of the portal module (PORTAL-01).

Other modules may import only this file. Every ``PortalApi`` method takes the tenant-bound
connection the caller already holds from ``with_tenant``, so its work joins their transaction.

- ``get_portal_user_by_user_id(conn, user_id)``: the live ``portal_users`` row for an identity user.
- ``mark_signed_in(conn, user_id)`` (PORTAL-02): ``invited`` -> ``active`` at the first sign-in,
  with no other approval; idempotent, and any other status is left alone.
- ``live_grants(conn, user_id)`` (PORTAL-02/03): the user's live grants.
- ``grants_expiring_between(conn, start, end)`` (PORTAL-08): unrevoked grants expiring in
  ``[start, end)``.
- ``grant_state`` / ``effective_status``: the pure lifecycle rules.
- ``register_action_permissions(action, codes)``: a host module adds its own permission codes to
  a grant action (INSPECTIONS-05 adds its client-review permission to ``sign_off``).
- ``PortalGrantProvider``: portal grants as policy grants (registered by ``aip.main``).
- ``ACTIONS`` / ``ACTION_PERMISSIONS``: the grant action codes and what each gives.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.portal import repository as repo
from aip.modules.portal import service
from aip.modules.portal.grant_provider import PortalGrantProvider
from aip.modules.portal.policies import (
    ACTION_PERMISSIONS,
    ACTIONS,
    Action,
    EffectiveStatus,
    GrantState,
    effective_status,
    grant_state,
    register_action_permissions,
)
from aip.modules.portal.schemas import GrantOut

__all__ = [
    "ACTIONS",
    "ACTION_PERMISSIONS",
    "Action",
    "EffectiveStatus",
    "GrantOut",
    "GrantState",
    "PortalApi",
    "PortalGrantProvider",
    "effective_status",
    "get_api",
    "grant_state",
    "register_action_permissions",
]


class PortalApi:
    """The operations the portal module offers to other modules."""

    async def get_portal_user_by_user_id(
        self, conn: AsyncConnection, user_id: UUID
    ) -> dict[str, Any] | None:
        return await repo.get_user_by_user_id(conn, user_id)

    async def mark_signed_in(self, conn: AsyncConnection, user_id: UUID) -> dict[str, Any] | None:
        return await service.mark_signed_in(conn, user_id)

    async def live_grants(self, conn: AsyncConnection, user_id: UUID) -> list[GrantOut]:
        return await service.live_grants(conn, user_id)

    async def grants_expiring_between(
        self, conn: AsyncConnection, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        return await repo.grants_expiring_between(conn, start, end)

    grant_state = staticmethod(grant_state)
    effective_status = staticmethod(effective_status)
    register_action_permissions = staticmethod(register_action_permissions)


def get_api() -> PortalApi:
    """Return the portal module's published interface."""
    return PortalApi()
