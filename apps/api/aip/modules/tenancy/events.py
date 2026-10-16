"""Domain events the tenancy module publishes (via the outbox, ADR 0003).

``tenant.entitlements_changed`` v1 (ENT-01): written in the same ``with_tenant`` transaction as
every subscription or override change, including the nightly removal of expired overrides.
ARCH-08 and other API instances subscribe to it to drop cached decisions. The payload is the audit
record until AUDIT-01: ``{tenantId, entitlementVersion, change, key, before, after, reason}``,
where ``before``/``after`` hold the changed record in camelCase (``null`` when there was none).

``tenancy.organisation_created`` and ``tenancy.organisation_updated`` v1 (TENANCY-03) share one
payload: ``{organisationId, name, type, status, before, after}``, where ``before``/``after`` hold
the changed fields in camelCase (``null`` on create).
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = [
    "ORGANISATION_CREATED",
    "ORGANISATION_UPDATED",
    "TENANT_ENTITLEMENTS_CHANGED",
    "EntitlementsChanged",
    "OrganisationEvent",
]

TENANT_ENTITLEMENTS_CHANGED = "tenant.entitlements_changed"

EntitlementChange = Literal[
    "subscription", "override_added", "override_removed", "override_expired"
]


class EntitlementsChanged(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )

    tenant_id: UUID
    entitlement_version: int
    change: EntitlementChange
    key: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    reason: str | None = None


register_event(TENANT_ENTITLEMENTS_CHANGED, 1, EntitlementsChanged, "tenancy")


ORGANISATION_CREATED = "tenancy.organisation_created"
ORGANISATION_UPDATED = "tenancy.organisation_updated"


class OrganisationEvent(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )

    organisation_id: UUID
    name: str
    type: str
    status: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


for _name in (ORGANISATION_CREATED, ORGANISATION_UPDATED):
    register_event(_name, 1, OrganisationEvent, "tenancy")
