"""Per-tenant release flags for deferred modules (ARCH-08, ADR 0008).

Release flags (rollout, kill switch) are separate from entitlements (what a tenant paid for,
ENT-01).
``requires_flag("bim")`` hides a route while the tenant's flag is off; ``FlagService`` reads and
sets values; ``GET``/``PUT /api/v1/settings/flags`` are in ``routes``.
"""

from aip.platform.flags.dependency import (
    AllowAllEntitlements,
    EntitlementCheck,
    get_flag_entitlements,
    requires_flag,
)
from aip.platform.flags.service import (
    FLAG_CHANGED,
    FlagChange,
    FlagService,
    UnknownFlagError,
    check_flag,
    known_flags,
    register_flag,
)

__all__ = [
    "FLAG_CHANGED",
    "AllowAllEntitlements",
    "EntitlementCheck",
    "FlagChange",
    "FlagService",
    "UnknownFlagError",
    "check_flag",
    "get_flag_entitlements",
    "known_flags",
    "register_flag",
    "requires_flag",
]
