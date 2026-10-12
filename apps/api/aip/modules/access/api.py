"""Published interface of the access module.

Other modules may import only this file. Keep it small and stable.

- ``get_access_version`` / ``bump_access_version`` (ADR 0020): ACCESS-02 bumps the version in the
  same transaction as every role, override or assignment change; ACCESS-04 keys its grant cache
  by it. Both take the connection from ``with_tenant``.
- ``sync_catalogue``: the startup sync of the permission catalogue (called by ``aip.main``).

The authorisation runtime itself (``PolicyService``, ``requires``) is ``aip.platform.access``.
"""

from __future__ import annotations

from typing import Protocol

from aip.modules.access.repository import (
    PermissionRow,
    bump_access_version,
    get_access_version,
    list_permissions,
)
from aip.modules.access.service import sync_catalogue

__all__ = [
    "ModuleApi",
    "PermissionRow",
    "bump_access_version",
    "get_access_version",
    "get_api",
    "list_permissions",
    "sync_catalogue",
]


class ModuleApi(Protocol):
    """The operations access offers to other modules."""


def get_api() -> ModuleApi:
    """Return the access module's published interface."""
    raise NotImplementedError
