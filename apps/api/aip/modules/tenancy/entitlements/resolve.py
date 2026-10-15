"""``resolve``: one entitlement key for one tenant, as a pure function (ENT-01 step 4, ADR 0008).

Order, each step able to change the value and its ``source``:

1. **plan**: the plan's feature flag or limit. For limits, the subscription's contracted amounts
   (``seat_limits`` per class -> ``limit.seats.<class>``, ``storage_gb`` -> ``limit.storage_gb``)
   replace the plan's figure; they are part of the plan as sold, so the source stays ``plan``.
2. **add_on**: features are OR'd; a limit takes the larger value (``None``, unlimited, is the
   largest); an increment adds to it.
3. **override**: an unexpired tenant override wins, even when it is lower. The newest one counts.
4. **toggle**: a site/project toggle can only switch a feature off; never on, never a limit.

Fail closed: no subscription, a subscription that is not ``active``, has not started yet or
whose ``ends_on`` has passed, or a plan code the registry does not know gives every feature
``False`` and every limit ``0``, with source ``none``. A key that is not ``feature.*`` or
``limit.*`` (release flags are ``release.*`` and belong to ARCH-08) raises
``InvalidEntitlementKey``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from aip.modules.tenancy.entitlements.plans import (
    WARN_AT,
    AddOn,
    LimitAction,
    Plan,
    is_feature_key,
    is_limit_key,
)

__all__ = [
    "InvalidEntitlementKey",
    "LimitDecision",
    "OverrideView",
    "Resolution",
    "Source",
    "SubscriptionView",
    "check_key",
    "decide_limit",
    "is_live",
    "live_overrides",
    "resolve",
]

Source = Literal["plan", "add_on", "override", "toggle", "none"]
Value = bool | int | None


class InvalidEntitlementKey(ValueError):  # noqa: N818 - the name the spec and callers use
    """The key is not ``feature.<name>`` or ``limit.<name>`` (for example a ``release.*`` flag)."""

    def __init__(self, key: str) -> None:
        super().__init__(
            f"not an entitlement key: {key!r} (features are feature.*, limits limit.*)"
        )
        self.key = key


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    tenant_id: UUID
    plan_code: str
    plan_version: int
    term: str
    status: str
    starts_on: date
    ends_on: date | None = None
    renewal_date: date | None = None
    seat_limits: Mapping[str, int | None] = field(default_factory=dict[str, int | None])
    storage_gb: int | None = None
    add_ons: tuple[str, ...] = ()
    contract_ref: str | None = None
    entitlement_version: int = 1


@dataclass(frozen=True, slots=True)
class OverrideView:
    id: UUID
    key: str
    value: Value
    reason: str
    created_at: datetime
    expires_at: datetime | None = None
    created_by: UUID | None = None


@dataclass(frozen=True, slots=True)
class Resolution:
    value: Value
    source: Source
    action: LimitAction | None = None  # limits only


def check_key(key: str) -> Literal["feature", "limit"]:
    if is_feature_key(key):
        return "feature"
    if is_limit_key(key):
        return "limit"
    raise InvalidEntitlementKey(key)


def is_live(subscription: SubscriptionView | None, now: datetime) -> bool:
    """Whether ``subscription`` grants anything at ``now`` (active, started, not ended)."""
    if subscription is None or subscription.status != "active":
        return False
    if subscription.starts_on > now.date():
        return False
    return subscription.ends_on is None or subscription.ends_on >= now.date()


def live_overrides(overrides: Sequence[OverrideView], now: datetime) -> list[OverrideView]:
    """The overrides not yet expired at ``now``."""
    return [o for o in overrides if o.expires_at is None or o.expires_at > now]


def _override_for(
    key: str, overrides: Sequence[OverrideView], now: datetime
) -> OverrideView | None:
    matching = [o for o in live_overrides(overrides, now) if o.key == key]
    return max(matching, key=lambda o: o.created_at) if matching else None


def _larger(a: int | None, b: int | None) -> int | None:
    return None if a is None or b is None else max(a, b)


def _feature(
    key: str,
    plan: Plan,
    add_ons: Sequence[AddOn],
    override: OverrideView | None,
    toggles: Mapping[str, bool],
) -> Resolution:
    value = bool(plan.features.get(key, False))
    source: Source = "plan"
    if not value and any(key in add_on.features for add_on in add_ons):
        value, source = True, "add_on"
    if override is not None:
        value, source = bool(override.value), "override"
    if value and toggles.get(key) is False:
        value, source = False, "toggle"
    return Resolution(value, source)


def _contracted(key: str, subscription: SubscriptionView) -> tuple[bool, int | None]:
    """Whether the subscription contracts an amount for ``key``, and that amount."""
    if key == "limit.storage_gb" and subscription.storage_gb is not None:
        return True, subscription.storage_gb
    prefix = "limit.seats."
    if key.startswith(prefix):
        user_class = key.removeprefix(prefix)
        if user_class in subscription.seat_limits:
            return True, subscription.seat_limits[user_class]
    return False, None


def _limit(
    key: str,
    subscription: SubscriptionView,
    plan: Plan,
    add_ons: Sequence[AddOn],
    override: OverrideView | None,
) -> Resolution:
    spec = plan.limits.get(key)
    if spec is None:
        value: int | None = 0
        source: Source = "none"
        action: LimitAction = "BLOCK"
    else:
        value, source, action = spec.value, "plan", spec.action
    contracted, amount = _contracted(key, subscription)
    if contracted:
        value, source = amount, "plan"
    for add_on in add_ons:
        raised = value
        if key in add_on.limits:
            raised = _larger(raised, add_on.limits[key])
        if key in add_on.increments and raised is not None:
            raised += add_on.increments[key]
        if raised != value:
            value, source = raised, "add_on"
    if override is not None:
        raw = override.value
        value = None if raw is None else int(raw)
        source = "override"
    return Resolution(value, source, action)


def resolve(
    key: str,
    *,
    subscription: SubscriptionView | None,
    plan: Plan | None,
    add_ons: Sequence[AddOn],
    overrides: Sequence[OverrideView],
    toggles: Mapping[str, bool],
    now: datetime,
) -> Resolution:
    """The value of ``key`` for this tenant at ``now`` and where it came from (see the module)."""
    kind = check_key(key)
    if plan is None or subscription is None or not is_live(subscription, now):
        return Resolution(False, "none") if kind == "feature" else Resolution(0, "none", "BLOCK")
    override = _override_for(key, overrides, now)
    if kind == "feature":
        return _feature(key, plan, add_ons, override, toggles)
    return _limit(key, subscription, plan, add_ons, override)


@dataclass(frozen=True, slots=True)
class LimitDecision:
    """Whether ``requested_total`` fits a limit (ADR 0023 point 2).

    ``allowed`` is False only for a ``BLOCK`` limit that would be exceeded, or when nothing is
    granted (source ``none``). ``WARN`` and ``OVERAGE`` always allow; ``recorded`` says the call
    went over, and the service records it in the month's usage. ``threshold`` is the highest of
    80/95/100 percent that ``requested_total`` reaches (``None`` below 80% or when unlimited).
    """

    allowed: bool
    limit: int | None
    source: Source
    action: LimitAction
    threshold: int | None = None
    recorded: bool = False


def decide_limit(resolution: Resolution, requested_total: int) -> LimitDecision:
    """Apply ``resolution`` (a limit) to ``requested_total``, the total after the change."""
    action: LimitAction = resolution.action or "BLOCK"
    if resolution.source == "none":
        return LimitDecision(False, 0, "none", action)
    limit = resolution.value
    if limit is None or isinstance(limit, bool):  # unlimited
        return LimitDecision(True, None, resolution.source, action)
    if limit == 0:
        threshold = 100 if requested_total > 0 else None
    else:
        reached = [pct for pct in WARN_AT if requested_total * 100 >= limit * pct]
        threshold = reached[-1] if reached else None
    if requested_total <= limit:
        return LimitDecision(True, limit, resolution.source, action, threshold)
    if action == "BLOCK":
        return LimitDecision(False, limit, resolution.source, action, threshold)
    return LimitDecision(True, limit, resolution.source, action, threshold, recorded=True)
