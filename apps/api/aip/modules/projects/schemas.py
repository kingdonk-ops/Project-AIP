"""Pydantic request/response models for projects and sites (PROJECTS-01).

JSON uses camelCase (``syncVersion``, ``siteId``). Codes are upper-cased before they are checked,
so ``l592`` is stored as ``L592``. Region keys need the database and are checked in the service.
"""

from __future__ import annotations

import re
import zoneinfo
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, ClassVar, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

__all__ = [
    "CURRENCIES",
    "ErrorBody",
    "ProjectCreate",
    "ProjectOut",
    "ProjectPage",
    "ProjectSort",
    "ProjectStatus",
    "ProjectUpdate",
    "SiteCreate",
    "SiteOut",
    "SitePage",
    "SiteUpdate",
]

ProjectStatus = Literal["draft", "active", "closing", "archived"]
ProjectSort = Literal["code", "name", "updated_at"]

_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,31}$")

# ISO 4217 currencies in circulation (no funds, metals or test codes such as XXX).
CURRENCIES = frozenset(
    [
        "AED",
        "AFN",
        "ALL",
        "AMD",
        "ANG",
        "AOA",
        "ARS",
        "AUD",
        "AWG",
        "AZN",
        "BAM",
        "BBD",
        "BDT",
        "BGN",
        "BHD",
        "BIF",
        "BMD",
        "BND",
        "BOB",
        "BRL",
        "BSD",
        "BTN",
        "BWP",
        "BYN",
        "BZD",
        "CAD",
        "CDF",
        "CHF",
        "CLP",
        "CNY",
        "COP",
        "CRC",
        "CUP",
        "CVE",
        "CZK",
        "DJF",
        "DKK",
        "DOP",
        "DZD",
        "EGP",
        "ERN",
        "ETB",
        "EUR",
        "FJD",
        "FKP",
        "GBP",
        "GEL",
        "GHS",
        "GIP",
        "GMD",
        "GNF",
        "GTQ",
        "GYD",
        "HKD",
        "HNL",
        "HTG",
        "HUF",
        "IDR",
        "ILS",
        "INR",
        "IQD",
        "IRR",
        "ISK",
        "JMD",
        "JOD",
        "JPY",
        "KES",
        "KGS",
        "KHR",
        "KMF",
        "KPW",
        "KRW",
        "KWD",
        "KYD",
        "KZT",
        "LAK",
        "LBP",
        "LKR",
        "LRD",
        "LSL",
        "LYD",
        "MAD",
        "MDL",
        "MGA",
        "MKD",
        "MMK",
        "MNT",
        "MOP",
        "MRU",
        "MUR",
        "MVR",
        "MWK",
        "MXN",
        "MYR",
        "MZN",
        "NAD",
        "NGN",
        "NIO",
        "NOK",
        "NPR",
        "NZD",
        "OMR",
        "PAB",
        "PEN",
        "PGK",
        "PHP",
        "PKR",
        "PLN",
        "PYG",
        "QAR",
        "RON",
        "RSD",
        "RUB",
        "RWF",
        "SAR",
        "SBD",
        "SCR",
        "SDG",
        "SEK",
        "SGD",
        "SHP",
        "SLE",
        "SOS",
        "SRD",
        "SSP",
        "STN",
        "SVC",
        "SYP",
        "SZL",
        "THB",
        "TJS",
        "TMT",
        "TND",
        "TOP",
        "TRY",
        "TTD",
        "TWD",
        "TZS",
        "UAH",
        "UGX",
        "USD",
        "UYU",
        "UZS",
        "VES",
        "VND",
        "VUV",
        "WST",
        "XAF",
        "XCD",
        "XOF",
        "XPF",
        "YER",
        "ZAR",
        "ZMW",
        "ZWG",
    ]
)


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def _check_code(value: str) -> str:
    if not _CODE.fullmatch(value):
        raise ValueError(
            "must be 2-32 characters of A-Z, 0-9 and '-', starting with a letter or digit"
        )
    return value


def _check_currency(value: str) -> str:
    if value not in CURRENCIES:
        raise ValueError("must be an ISO 4217 currency code")
    return value


