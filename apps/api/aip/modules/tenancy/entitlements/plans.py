"""Plans and add-ons, in code (ENT-01 step 2, ADR 0008 table, ADR 0023 point 1).

Changing a plan's numbers is a release: plans are versioned, validated when this module is imported
(so a bad plan stops startup) and tested. One tenant's limits change through overrides instead.
Prices never appear here (ADR 0008).

Keys: ``feature.<name>`` is a boolean; ``limit.<name>`` is a whole number, or ``None`` for
unlimited. Each limit carries the action taken when it is reached (ADR 0023 point 2): ``BLOCK``
refuses, ``WARN`` allows and records, ``OVERAGE`` allows and records the overage for the invoice
(ENT-02 exports it). Storage and database size warn at 80% and 95% (``WARN_AT``).

Decisions on the ADR 0008 table:

- ``feature.reporting_feed`` is off in every plan and switched on only by the ``reporting_feed``
  add-on (adjustment C sells it as an add-on).
- ``feature.bim`` is off in every plan and switched on by the ``bim`` add-on.
- Enterprise's "custom" full-seat count is unlimited here; the contracted number is the
  subscription's ``seat_limits`` or an override.
- ``limit.storage_gb`` blocks at 100%, and only new uploads check it, so reads, exports and
  sign-off are never refused (ADR 0023 point 2). ``limit.db_gb`` only warns.
- ``core``'s included database size is OPEN-QUESTIONS 24; 5 GB is the ADR 0008 table's figure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ADD_ONS",
    "PLANS",
    "PRODUCTION_TERMS",
    "WARN_AT",
    "AddOn",
    "ContractRefRequiredError",
    "LimitAction",
    "LimitSpec",
    "Plan",
    "PlanRegistry",
    "Term",
    "build_registry",
    "check_contract_ref",
    "default_registry",
    "is_feature_key",
    "is_limit_key",
]

LimitAction = Literal["BLOCK", "WARN", "OVERAGE"]
Term = Literal["annual", "multi_year", "trial", "sandbox"]

# Production terms need the contract reference (ADR 0017); trial and sandbox do not.
PRODUCTION_TERMS: Final[frozenset[str]] = frozenset({"annual", "multi_year"})


class ContractRefRequiredError(ValueError):
    """A production term without ``contract_ref`` (422 ``CONTRACT_REF_REQUIRED``)."""


def check_contract_ref(term: str, contract_ref: str | None) -> None:
    """Raise ``ContractRefRequiredError`` for an annual or multi-year term without a reference."""
    if term in PRODUCTION_TERMS and not (contract_ref or "").strip():
        raise ContractRefRequiredError(f"a {term} subscription needs a contract reference")


# Percentages of a limit at which a decision reports a threshold (ADR 0023 point 2).
WARN_AT: Final[tuple[int, ...]] = (80, 95, 100)

_FEATURE = re.compile(r"^feature\.[a-z][a-z0-9_]*$")
_LIMIT = re.compile(r"^limit\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
_CODE = re.compile(r"^[a-z][a-z0-9_]*$")

NonNegative = Annotated[int, Field(ge=0)]


def is_feature_key(key: str) -> bool:
    return _FEATURE.fullmatch(key) is not None


def is_limit_key(key: str) -> bool:
    return _LIMIT.fullmatch(key) is not None


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LimitSpec(_Frozen):
    """A plan's amount for one limit (``None`` = unlimited) and what happens when it is reached."""

    value: NonNegative | None
    action: LimitAction = "BLOCK"


def _check_feature_keys(keys: Iterable[str]) -> None:
    bad = sorted(key for key in keys if not is_feature_key(key))
    if bad:
        raise ValueError(f"not feature.* keys: {', '.join(bad)}")


def _check_limit_keys(keys: Iterable[str]) -> None:
    bad = sorted(key for key in keys if not is_limit_key(key))
    if bad:
        raise ValueError(f"not limit.* keys: {', '.join(bad)}")


class Plan(_Frozen):
    code: str
    version: Annotated[int, Field(ge=1)]
    features: Mapping[str, bool]
    limits: Mapping[str, LimitSpec]

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not _CODE.fullmatch(value):
            raise ValueError("plan code must be lower snake_case")
        return value

    @field_validator("features")
    @classmethod
    def _features(cls, value: Mapping[str, bool]) -> Mapping[str, bool]:
        _check_feature_keys(value)
        return value

    @field_validator("limits")
    @classmethod
    def _limits(cls, value: Mapping[str, LimitSpec]) -> Mapping[str, LimitSpec]:
        _check_limit_keys(value)
        return value


