"""Business logic for tenancy (TENANCY-01): load a tenant and decide whether it may be used.

Status to access (step 4), failing closed for anything unknown:

==============  ======  =====================
status          HTTP    code
==============  ======  =====================
active          -       (allowed)
suspended       403     ``TENANT_SUSPENDED``
offboarding     403     ``TENANT_OFFBOARDED``
offboarded      403     ``TENANT_OFFBOARDED``
provisioning    403     ``TENANT_NOT_READY``
anything else   403     ``TENANT_UNAVAILABLE``
==============  ======  =====================
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.tenancy.repository import load_tenant
from aip.modules.tenancy.schemas import TenantView
from aip.platform.db.session import with_tenant

__all__ = [
    "Denial",
    "TenantAccessError",
    "TenantConnect",
    "TenantLoader",
    "TenantService",
    "access_for_status",
]


@dataclass(frozen=True, slots=True)
class Denial:
    status_code: int
    code: str
    message: str


class TenantAccessError(Exception):
    """The caller may not act for this tenant. Messages never name the tenant."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message

    @classmethod
    def from_denial(cls, denial: Denial) -> TenantAccessError:
        return cls(denial.status_code, denial.code, denial.message)


_SUSPENDED = Denial(403, "TENANT_SUSPENDED", "this tenant is suspended")
_OFFBOARDED = Denial(403, "TENANT_OFFBOARDED", "this tenant has been offboarded")
_NOT_READY = Denial(403, "TENANT_NOT_READY", "this tenant is not ready yet")
_UNAVAILABLE = Denial(403, "TENANT_UNAVAILABLE", "this tenant is not available")

_ACCESS: dict[str, Denial | None] = {
    "active": None,
    "suspended": _SUSPENDED,
    "offboarding": _OFFBOARDED,
    "offboarded": _OFFBOARDED,
    "provisioning": _NOT_READY,
}


def access_for_status(status: str) -> Denial | None:
    """``None`` when a tenant in ``status`` may be used, else why not. Unknown denies."""
    return _ACCESS.get(status, _UNAVAILABLE)


class TenantLoader(Protocol):
    async def get(self, tenant_id: UUID) -> TenantView | None: ...


TenantConnect = Callable[[UUID], AbstractAsyncContextManager[AsyncConnection]]


class TenantService:
    """Loads tenants inside ``with_tenant`` (tests pass a ``with_tenant`` bound to their engine)."""

    def __init__(self, connect: TenantConnect = with_tenant) -> None:
        self._connect = connect

    async def get(self, tenant_id: UUID) -> TenantView | None:
        """The tenant ``tenant_id``, read under its own RLS context, or ``None``."""
        async with self._connect(tenant_id) as conn:
            return await load_tenant(conn, tenant_id)


async def resolve_active(loader: TenantLoader, tenant_id: UUID) -> TenantView:
    """The tenant if it exists and is active; otherwise raise ``TenantAccessError``."""
    tenant = await loader.get(tenant_id)
    if tenant is None:
        raise TenantAccessError(401, "TENANT_UNKNOWN", "not authenticated for a known tenant")
    if tenant.id != tenant_id:  # defence in depth: RLS and the query already pin the id
        raise TenantAccessError(401, "TENANT_UNKNOWN", "not authenticated for a known tenant")
    denial = access_for_status(tenant.status)
    if denial is not None:
        raise TenantAccessError.from_denial(denial)
    return tenant
