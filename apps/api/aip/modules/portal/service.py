"""Business logic for portal users and grants (PORTAL-01, ADR 0036 owner answers 2026-10-18).

Every operation runs in one ``with_tenant(get_context())`` transaction, so the row change, its
outbox event and the access-version bump (ADR 0020) commit or roll back together; a refused call
writes nothing. Rows of another tenant are invisible under RLS and come back as 404, never 403.

- ``invite``: the project admin's invitation is the only approval (no second approver). For each
  grant the inviter needs ``portal.user.invite`` and ``portal.grant.manage`` on the project (403),
  the project must be visible (404) and ``draft``/``active`` (422 ``PROJECT_CLOSED``) and the asset
  live (422 ``ASSET_NOT_FOUND``). Each grant's period is the project's ``portal_access_days``
  (``read_access_days``); the body cannot set an expiry. Identity's ``create_invite`` creates the
  ``app_user`` (``user_class = 'portal'``); its ``InviteError`` keeps its status and code.
- ``add_grant`` / ``renew`` / ``revoke``: ``portal.grant.manage`` on the grant's project. Renewing
  is allowed while the grant is live or expired (409 ``REVOKED`` once revoked) and sets another
  full period from now. A second revoke is 404.
- ``suspend`` (from ``invited``/``active``) ends every session through identity's
  ``revoke_all_for_user``; ``reinstate`` returns a user who has signed in to ``active``, else to
  ``invited``. Grants are kept: the provider gives a suspended user nothing.
- ``mark_signed_in`` (PORTAL-02): ``invited`` -> ``active`` and ``first_signed_in_at``; idempotent.

``read_access_days`` reads the project setting through ``ProjectsApi.get_setting`` (PROJECTS-04).
Until that task ships ``get_setting``, every project has the default period of 180 days.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.api import bump_access_version
from aip.modules.assets.api import AssetsApi
from aip.modules.identity import api as identity
from aip.modules.portal import policies
from aip.modules.portal import repository as repo
from aip.modules.portal.events import (
    PORTAL_GRANT_CREATED,
    PORTAL_GRANT_RENEWED,
    PORTAL_USER_INVITED,
    PORTAL_USER_STATUS_CHANGED,
    GrantCreated,
    GrantRenewed,
    PortalUserInvited,
    PortalUserStatusChanged,
    emit_grant_revoked,
)
from aip.modules.portal.schemas import GrantIn, GrantOut, InviteIn, PortalUserOut, PortalUserPage
from aip.modules.projects.api import ProjectsApi
from aip.platform.access import AccessPrincipal, PolicyService, Resource
from aip.platform.context import get_context, new_request_id
from aip.platform.db.errors import NotFoundError
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "OPEN_PROJECT_STATUSES",
    "PortalService",
    "grant_out",
    "live_grants",
    "mark_signed_in",
    "read_access_days",
    "user_out",
]

_UNIQUE_VIOLATION: Final = "23505"
OPEN_PROJECT_STATUSES: Final = frozenset({"draft", "active"})
ACCESS_DAYS_SETTING: Final = "portal_access_days"
# q also matches identity emails: at most this many matching portal users are looked up.
_EMAIL_MATCH_PAGES: Final = 10
_EMAIL_MATCH_PAGE_SIZE: Final = 100

SettingReader = Callable[[AsyncConnection, UUID, str], Awaitable[object]]


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _now() -> datetime:
    return datetime.now(UTC)


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


def _not_found(what: str) -> NotFoundError:
    return NotFoundError(f"{what} not found")


async def read_access_days(conn: AsyncConnection, project_id: UUID) -> int:
    """The project's portal access period: ``portal_access_days`` (1..400), else 180."""
    getter = cast("SettingReader | None", getattr(ProjectsApi(), "get_setting", None))
    value = None if getter is None else await getter(conn, project_id, ACCESS_DAYS_SETTING)
    return policies.access_days(value)


def grant_out(row: repo.Row, now: datetime) -> GrantOut:
    return GrantOut.model_validate({**row, "state": policies.grant_state(row, now)})


def user_out(
    row: repo.Row, grants: Iterable[repo.Row], email: str | None, now: datetime
) -> PortalUserOut:
    outs = [grant_out(g, now) for g in grants]
    live = [g.expires_at for g in outs if g.state == "live"]
    return PortalUserOut.model_validate(
        {
            **row,
            "email": email,
            "effective_status": policies.effective_status(row["status"], (g.state for g in outs)),
            "expires_at": max(live) if live else None,
            "grants": outs,
        }
    )


