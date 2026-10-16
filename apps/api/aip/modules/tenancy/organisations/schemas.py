"""Pydantic request/response models for organisations (TENANCY-03).

JSON uses camelCase (``syncVersion``, ``registrationNumber``); the column ``org_type`` is ``type``
on the wire. Types and statuses are stable codes; their labels are terminology keys in the UI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

__all__ = [
    "OrganisationCreate",
    "OrganisationErrorBody",
    "OrganisationList",
    "OrganisationOut",
    "OrganisationStatus",
    "OrganisationType",
    "OrganisationUpdate",
]

OrganisationType = Literal["owner", "client", "subcontractor"]
OrganisationStatus = Literal["active", "inactive"]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
RegistrationNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    """A response: built from database rows, so columns the API does not show are ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class OrganisationErrorBody(_Out):
    """A domain error: a stable ``code`` (``ORGANISATION_NAME_TAKEN``, ``NOT_FOUND``, ...)."""

    code: str


class OrganisationCreate(_Model):
    name: Name
    org_type: OrganisationType = Field(alias="type")
    registration_number: RegistrationNumber | None = None


class OrganisationUpdate(_Model):
    """Only the fields sent are changed; ``syncVersion`` is the version the client last read."""

    REQUIRED: ClassVar[tuple[str, ...]] = ("name", "org_type", "status")

    sync_version: int = Field(ge=1)
    name: Name | None = None
    org_type: OrganisationType | None = Field(default=None, alias="type")
    registration_number: RegistrationNumber | None = None
    status: OrganisationStatus | None = None

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


class OrganisationOut(_Out):
    id: UUID
    name: str
    org_type: OrganisationType = Field(alias="type")
    registration_number: str | None
    status: OrganisationStatus
    sync_version: int
    created_at: datetime
    updated_at: datetime


class OrganisationList(_Out):
    """Every live organisation that matches, by name (a tenant has tens, not thousands)."""

    items: list[OrganisationOut]
