"""Domain events the portal module publishes and subscribes to (via the outbox, ADR 0003).

Published (all v1; payloads carry ids, codes and timestamps only, never an email or company name):

- ``portal_user.invited`` ``{portalUserId, userId, organisationId, invitedBy}``;
- ``portal_user.status_changed`` ``{portalUserId, userId, before, after}`` (status codes);
- ``portal_grant.created`` ``{grantId, portalUserId, projectId, assetId, actions, accessDays,
  expiresAt}``;
- ``portal_grant.renewed`` ``{grantId, portalUserId, projectId, expiresAt, renewedBy}``;
- ``portal_grant.revoked`` ``{grantId, portalUserId, projectId, assetId, reason}``.

Each is emitted in the same transaction as its row change, so the audit writer (AUDIT-02) records
it. Subscribed: ``project.archived`` v1. The handler revokes every live grant of the project with
reason ``project_closed``, one ``portal_grant.revoked`` per grant, and bumps the access version. It
is idempotent on the event: a redelivery finds the grants already revoked and does nothing.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.api import bump_access_version
from aip.modules.portal import repository as repo
from aip.platform.events import Aggregate, emit, register_event
from aip.platform.events.subscribers import DomainEvent, subscriber

__all__ = [
    "PORTAL_GRANT_CREATED",
    "PORTAL_GRANT_RENEWED",
    "PORTAL_GRANT_REVOKED",
    "PORTAL_USER_INVITED",
    "PORTAL_USER_STATUS_CHANGED",
    "GrantCreated",
    "GrantRenewed",
    "GrantRevoked",
    "PortalUserInvited",
    "PortalUserStatusChanged",
    "emit_grant_revoked",
    "revoke_on_project_archived",
]

PORTAL_USER_INVITED = "portal_user.invited"
PORTAL_USER_STATUS_CHANGED = "portal_user.status_changed"
PORTAL_GRANT_CREATED = "portal_grant.created"
PORTAL_GRANT_RENEWED = "portal_grant.renewed"
PORTAL_GRANT_REVOKED = "portal_grant.revoked"


class _Payload(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class PortalUserInvited(_Payload):
    portal_user_id: UUID
    user_id: UUID
    organisation_id: UUID | None
    invited_by: UUID


class PortalUserStatusChanged(_Payload):
    portal_user_id: UUID
    user_id: UUID
    before: str
    after: str


class GrantCreated(_Payload):
    grant_id: UUID
    portal_user_id: UUID
    project_id: UUID
    asset_id: UUID | None
    actions: list[str]
    access_days: int
    expires_at: datetime


class GrantRenewed(_Payload):
    grant_id: UUID
    portal_user_id: UUID
    project_id: UUID
    expires_at: datetime
    renewed_by: UUID


class GrantRevoked(_Payload):
    grant_id: UUID
    portal_user_id: UUID
    project_id: UUID
    asset_id: UUID | None
    reason: str


register_event(PORTAL_USER_INVITED, 1, PortalUserInvited, "portal")
register_event(PORTAL_USER_STATUS_CHANGED, 1, PortalUserStatusChanged, "portal")
register_event(PORTAL_GRANT_CREATED, 1, GrantCreated, "portal")
register_event(PORTAL_GRANT_RENEWED, 1, GrantRenewed, "portal")
register_event(PORTAL_GRANT_REVOKED, 1, GrantRevoked, "portal")


async def emit_grant_revoked(conn: AsyncConnection, grant: repo.Row, reason: str) -> None:
    """``portal_grant.revoked`` v1 for ``grant`` (a revoked ``portal_grants`` row)."""
    payload = GrantRevoked(
        grant_id=grant["id"],
        portal_user_id=grant["portal_user_id"],
        project_id=grant["project_id"],
        asset_id=grant["asset_id"],
        reason=reason,
    )
    await emit(
        conn,
        PORTAL_GRANT_REVOKED,
        1,
        Aggregate("portal_grant", grant["id"]),
        payload.model_dump(mode="json"),
        asset_id=grant["asset_id"],
    )


@subscriber("project.archived", 1)
async def revoke_on_project_archived(conn: AsyncConnection, event: DomainEvent) -> None:
    """A closed project ends its portal access: revoke its live grants (``project_closed``)."""
    raw = event.payload.get("projectId")
    if raw is None:
        return
    revoked = await repo.revoke_project_grants(
        conn, UUID(str(raw)), reason="project_closed", revoked_by=event.actor_id
    )
    for grant in revoked:
        await emit_grant_revoked(conn, grant, "project_closed")
    if revoked:
        await bump_access_version(conn)