async def _user_out(conn: AsyncConnection, row: repo.Row) -> PortalUserOut:
    grants = await repo.unrevoked_grants(conn, [row["id"]])
    user = await identity.get_user(conn, row["user_id"])
    return user_out(row, grants, None if user is None else user.email, _now())


def _encode_cursor(last_id: UUID) -> str:
    return base64.urlsafe_b64encode(last_id.bytes).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str) -> UUID:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        return UUID(bytes=raw)
    except (binascii.Error, ValueError):
        raise DomainError(422, "INVALID_CURSOR", field="cursor") from None


@asynccontextmanager
async def _grant_unique() -> AsyncIterator[None]:
    """One live grant per user, project and subtree: a duplicate is 409 ``GRANT_EXISTS``."""
    try:
        yield
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION:
            raise DomainError(409, "GRANT_EXISTS") from None
        raise


async def _emit_status(conn: AsyncConnection, before: repo.Row, after: repo.Row) -> None:
    payload = PortalUserStatusChanged(
        portal_user_id=after["id"],
        user_id=after["user_id"],
        before=before["status"],
        after=after["status"],
    )
    await emit(
        conn,
        PORTAL_USER_STATUS_CHANGED,
        1,
        Aggregate("portal_user", after["id"]),
        payload.model_dump(mode="json"),
    )


async def mark_signed_in(conn: AsyncConnection, user_id: UUID) -> repo.Row | None:
    """The portal user's first sign-in makes them ``active`` (no other approval); idempotent.

    Any other status is left as it is. ``None`` when ``user_id`` is not a portal user here.
    """
    row = await repo.get_user_by_user_id(conn, user_id)
    if row is None or row["status"] != "invited":
        return row
    current = await repo.lock_user(conn, row["id"])
    if current is None or current["status"] != "invited":
        return current
    updated = await repo.update_user(
        conn, row["id"], {"status": "active", "first_signed_in_at": func.now()}
    )
    await _emit_status(conn, current, updated)
    await bump_access_version(conn)
    return updated


async def live_grants(conn: AsyncConnection, user_id: UUID) -> list[GrantOut]:
    """The live grants of identity user ``user_id`` (none when not a portal user here)."""
    row = await repo.get_user_by_user_id(conn, user_id)
    if row is None:
        return []
    now = _now()
    rows = await repo.unrevoked_grants(conn, [row["id"]])
    return [grant_out(g, now) for g in rows if policies.grant_state(g, now) == "live"]


