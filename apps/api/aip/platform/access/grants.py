"""Grants and the ``GrantProvider`` port the policy service reads them from (ACCESS-01).

A ``Grant`` gives one permission at one scope: the whole tenant (``TenantScope``) or one project
(``ProjectScope``). Providers are registered on the ``PolicyService``; the principal's grants are
the union of what every provider returns. ACCESS-02 adds the role-assignment provider; until then
no provider is registered and every ``requires()`` route is denied.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from aip.platform.access.policy import AccessPrincipal

__all__ = ["Grant", "GrantProvider", "GrantScope", "ProjectScope", "TenantScope"]


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Matches any resource in the principal's own tenant."""


@dataclass(frozen=True, slots=True)
class ProjectScope:
    """Matches only resources whose ``project_id`` equals this one."""

    project_id: UUID | str


GrantScope = TenantScope | ProjectScope


@dataclass(frozen=True, slots=True)
class Grant:
    permission: str
    scope: GrantScope = TenantScope()


@runtime_checkable
class GrantProvider(Protocol):
    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        """Every grant this source gives ``principal`` (in the principal's own tenant)."""
        ...