class AddOn(_Frozen):
    """Switches features on, raises limits to at least ``limits``, and adds ``increments``."""

    code: str
    version: Annotated[int, Field(ge=1)] = 1
    features: frozenset[str] = frozenset()
    limits: Mapping[str, NonNegative | None] = {}
    increments: Mapping[str, NonNegative] = {}

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not _CODE.fullmatch(value):
            raise ValueError("add-on code must be lower snake_case")
        return value

    @field_validator("features")
    @classmethod
    def _features(cls, value: frozenset[str]) -> frozenset[str]:
        _check_feature_keys(value)
        return value

    @field_validator("limits", "increments")
    @classmethod
    def _limits(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        _check_limit_keys(value)
        return value


class PlanRegistry(_Frozen):
    plans: Mapping[str, Plan]
    add_ons: Mapping[str, AddOn]

    def plan(self, code: str) -> Plan | None:
        return self.plans.get(code)

    def add_on(self, code: str) -> AddOn | None:
        return self.add_ons.get(code)

    def feature_keys(self) -> list[str]:
        keys = {key for plan in self.plans.values() for key in plan.features}
        keys |= {key for add_on in self.add_ons.values() for key in add_on.features}
        return sorted(keys)

    def limit_keys(self) -> list[str]:
        return sorted({key for plan in self.plans.values() for key in plan.limits})


def build_registry(
    plans: Iterable[Mapping[str, object]], add_ons: Iterable[Mapping[str, object]]
) -> PlanRegistry:
    """Validate raw plan and add-on data; raises ``pydantic.ValidationError`` on a bad one."""
    built_plans = [Plan.model_validate(raw) for raw in plans]
    built_add_ons = [AddOn.model_validate(raw) for raw in add_ons]
    return PlanRegistry(
        plans={plan.code: plan for plan in built_plans},
        add_ons={add_on.code: add_on for add_on in built_add_ons},
    )


def _seats(full: int | None, portal: int | None, action: LimitAction) -> dict[str, object]:
    return {
        "limit.seats.full": {"value": full, "action": action},
        "limit.seats.portal": {"value": portal, "action": action},
    }


_RAW_PLANS: Final[tuple[dict[str, object], ...]] = (
    {
        "code": "core",
        "version": 1,
        "features": {
            "feature.portal": True,
            "feature.api": False,
            "feature.sso": False,
            "feature.custom_categories": False,
            "feature.reporting_feed": False,
            "feature.bim": False,
        },
        "limits": {
            **_seats(1, 3, "OVERAGE"),
            "limit.projects": {"value": 2, "action": "OVERAGE"},
            "limit.storage_gb": {"value": 25, "action": "BLOCK"},
            "limit.db_gb": {"value": 5, "action": "WARN"},
            "limit.api_calls_per_day": {"value": 0, "action": "BLOCK"},
        },
    },
    {
        "code": "professional",
        "version": 1,
        "features": {
            "feature.portal": True,
            "feature.api": True,
            "feature.sso": False,
            "feature.custom_categories": True,
            "feature.reporting_feed": False,
            "feature.bim": False,
        },
        "limits": {
            **_seats(5, 20, "OVERAGE"),
            "limit.projects": {"value": 15, "action": "OVERAGE"},
            "limit.storage_gb": {"value": 250, "action": "BLOCK"},
            "limit.db_gb": {"value": 20, "action": "WARN"},
            "limit.api_calls_per_day": {"value": 5000, "action": "BLOCK"},
        },
    },
    {
        "code": "enterprise",
        "version": 1,
        "features": {
            "feature.portal": True,
            "feature.api": True,
            "feature.sso": True,
            "feature.custom_categories": True,
            "feature.reporting_feed": False,
            "feature.bim": False,
        },
        "limits": {
            **_seats(None, None, "OVERAGE"),
            "limit.projects": {"value": None, "action": "OVERAGE"},
            "limit.storage_gb": {"value": 2048, "action": "BLOCK"},
            "limit.db_gb": {"value": 100, "action": "WARN"},
            "limit.api_calls_per_day": {"value": None, "action": "BLOCK"},
        },
    },
)

_RAW_ADD_ONS: Final[tuple[dict[str, object], ...]] = (
    {"code": "bim", "features": frozenset({"feature.bim"})},
    {"code": "reporting_feed", "features": frozenset({"feature.reporting_feed"})},
    {"code": "db_block_20gb", "increments": {"limit.db_gb": 20}},
)

_REGISTRY: Final[PlanRegistry] = build_registry(_RAW_PLANS, _RAW_ADD_ONS)
PLANS: Final[Mapping[str, Plan]] = _REGISTRY.plans
ADD_ONS: Final[Mapping[str, AddOn]] = _REGISTRY.add_ons


def default_registry() -> PlanRegistry:
    return _REGISTRY