class PortalService:
    """The admin operations, for ``principal`` (the caller) checked by ``policy``."""

    def __init__(self, policy: PolicyService, principal: AccessPrincipal) -> None:
        self._policy = policy
        self._principal = principal

    @property
    def _actor(self) -> UUID:
        if self._principal.actor_id is None:  # requires() only lets user principals through
            raise DomainError(403, "FORBIDDEN")
        return self._principal.actor_id

    async def _assert_on_project(self, project_id: UUID, *codes: str) -> None:
        resource = Resource(project_id=project_id, tenant_id=self._principal.tenant_id)
        for code in codes:
            await self._policy.assert_can(self._principal, code, resource)

    async def _check_target(self, conn: AsyncConnection, grant: GrantIn) -> None:
        project = await ProjectsApi().get_project(conn, grant.project_id)
        if project is None:
            raise _not_found(f"project {grant.project_id}")
        if project.status not in OPEN_PROJECT_STATUSES:
            raise DomainError(422, "PROJECT_CLOSED", projectId=str(grant.project_id))
        if grant.asset_id is not None and await AssetsApi().get_asset(conn, grant.asset_id) is None:
            raise DomainError(422, "ASSET_NOT_FOUND", assetId=str(grant.asset_id))

    async def _insert_grant(
        self, conn: AsyncConnection, portal_user_id: UUID, grant: GrantIn
    ) -> repo.Row:
        days = await read_access_days(conn, grant.project_id)
        async with _grant_unique():
            row = await repo.insert_grant(
                conn,
                {
                    "id": _new_id(),
                    "tenant_id": self._principal.tenant_id,
                    "portal_user_id": portal_user_id,
                    "project_id": grant.project_id,
                    "asset_id": grant.asset_id,
                    "actions": list(grant.actions),
                    "access_days": days,
                    "expires_at": func.now() + func.make_interval(0, 0, 0, days),
                    "created_by": self._actor,
                },
            )
        payload = GrantCreated(
            grant_id=row["id"],
            portal_user_id=portal_user_id,
            project_id=row["project_id"],
            asset_id=row["asset_id"],
            actions=list(row["actions"]),
            access_days=row["access_days"],
            expires_at=row["expires_at"],
        )
        await emit(
            conn,
            PORTAL_GRANT_CREATED,
            1,
            Aggregate("portal_grant", row["id"]),
            payload.model_dump(mode="json"),
            asset_id=row["asset_id"],
        )
        return row

    # --- invitations ----------------------------------------------------------------------------

    async def invite(self, body: InviteIn) -> PortalUserOut:
        # (a) the inviter's permission on every project first, so a project they cannot manage is
        # 403 whether or not they can see it.
        for grant in body.grants:
            await self._assert_on_project(
                grant.project_id, "portal.user.invite", "portal.grant.manage"
            )
        async with _tx() as conn:
            for grant in body.grants:
                await self._check_target(conn, grant)
            try:
                invite = await identity.create_invite(
                    conn,
                    tenant_id=self._principal.tenant_id,
                    email=body.email,
                    user_class="portal",
                    first_name=body.first_name,
                    last_name=body.last_name,
                    organisation_id=body.organisation_id,
                    invited_by=self._actor,
                )
            except identity.InviteError as exc:
                raise DomainError(exc.status_code, exc.code) from None
            invited = await identity.get_user(conn, invite.user_id)
            if invited is None or invited.user_class != "portal":
                # A pending staff invite for the same email: never turn it into a portal user.
                raise DomainError(409, "USER_EXISTS")
            if await repo.get_user_by_user_id(conn, invite.user_id) is not None:
                raise DomainError(409, "PORTAL_USER_EXISTS")
            user = await repo.insert_user(
                conn,
                {
                    "id": _new_id(),
                    "tenant_id": self._principal.tenant_id,
                    "user_id": invite.user_id,
                    "company_name": body.company_name,
                    "organisation_id": body.organisation_id,
                    "status": "invited",
                    "invited_by": self._actor,
                },
            )
            await emit(
                conn,
                PORTAL_USER_INVITED,
                1,
                Aggregate("portal_user", user["id"]),
                PortalUserInvited(
                    portal_user_id=user["id"],
                    user_id=invite.user_id,
                    organisation_id=body.organisation_id,
                    invited_by=self._actor,
                ).model_dump(mode="json"),
            )
            grants = [await self._insert_grant(conn, user["id"], grant) for grant in body.grants]
            await bump_access_version(conn)
        return user_out(user, grants, body.email, _now())

    # --- reads ----------------------------------------------------------------------------------

    async def list(
        self,
        *,
        status: str | None,
        q: str | None,
        cursor: str | None,
        limit: int,
        project_id: UUID | None = None,
        expiring_within_days: int | None = None,
    ) -> PortalUserPage:
        after = None if cursor is None else _decode_cursor(cursor)
        async with _tx() as conn:
            user_ids: list[UUID] = []
            if q:
                user_ids = await self._email_matches(conn, q)
            rows = await repo.list_users(
                conn,
                limit=limit,
                after=after,
                status=status,
                q=q,
                user_ids=user_ids,
                project_id=project_id,
                expiring_within=None
                if expiring_within_days is None
                else timedelta(days=expiring_within_days),
            )
            page = rows[:limit]
            grants = await repo.unrevoked_grants(conn, [r["id"] for r in page])
            emails: dict[UUID, str] = {}
            for row in page:
                user = await identity.get_user(conn, row["user_id"])
                if user is not None:
                    emails[row["user_id"]] = user.email
        now = _now()
        by_user: dict[UUID, list[repo.Row]] = {}
        for grant in grants:
            by_user.setdefault(grant["portal_user_id"], []).append(grant)
        items = [user_out(r, by_user.get(r["id"], []), emails.get(r["user_id"]), now) for r in page]
        more = len(rows) > limit
        return PortalUserPage(
            items=items, next_cursor=_encode_cursor(page[-1]["id"]) if more else None
        )

    @staticmethod
    async def _email_matches(conn: AsyncConnection, q: str) -> list[UUID]:
        """The ids of portal-class identity users whose email or name contains ``q``."""
        ids: list[UUID] = []
        cursor: str | None = None
        for _ in range(_EMAIL_MATCH_PAGES):
            page = await identity.list_users(
                conn, q=q, user_class="portal", cursor=cursor, limit=_EMAIL_MATCH_PAGE_SIZE
            )
            ids.extend(user.id for user in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        return ids

    async def get(self, portal_user_id: UUID) -> PortalUserOut:
        async with _tx() as conn:
            row = await repo.get_user(conn, portal_user_id)
            if row is None:
                raise _not_found(f"portal user {portal_user_id}")
            return await _user_out(conn, row)

    # --- grants ---------------------------------------------------------------------------------

    async def add_grant(self, portal_user_id: UUID, body: GrantIn) -> GrantOut:
        await self._assert_on_project(body.project_id, "portal.grant.manage")
        async with _tx() as conn:
            user = await repo.lock_user(conn, portal_user_id)
            if user is None:
                raise _not_found(f"portal user {portal_user_id}")
            await self._check_target(conn, body)
            row = await self._insert_grant(conn, portal_user_id, body)
            await bump_access_version(conn)
        return grant_out(row, _now())

    async def _grant_of(
        self, conn: AsyncConnection, portal_user_id: UUID, grant_id: UUID
    ) -> repo.Row:
        grant = await repo.get_grant(conn, grant_id, lock=True)
        if grant is None or grant["portal_user_id"] != portal_user_id:
            raise _not_found(f"grant {grant_id}")
        await self._assert_on_project(grant["project_id"], "portal.grant.manage")
        return grant

    async def renew(self, portal_user_id: UUID, grant_id: UUID) -> GrantOut:
        async with _tx() as conn:
            grant = await self._grant_of(conn, portal_user_id, grant_id)
            if grant["revoked_at"] is not None:
                raise DomainError(409, "REVOKED")
            project = await ProjectsApi().get_project(conn, grant["project_id"])
            if project is None or project.status not in OPEN_PROJECT_STATUSES:
                raise DomainError(422, "PROJECT_CLOSED", projectId=str(grant["project_id"]))
            days = await read_access_days(conn, grant["project_id"])
            row = await repo.renew_grant(conn, grant_id, access_days=days, renewed_by=self._actor)
            await emit(
                conn,
                PORTAL_GRANT_RENEWED,
                1,
                Aggregate("portal_grant", grant_id),
                GrantRenewed(
                    grant_id=grant_id,
                    portal_user_id=portal_user_id,
                    project_id=row["project_id"],
                    expires_at=row["expires_at"],
                    renewed_by=self._actor,
                ).model_dump(mode="json"),
                asset_id=row["asset_id"],
            )
            await bump_access_version(conn)
        return grant_out(row, _now())

    async def revoke(self, portal_user_id: UUID, grant_id: UUID) -> None:
        async with _tx() as conn:
            grant = await self._grant_of(conn, portal_user_id, grant_id)
            row = await repo.revoke_grant(
                conn, grant["id"], reason="manual", revoked_by=self._actor
            )
            if row is None:  # already revoked: as absent
                raise _not_found(f"grant {grant_id}")
            await emit_grant_revoked(conn, row, "manual")
            await bump_access_version(conn)

    # --- lifecycle ------------------------------------------------------------------------------

    async def suspend(self, portal_user_id: UUID, reason: str) -> PortalUserOut:
        async with _tx() as conn:
            current = await repo.lock_user(conn, portal_user_id)
            if current is None:
                raise _not_found(f"portal user {portal_user_id}")
            if current["status"] not in policies.SUSPENDABLE:
                raise DomainError(409, "INVALID_STATUS", status=current["status"])
            updated = await repo.update_user(
                conn,
                portal_user_id,
                {"status": "suspended", "suspended_at": func.now(), "suspended_reason": reason},
            )
            await identity.revoke_all_for_user(conn, updated["user_id"], "portal_suspended")
            await _emit_status(conn, current, updated)
            await bump_access_version(conn)
            return await _user_out(conn, updated)

    async def reinstate(self, portal_user_id: UUID) -> PortalUserOut:
        async with _tx() as conn:
            current = await repo.lock_user(conn, portal_user_id)
            if current is None:
                raise _not_found(f"portal user {portal_user_id}")
            if current["status"] != "suspended":
                raise DomainError(409, "INVALID_STATUS", status=current["status"])
            status = policies.reinstated_status(current["first_signed_in_at"])
            patch: dict[str, Any] = {
                "status": status,
                "suspended_at": None,
                "suspended_reason": None,
            }
            updated = await repo.update_user(conn, portal_user_id, patch)
            await _emit_status(conn, current, updated)
            await bump_access_version(conn)
            return await _user_out(conn, updated)
