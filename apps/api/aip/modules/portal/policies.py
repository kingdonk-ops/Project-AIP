"""Pure rules for portal users and grants (PORTAL-01). No I/O here.

Authorisation goes through the policy service (``requires`` on every route, ``PolicyService.can``
per project in the service) and RLS, deny by default.

- ``ACTION_PERMISSIONS``: what each grant action gives. ``view`` -> ``portal.record.view``,
  ``sign_off`` -> ``portal.record.sign_off``, ``witness`` -> ``portal.record.witness``,
  ``download`` -> ``portal.report.download``. ``register_action_permissions`` lets a host module
  add its own codes to an action (INSPECTIONS-05 adds its client-review permission to
  ``sign_off``); an unknown action raises ``ValueError``. ``unknown_action_codes`` lists the codes
  missing from a catalogue, which fails app start (``routes.py`` lifespan).
- ``grant_state(grant, now)``: ``revoked`` when ``revoked_at`` is set, ``expired`` when
  ``expires_at <= now``, else ``live``. Reads and the grant provider both use it, so expiry needs
  no job.
- ``effective_status(status, states)``: ``suspended``/``invited`` as stored; ``expired`` when an
  active user has no live grant and at least one expired one; else ``active``.
- ``access_days(value)``: a project's ``portal_access_days`` setting, 1 to 400, else 180.
- ``reinstated_status(first_signed_in_at)``: ``active`` for a user who has signed in, else
  ``invited``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Final, Literal, Protocol

__all__ = [
    "ACTIONS",
    "ACTION_PERMISSIONS",
    "DEFAULT_ACCESS_DAYS",
    "MAX_ACCESS_DAYS",
    "MAX_GRANTS_PER_INVITE",
    "SUSPENDABLE",
    "Action",
    "EffectiveStatus",
    "GrantState",
    "PortalUserStatus",
    "RevokeReason",
    "access_days",
    "effective_status",
    "expand_actions",
    "grant_state",
    "register_action_permissions",
    "reinstated_status",
    "unknown_action_codes",
]

logger = logging.getLogger(__name__)

Action = Literal["view", "sign_off", "witness", "download"]
PortalUserStatus = Literal["invited", "active", "suspended"]
EffectiveStatus = Literal["invited", "active", "suspended", "expired"]
GrantState = Literal["live", "expired", "revoked"]
RevokeReason = Literal["manual", "project_closed", "user_suspended"]

ACTIONS: Final[tuple[Action, ...]] = ("view", "sign_off", "witness", "download")
DEFAULT_ACCESS_DAYS: Final = 180
MAX_ACCESS_DAYS: Final = 400
MAX_GRANTS_PER_INVITE: Final = 20
SUSPENDABLE: Final[frozenset[str]] = frozenset({"invited", "active"})

# Mutable on purpose: host modules add codes at import (register_action_permissions).
ACTION_PERMISSIONS: Final[dict[str, list[str]]] = {
    "view": ["portal.record.view"],
    "sign_off": ["portal.record.sign_off"],
    "witness": ["portal.record.witness"],
    "download": ["portal.report.download"],
}


def register_action_permissions(action: str, codes: Iterable[str]) -> None:
    """Add permission ``codes`` to what a grant ``action`` gives (idempotent per code).

    ``ValueError`` for an action outside ``ACTIONS``. A code missing from the catalogue is caught
    when the app starts (``unknown_action_codes``).
    """
    if action not in ACTION_PERMISSIONS:
        raise ValueError(f"unknown portal grant action {action!r}")
    held = ACTION_PERMISSIONS[action]
    for code in codes:
        if code not in held:
            held.append(code)


def expand_actions(actions: Iterable[str]) -> set[str]:
    """The permission codes a grant with ``actions`` gives (unknown actions give nothing)."""
    codes: set[str] = set()
    for action in actions:
        codes.update(ACTION_PERMISSIONS.get(action, ()))
    return codes


def unknown_action_codes(catalogue: Iterable[str]) -> list[str]:
    """The codes in ``ACTION_PERMISSIONS`` that ``catalogue`` does not declare, sorted."""
    known = set(catalogue)
    return sorted({c for codes in ACTION_PERMISSIONS.values() for c in codes} - known)


class _GrantLike(Protocol):
    @property
    def expires_at(self) -> datetime: ...
    @property
    def revoked_at(self) -> datetime | None: ...


def grant_state(grant: _GrantLike | Mapping[str, Any], now: datetime) -> GrantState:
    """``revoked``, ``expired`` (``expires_at <= now``) or ``live``."""
    if isinstance(grant, Mapping):
        revoked_at: datetime | None = grant.get("revoked_at")
        expires_at: datetime = grant["expires_at"]
    else:
        revoked_at, expires_at = grant.revoked_at, grant.expires_at
    if revoked_at is not None:
        return "revoked"
    if expires_at <= now:
        return "expired"
    return "live"


def effective_status(status: str, states: Iterable[GrantState]) -> EffectiveStatus:
    """What an admin sees: the stored status, or ``expired`` for an active user whose grants all
    ran out (at least one expired, none live)."""
    if status == "suspended":
        return "suspended"
    if status == "invited":
        return "invited"
    seen = set(states)
    if "live" not in seen and "expired" in seen:
        return "expired"
    return "active"


def access_days(value: object) -> int:
    """A project's ``portal_access_days``: an integer 1..400, else the default 180 (logged)."""
    if value is None:
        return DEFAULT_ACCESS_DAYS
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_ACCESS_DAYS:
        logger.warning(
            "portal_access_days %r is outside 1..%d; using %d",
            value,
            MAX_ACCESS_DAYS,
            DEFAULT_ACCESS_DAYS,
        )
        return DEFAULT_ACCESS_DAYS
    return value


def reinstated_status(first_signed_in_at: datetime | None) -> PortalUserStatus:
    """Where a reinstated user goes: ``active`` once they have signed in, else ``invited``."""
    return "active" if first_signed_in_at is not None else "invited"