def _check_timezone(value: str) -> str:
    if value not in zoneinfo.available_timezones():
        raise ValueError("must be an IANA time zone, for example Australia/Perth")
    return value


# The OpenAPI patterns describe what a client may send (any case: the server upper-cases), so the
# Zod schemas orval generates for the web forms reject the same input the server does
# (PROJECTS-02). The validators above stay the source of truth.
CODE_INPUT_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{1,31}$"
CURRENCY_INPUT_PATTERN = r"^[A-Za-z]{3}$"

Code = Annotated[
    str,
    BeforeValidator(_upper),
    AfterValidator(_check_code),
    Field(json_schema_extra={"pattern": CODE_INPUT_PATTERN}),
]
Currency = Annotated[
    str,
    BeforeValidator(_upper),
    AfterValidator(_check_currency),
    Field(json_schema_extra={"pattern": CURRENCY_INPUT_PATTERN}),
]
TimeZone = Annotated[str, AfterValidator(_check_timezone)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Region = Annotated[str, Field(min_length=1, max_length=64)]
Latitude = Annotated[Decimal, Field(ge=-90, le=90, max_digits=9, decimal_places=6)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180, max_digits=9, decimal_places=6)]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    """A response: built from database rows, so columns the API does not show are ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class _Patch(_Model):
    """A partial update: absent fields stay as they are; ``REQUIRED`` fields may not be null."""

    REQUIRED: ClassVar[tuple[str, ...]] = ("code", "name")

    @model_validator(mode="after")
    def _required_not_null(self) -> Self:
        nulls = [
            f for f in self.REQUIRED if f in self.model_fields_set and getattr(self, f) is None
        ]
        if nulls:
            raise ValueError(f"{', '.join(nulls)} cannot be null")
        return self

    def changes(self, *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
        """The fields the client sent, by column name."""
        return {f: getattr(self, f) for f in self.model_fields_set - exclude}


class ErrorBody(_Out):
    """A domain error: a stable ``code`` (``PROJECT_CODE_TAKEN``, ``SITE_IN_USE``, ...)."""

    code: str


# --- projects ---------------------------------------------------------------------------------


class ProjectCreate(_Model):
    code: Code
    name: Name
    status: Literal["draft", "active"] = "draft"
    site_id: UUID | None = None
    client_company_id: UUID | None = None
    classification_id: UUID | None = None
    template_id: UUID | None = None
    region: Region | None = None
    timezone: TimeZone | None = None
    currency: Currency | None = None


class ProjectUpdate(_Patch):
    """Only the fields sent are changed; ``syncVersion`` is the version the client last read."""

    REQUIRED: ClassVar[tuple[str, ...]] = ("code", "name", "status")

    sync_version: int = Field(ge=1)
    code: Code | None = None
    name: Name | None = None
    status: ProjectStatus | None = None
    site_id: UUID | None = None
    client_company_id: UUID | None = None
    classification_id: UUID | None = None
    template_id: UUID | None = None
    region: Region | None = None
    timezone: TimeZone | None = None
    currency: Currency | None = None


class ProjectOut(_Out):
    id: UUID
    code: str
    name: str
    status: ProjectStatus
    site_id: UUID | None
    client_company_id: UUID | None
    classification_id: UUID | None
    template_id: UUID | None
    region: str | None
    timezone: str | None
    currency: str | None
    closed_at: datetime | None
    sync_version: int
    created_at: datetime
    updated_at: datetime


class ProjectPage(_Out):
    items: list[ProjectOut]
    next_cursor: str | None


# --- sites ------------------------------------------------------------------------------------


class SiteCreate(_Model):
    code: Code
    name: Name
    lat: Latitude | None = None
    lng: Longitude | None = None
    timezone: TimeZone | None = None


class SiteUpdate(_Patch):
    """Only the fields sent are changed."""

    code: Code | None = None
    name: Name | None = None
    lat: Latitude | None = None
    lng: Longitude | None = None
    timezone: TimeZone | None = None


class SiteOut(_Out):
    id: UUID
    code: str
    name: str
    lat: Decimal | None
    lng: Decimal | None
    timezone: str | None
    is_system: bool
    created_at: datetime
    updated_at: datetime


class SitePage(_Out):
    items: list[SiteOut]
    next_cursor: str | None
