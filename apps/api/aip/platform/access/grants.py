"""Grants and the ``GrantProvider`` port the policy service reads them from (ACCESS-01).

A ``Grant`` gives one permission at one scope: the whole tenant (``TenantScope``), one project
(``ProjectScope``) or one asset subtree inside a project (``AssetSubtreeScope``, PORTAL-01).
Providers are registered on the ``PolicyService``; the principal's grants are the union of what
every provider returns. ACCESS-02 adds the role-assignment provider; until then no provider is
registered and every ``requires()`` route is denied.

A provider class that sets ``serves_external = True`` (PORTAL-01's portal grants) is asked only for
external principals (``AccessPrincipal.external``); every other provider only for internal ones.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from aip.platform.access.policy import AccessPrincipal

__all__ = [
    "AssetSubtreeScope",
    "Grant",
    "GrantProvider",
    "GrantScope",
    "ProjectScope",
    "TenantScope",
]


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Matches any resource in the principal's own tenant."""


@dataclass(frozen=True, slots=True)
class ProjectScope:
    """Matches only resources whose ``project_id`` equals this one."""

    project_id: UUID | str


@dataclass(frozen=True, slots=True)
class AssetSubtreeScope:
    """Matches only resources in ``project_id`` whose asset path runs through ``asset_id``.

    The resource's ``asset_path`` (ltree text) must contain a label equal to ``asset_id`` without
    dashes (ASSETS-01 labels each node by its id), so the node and its descendants match and its
    siblings and ancestors do not. A resource without an asset path never matches (fail closed).
    """

    project_id: UUID | str
    asset_id: UUID | str


GrantScope = TenantScope | ProjectScope | AssetSubtreeScope


@dataclass(frozen=True, slots=True)
class Grant:
    permission: str
    scope: GrantScope = TenantScope()


@runtime_checkable
class GrantProvider(Protocol):
    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        """Every grant this source gives ``principal`` (in the principal's own tenant)."""
        ...
