"""Ports the context middleware calls to learn who is asking (ADR 0005).

The real session/cookie ``PrincipalResolver`` arrives with the identity tasks; tests inject a
fixture resolver that maps bearer tokens to principals. The defaults here deny everything.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "DenyAllMembershipResolver",
    "DenyAllPrincipalResolver",
    "Principal",
    "PrincipalResolver",
    "ProjectMembershipResolver",
]


@dataclass(frozen=True, slots=True)
class Principal:
    """A verified caller: the tenant it belongs to, the actor, and the assets it may see."""

    tenant_id: UUID
    actor_id: UUID | None = None
    asset_path_scope: tuple[str, ...] = ()


@runtime_checkable
class PrincipalResolver(Protocol):
    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        """Return the verified principal for these (lower-cased) request headers, or ``None``."""
        ...


@runtime_checkable
class ProjectMembershipResolver(Protocol):
    async def is_member(self, *, tenant_id: UUID, actor_id: UUID | None, project_id: UUID) -> bool:
        """True when the actor may act within ``project_id`` in ``tenant_id``."""
        ...


class DenyAllPrincipalResolver:
    """Default until identity lands: nobody is authenticated."""

    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        return None


class DenyAllMembershipResolver:
    """Default until projects land: nobody is a member of any project."""

    async def is_member(self, *, tenant_id: UUID, actor_id: UUID | None, project_id: UUID) -> bool:
        return False
