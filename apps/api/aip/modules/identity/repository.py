"""Data access for identity (ADR 0002, 0005).

**Login directory** (IDENTITY-01): reads go only through the SECURITY DEFINER function
``identity_resolve_login``; ``aip_app`` cannot select from ``login_directory``. This runs before
any tenant is known, so it uses the platform's ``before_tenant()`` connection (``aip_app``, no
tenant set) instead of ``with_tenant``. Local-account emails are written only through
``identity_register_email`` (IDENTITY-02), inside the tenant's own transaction.

**Users, memberships, auth events** (IDENTITY-02): every function takes the tenant-bound
connection from ``with_tenant`` and never opens its own. RLS is the isolation; every query also
filters on the bound tenant (``app.tenant_id``) as a second line, so a query can never widen to
another tenant even if a policy were dropped.

**Invites, MFA enrolment, sign-off policy** (IDENTITY-04): same rules. Invites are revoked, never
deleted; ``signoff_policy`` rows are upserted per ``(tenant, action_code)``.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy import ColumnElement, Select, Uuid, cast, func, insert, or_, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.identity.tables import (
    app_user,
    auth_event,
    signoff_policy,
    tenant_membership,
    user_invite,
)
from aip.platform.context import new_request_id
from aip.platform.db.errors import NotFoundError
from aip.platform.db.session import before_tenant

LookupKind = Literal["email_domain", "tenant_slug", "email"]
UserStatus = Literal["invited", "active", "deactivated"]
UserClass = Literal["staff", "field", "portal"]
MembershipType = Literal["member", "client", "subcontractor", "guest"]
MAX_PAGE = 100

_RESOLVE = text("SELECT tenant_id, idp_alias FROM identity_resolve_login(:kind, :key)")


@dataclass(frozen=True)
class LoginTarget:
    tenant_id: UUID
    idp_alias: str | None


class LoginDirectory(Protocol):
    async def resolve(self, kind: LookupKind, key: str) -> LoginTarget | None: ...


async def resolve_login(conn: AsyncConnection, kind: LookupKind, key: str) -> LoginTarget | None:
    row = (await conn.execute(_RESOLVE, {"kind": kind, "key": key})).first()
    if row is None:
        return None
    return LoginTarget(tenant_id=row[0], idp_alias=row[1])


Connect = Callable[[], AbstractAsyncContextManager[AsyncConnection]]


class SqlLoginDirectory:
    """``LoginDirectory`` over Postgres; ``connect`` defaults to ``before_tenant``."""

    def __init__(self, connect: Connect = before_tenant) -> None:
        self._connect = connect

    async def resolve(self, kind: LookupKind, key: str) -> LoginTarget | None:
        async with self._connect() as conn:
            return await resolve_login(conn, kind, key)


# --- users, memberships and auth events (IDENTITY-02) ------------------------------------------


def new_id() -> UUID:
    """A UUIDv7 generated in the app (ADR 0002), from the platform's generator (ARCH-04)."""
    return UUID(new_request_id())


def _bound_tenant() -> ColumnElement[Any]:
    """The tenant bound by ``with_tenant`` (NULL when unset, which then matches nothing)."""
    return cast(func.nullif(func.current_setting("app.tenant_id", True), ""), Uuid)


_NIL = UUID(int=0)


@dataclass(frozen=True)
class UserRow:
    """An ``app_user`` row as identity's services see it (defaults serve the pure unit tests)."""

    id: UUID = _NIL
    tenant_id: UUID = _NIL
    email: str = ""
    display_name: str = ""
    user_class: UserClass = "staff"
    status: UserStatus = "active"
    sso_managed: bool = False
    keycloak_user_id: UUID | None = None
    idp_alias: str | None = None
    organisation_id: UUID | None = None
    deactivated_at: datetime | None = None
    last_login_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def deleted(self) -> bool:
        return self.deleted_at is not None


@dataclass(frozen=True)
class MembershipRow:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    organisation_id: UUID | None
    membership_type: MembershipType
    valid_from: date
    valid_to: date | None


_USER_COLUMNS = (
    app_user.c.id,
    app_user.c.tenant_id,
    app_user.c.email,
    app_user.c.display_name,
    app_user.c.user_class,
    app_user.c.status,
    app_user.c.sso_managed,
    app_user.c.keycloak_user_id,
    app_user.c.idp_alias,
    app_user.c.organisation_id,
    app_user.c.deactivated_at,
    app_user.c.last_login_at,
    app_user.c.deleted_at,
)


def _user(row: Mapping[Any, Any]) -> UserRow:
    return UserRow(**{c.name: row[c.name] for c in _USER_COLUMNS})


def _users_in_bound_tenant() -> Select[*tuple[Any, ...]]:
    return select(*_USER_COLUMNS).where(app_user.c.tenant_id == _bound_tenant())


async def _one_user(conn: AsyncConnection, stmt: Select[*tuple[Any, ...]]) -> UserRow | None:
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else _user(row)


async def get_user(conn: AsyncConnection, user_id: UUID) -> UserRow | None:
    """The live user ``user_id`` in the bound tenant, or ``None`` (also for another tenant's id)."""
    stmt = _users_in_bound_tenant().where(app_user.c.id == user_id, app_user.c.deleted_at.is_(None))
    return await _one_user(conn, stmt)


async def get_display_names(conn: AsyncConnection, user_ids: Iterable[UUID]) -> dict[UUID, str]:
    """``{user id: display name}`` for the given users of the bound tenant (IDENTITY-09).

    Reports and registers print who signed or approved, long after the fact, so deactivated and
    soft-deleted users keep their name here. Ids of another tenant or unknown ids are left out.
    Only the display name is read: no email or other PII.
    """
    ids = set(user_ids)
    if not ids:
        return {}
    stmt = select(app_user.c.id, app_user.c.display_name).where(
        app_user.c.tenant_id == _bound_tenant(), app_user.c.id.in_(ids)
    )
    return {row.id: row.display_name for row in await conn.execute(stmt)}


async def find_by_email(conn: AsyncConnection, email: str) -> UserRow | None:
    """The live user with ``email`` (case-insensitive, citext) in the bound tenant, or ``None``."""
    stmt = _users_in_bound_tenant().where(
        app_user.c.email == email.strip(), app_user.c.deleted_at.is_(None)
    )
    return await _one_user(conn, stmt)


async def find_deleted_by_email(conn: AsyncConnection, email: str) -> UserRow | None:
    """The most recently soft-deleted user with ``email`` in the bound tenant, or ``None``."""
    stmt = (
        _users_in_bound_tenant()
        .where(app_user.c.email == email.strip(), app_user.c.deleted_at.is_not(None))
        .order_by(app_user.c.deleted_at.desc())
        .limit(1)
    )
    return await _one_user(conn, stmt)


async def find_by_keycloak_user_id(conn: AsyncConnection, keycloak_user_id: UUID) -> UserRow | None:
    """The user (live or soft-deleted) linked to this Keycloak user in the bound tenant."""
    stmt = _users_in_bound_tenant().where(app_user.c.keycloak_user_id == keycloak_user_id)
    return await _one_user(conn, stmt)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def encode_cursor(user_id: UUID) -> str:
    return base64.urlsafe_b64encode(user_id.bytes).decode().rstrip("=")


def decode_cursor(cursor: str) -> UUID:
    """``ValueError`` for anything that is not a cursor this module produced."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid cursor") from exc
    if len(raw) != 16:
        raise ValueError("invalid cursor")
    return UUID(bytes=raw)


@dataclass(frozen=True)
class UserPage:
    items: list[UserRow]
    next_cursor: str | None


async def list_users(
    conn: AsyncConnection,
    *,
    q: str | None = None,
    status: UserStatus | None = None,
    user_class: UserClass | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> UserPage:
    """Live users of the bound tenant, oldest first (UUIDv7 ids sort by time), keyset-paged.

    ``q`` matches a substring of the email or display name (case-insensitive). ``limit`` is
    1..100 (``ValueError`` otherwise); ``cursor`` is the ``next_cursor`` of the previous page.
    """
    if not 1 <= limit <= MAX_PAGE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE}")
    stmt = _users_in_bound_tenant().where(app_user.c.deleted_at.is_(None))
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                app_user.c.email.ilike(pattern, escape="\\"),
                app_user.c.display_name.ilike(pattern, escape="\\"),
            )
        )
    if status is not None:
        stmt = stmt.where(app_user.c.status == status)
    if user_class is not None:
        stmt = stmt.where(app_user.c.user_class == user_class)
    if cursor is not None:
        stmt = stmt.where(app_user.c.id > decode_cursor(cursor))
    stmt = stmt.order_by(app_user.c.id).limit(limit + 1)
    rows = [_user(r) for r in (await conn.execute(stmt)).mappings().all()]
    items = rows[:limit]
    more = len(rows) > limit
    return UserPage(items=items, next_cursor=encode_cursor(items[-1].id) if more else None)


async def insert_user(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    email: str,
    display_name: str,
    user_class: UserClass,
    status: UserStatus,
    sso_managed: bool,
    idp_alias: str | None = None,
    keycloak_user_id: UUID | None = None,
    organisation_id: UUID | None = None,
    last_login_at: Any = None,
) -> UUID:
    user_id = new_id()
    await conn.execute(
        insert(app_user).values(
            id=user_id,
            tenant_id=tenant_id,
            email=email.strip(),
            display_name=display_name,
            user_class=user_class,
            status=status,
            sso_managed=sso_managed,
            idp_alias=idp_alias,
            keycloak_user_id=keycloak_user_id,
            organisation_id=organisation_id,
            last_login_at=last_login_at,
        )
    )
    return user_id


async def ensure_invited_sso_user(
    conn: AsyncConnection, *, tenant_id: UUID, email: str, idp_alias: str
) -> UUID:
    """The live user with ``email`` in the bound tenant; else a new ``invited`` SSO user.

    Dev and demo bootstrap only (TESTING-09): the new user has a ``member`` membership and no
    Keycloak link, so the first SSO sign-in with that verified email links it (``decide_jit``
    ``LINK``) and keeps any role assigned beforehand. Idempotent. ``ValueError`` for an existing
    local or deactivated account (it could never use a role given here).
    """
    existing = await find_by_email(conn, email)
    if existing is not None:
        if not existing.sso_managed or existing.status == "deactivated":
            raise ValueError(f"{email} exists as a local or deactivated account; not bootstrapped")
        return existing.id
    user_id = await insert_user(
        conn,
        tenant_id=tenant_id,
        email=email,
        display_name=email.split("@", 1)[0][:200],
        user_class="staff",
        status="invited",
        sso_managed=True,
        idp_alias=idp_alias,
    )
    await insert_membership(conn, tenant_id=tenant_id, user_id=user_id, membership_type="member")
    return user_id


async def update_user(conn: AsyncConnection, user_id: UUID, **values: Any) -> None:
    """Set ``values`` on the live user ``user_id`` (bumps ``updated_at`` and ``sync_version``).

    ``NotFoundError`` when no live user ``user_id`` exists in the bound tenant.
    """
    stmt = (
        update(app_user)
        .where(
            app_user.c.id == user_id,
            app_user.c.tenant_id == _bound_tenant(),
            app_user.c.deleted_at.is_(None),
        )
        .values(updated_at=func.now(), sync_version=app_user.c.sync_version + 1, **values)
        .returning(app_user.c.id)
    )
    if (await conn.execute(stmt)).first() is None:
        raise NotFoundError(f"app_user {user_id} not found")


async def set_user_status(conn: AsyncConnection, user_id: UUID, status: UserStatus) -> UserRow:
    """Change a live user's status; ``deactivated`` stamps ``deactivated_at``, others clear it.

    Any status other than ``active`` also revokes every session of the user in the same
    transaction (IDENTITY-03), so a later reactivation cannot revive an old cookie.
    ``NotFoundError`` when no live user ``user_id`` exists in the bound tenant.
    """
    if status not in ("invited", "active", "deactivated"):
        raise ValueError("unknown user status")
    await update_user(
        conn,
        user_id,
        status=status,
        deactivated_at=func.now() if status == "deactivated" else None,
    )
    user = await get_user(conn, user_id)
    if user is None:  # pragma: no cover - updated just above in the same transaction
        raise NotFoundError(f"app_user {user_id} not found")
    if status != "active":
        from aip.modules.identity.sessions import revoke_all_for_user

        await revoke_all_for_user(conn, user_id, f"user_{status}")
    return user


async def insert_membership(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    membership_type: MembershipType,
    valid_from: date | None = None,
    valid_to: date | None = None,
    organisation_id: UUID | None = None,
) -> UUID:
    membership_id = new_id()
    values: dict[str, Any] = {
        "id": membership_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "organisation_id": organisation_id,
        "membership_type": membership_type,
        "valid_to": valid_to,
    }
    if valid_from is not None:
        values["valid_from"] = valid_from
    await conn.execute(insert(tenant_membership).values(**values))
    return membership_id


async def list_memberships(conn: AsyncConnection, user_id: UUID) -> list[MembershipRow]:
    """The user's live memberships in the bound tenant (any validity), oldest first."""
    stmt = (
        select(
            tenant_membership.c.id,
            tenant_membership.c.tenant_id,
            tenant_membership.c.user_id,
            tenant_membership.c.organisation_id,
            tenant_membership.c.membership_type,
            tenant_membership.c.valid_from,
            tenant_membership.c.valid_to,
        )
        .where(
            tenant_membership.c.user_id == user_id,
            tenant_membership.c.tenant_id == _bound_tenant(),
            tenant_membership.c.deleted_at.is_(None),
        )
        .order_by(tenant_membership.c.id)
    )
    return [MembershipRow(**dict(r)) for r in (await conn.execute(stmt)).mappings().all()]


async def has_current_membership(conn: AsyncConnection, user_id: UUID) -> bool:
    """True when the user has a live membership valid today (``valid_from..valid_to``)."""
    today = func.current_date()
    stmt = (
        select(tenant_membership.c.id)
        .where(
            tenant_membership.c.user_id == user_id,
            tenant_membership.c.tenant_id == _bound_tenant(),
            tenant_membership.c.deleted_at.is_(None),
            tenant_membership.c.valid_from <= today,
            or_(tenant_membership.c.valid_to.is_(None), tenant_membership.c.valid_to >= today),
        )
        .limit(1)
    )
    return (await conn.execute(stmt)).first() is not None


async def record_auth_event(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    event_type: str,
    user_id: UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> UUID:
    """Append one ``auth_event`` (``aip_app`` may only INSERT and SELECT it).

    ``detail`` must never hold a token, password or secret; callers pass reasons and codes.
    """
    event_id = new_id()
    await conn.execute(
        insert(auth_event).values(
            id=event_id,
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            ip=ip,
            user_agent=None if user_agent is None else user_agent[:512],
            detail=dict(detail or {}),
        )
    )
    return event_id


async def list_auth_events(
    conn: AsyncConnection, *, user_id: UUID | None = None, limit: int = 100
) -> Sequence[Mapping[str, Any]]:
    """Recent auth events of the bound tenant (newest first), optionally for one user."""
    stmt = select(auth_event).where(auth_event.c.tenant_id == _bound_tenant())
    if user_id is not None:
        stmt = stmt.where(auth_event.c.user_id == user_id)
    stmt = stmt.order_by(auth_event.c.occurred_at.desc(), auth_event.c.id.desc()).limit(limit)
    return [dict(r) for r in (await conn.execute(stmt)).mappings().all()]


class EmailInOtherTenantError(Exception):
    """The email is already registered to another tenant's local account."""


class EmailDomainSsoError(Exception):
    """The email's domain belongs to an SSO IdP, so it cannot be a local account (IDENTITY-04)."""


_REGISTER = text("SELECT identity_register_email(CAST(:email AS citext), :tenant_id)")


async def register_email(conn: AsyncConnection, email: str, tenant_id: UUID) -> None:
    """Map a local account's email to the bound tenant in ``login_directory``.

    ``EmailInOtherTenantError`` when another tenant already holds the email,
    ``EmailDomainSsoError`` when an SSO IdP claims its domain. Any error aborts the surrounding
    transaction, so the user change that needed the registration rolls back with it.
    """
    try:
        await conn.execute(_REGISTER, {"email": email.strip(), "tenant_id": tenant_id})
    except DBAPIError as exc:
        if "EMAIL_IN_OTHER_TENANT" in str(exc.orig):
            raise EmailInOtherTenantError("email is registered to another tenant") from None
        if "EMAIL_DOMAIN_SSO" in str(exc.orig):
            raise EmailDomainSsoError("the email domain signs in with company SSO") from None
        raise


_LOCK = text("SELECT pg_advisory_xact_lock(:key)")


async def advisory_xact_lock(conn: AsyncConnection, key: int) -> None:
    """``pg_advisory_xact_lock(key)``: held until the transaction ends."""
    await conn.execute(_LOCK, {"key": key})


# --- MFA enrolment (IDENTITY-04) ---------------------------------------------------------------

_MFA_ENROLLED = text(
    "UPDATE app_user SET mfa_enrolled_at = now(), updated_at = now(),"
    " sync_version = sync_version + 1"
    " WHERE id = :id AND mfa_enrolled_at IS NULL"
    " AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)
_MFA_CLEARED = text(
    "UPDATE app_user SET mfa_enrolled_at = NULL, updated_at = now(),"
    " sync_version = sync_version + 1"
    " WHERE id = :id AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)
_MFA_READ = text(
    "SELECT mfa_enrolled_at FROM app_user WHERE id = :id"
    " AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)


async def mark_mfa_enrolled(conn: AsyncConnection, user_id: UUID) -> None:
    """Stamp ``mfa_enrolled_at`` the first time an ``aal=2`` session is issued for the user."""
    await conn.execute(_MFA_ENROLLED, {"id": user_id})


async def clear_mfa_enrolled(conn: AsyncConnection, user_id: UUID) -> None:
    await conn.execute(_MFA_CLEARED, {"id": user_id})


async def mfa_enrolled_at(conn: AsyncConnection, user_id: UUID) -> datetime | None:
    return (await conn.execute(_MFA_READ, {"id": user_id})).scalar_one_or_none()


# --- invites (IDENTITY-04) ---------------------------------------------------------------------

InviteStatus = Literal["pending", "sent", "accepted", "revoked", "failed"]
InviteMethod = Literal["local", "sso"]
LIVE_INVITE_STATUSES: tuple[InviteStatus, ...] = ("pending", "sent")


@dataclass(frozen=True)
class InviteRow:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    email: str
    user_class: UserClass
    organisation_id: UUID | None
    invited_by: UUID | None
    method: InviteMethod
    keycloak_user_id: UUID | None
    status: InviteStatus
    last_error: str | None
    expires_at: datetime
    sent_at: datetime | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


_INVITE_COLUMNS = tuple(user_invite.c[name] for name in InviteRow.__dataclass_fields__)


def _invites_in_bound_tenant() -> Select[*tuple[Any, ...]]:
    return select(*_INVITE_COLUMNS).where(
        user_invite.c.tenant_id == _bound_tenant(), user_invite.c.deleted_at.is_(None)
    )


def _invite(row: Mapping[Any, Any]) -> InviteRow:
    return InviteRow(**{c.name: row[c.name] for c in _INVITE_COLUMNS})


async def insert_invite(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    email: str,
    user_class: UserClass,
    method: InviteMethod,
    expires_at: Any,
    organisation_id: UUID | None = None,
    invited_by: UUID | None = None,
) -> UUID:
    invite_id = new_id()
    await conn.execute(
        insert(user_invite).values(
            id=invite_id,
            tenant_id=tenant_id,
            user_id=user_id,
            email=email.strip(),
            user_class=user_class,
            organisation_id=organisation_id,
            invited_by=invited_by,
            method=method,
            status="pending",
            expires_at=expires_at,
        )
    )
    return invite_id


async def get_invite(
    conn: AsyncConnection, invite_id: UUID, *, for_update: bool = False
) -> InviteRow | None:
    stmt = _invites_in_bound_tenant().where(user_invite.c.id == invite_id)
    if for_update:
        stmt = stmt.with_for_update()
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else _invite(row)


async def latest_invite_for_user(conn: AsyncConnection, user_id: UUID) -> InviteRow | None:
    """The user's most recent invite in the bound tenant, or ``None`` (never invited)."""
    stmt = (
        _invites_in_bound_tenant()
        .where(user_invite.c.user_id == user_id)
        .order_by(user_invite.c.created_at.desc(), user_invite.c.id.desc())
        .limit(1)
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else _invite(row)


async def list_invites(
    conn: AsyncConnection, *, status: InviteStatus | None = None, limit: int = MAX_PAGE
) -> list[InviteRow]:
    """Invites of the bound tenant, newest first (at most ``limit``)."""
    if not 1 <= limit <= MAX_PAGE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE}")
    stmt = _invites_in_bound_tenant()
    if status is not None:
        stmt = stmt.where(user_invite.c.status == status)
    stmt = stmt.order_by(user_invite.c.created_at.desc(), user_invite.c.id.desc()).limit(limit)
    return [_invite(r) for r in (await conn.execute(stmt)).mappings().all()]


async def update_invite(conn: AsyncConnection, invite_id: UUID, **values: Any) -> None:
    stmt = (
        update(user_invite)
        .where(
            user_invite.c.id == invite_id,
            user_invite.c.tenant_id == _bound_tenant(),
            user_invite.c.deleted_at.is_(None),
        )
        .values(updated_at=func.now(), **values)
        .returning(user_invite.c.id)
    )
    if (await conn.execute(stmt)).first() is None:
        raise NotFoundError(f"user_invite {invite_id} not found")


async def revoke_live_invites(conn: AsyncConnection, email: str) -> list[UUID]:
    """Revoke every ``pending``/``sent`` invite for ``email`` in the bound tenant."""
    stmt = (
        update(user_invite)
        .where(
            user_invite.c.email == email.strip(),
            user_invite.c.tenant_id == _bound_tenant(),
            user_invite.c.deleted_at.is_(None),
            user_invite.c.status.in_(LIVE_INVITE_STATUSES),
        )
        .values(status="revoked", revoked_at=func.now(), updated_at=func.now())
        .returning(user_invite.c.id)
    )
    return [r[0] for r in (await conn.execute(stmt)).all()]


async def set_keycloak_link(conn: AsyncConnection, user_id: UUID, keycloak_user_id: UUID) -> None:
    """Link an invited user to the Keycloak account the invite job created (a column update, so
    the job role needs no wider grant on ``app_user``)."""
    await conn.execute(
        update(app_user)
        .where(
            app_user.c.id == user_id,
            app_user.c.tenant_id == _bound_tenant(),
            app_user.c.deleted_at.is_(None),
        )
        .values(
            keycloak_user_id=keycloak_user_id,
            updated_at=func.now(),
            sync_version=app_user.c.sync_version + 1,
        )
    )


# --- sign-off policy (IDENTITY-04 Part D) ------------------------------------------------------


@dataclass(frozen=True)
class SignoffPolicyRow:
    action_code: str
    min_aal: int
    step_up_max_age_min: int
    updated_by: UUID | None = None
    updated_at: datetime | None = None


_POLICY_COLUMNS = (
    signoff_policy.c.action_code,
    signoff_policy.c.min_aal,
    signoff_policy.c.step_up_max_age_min,
    signoff_policy.c.updated_by,
    signoff_policy.c.updated_at,
)


def _policies_in_bound_tenant() -> Select[*tuple[Any, ...]]:
    return select(*_POLICY_COLUMNS).where(
        signoff_policy.c.tenant_id == _bound_tenant(), signoff_policy.c.deleted_at.is_(None)
    )


async def get_signoff_policy(conn: AsyncConnection, action_code: str) -> SignoffPolicyRow | None:
    stmt = _policies_in_bound_tenant().where(signoff_policy.c.action_code == action_code)
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else SignoffPolicyRow(**dict(row))


async def list_signoff_policies(conn: AsyncConnection) -> list[SignoffPolicyRow]:
    stmt = _policies_in_bound_tenant().order_by(signoff_policy.c.action_code)
    return [SignoffPolicyRow(**dict(r)) for r in (await conn.execute(stmt)).mappings().all()]


_UPSERT_POLICY = text(
    """
    INSERT INTO signoff_policy (id, tenant_id, action_code, min_aal, step_up_max_age_min,
      updated_by)
    VALUES (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid, :action_code, :min_aal,
      :max_age, :updated_by)
    ON CONFLICT (tenant_id, action_code) WHERE deleted_at IS NULL DO UPDATE
      SET min_aal = EXCLUDED.min_aal, step_up_max_age_min = EXCLUDED.step_up_max_age_min,
          updated_by = EXCLUDED.updated_by, updated_at = now()
    """
)


async def upsert_signoff_policy(
    conn: AsyncConnection,
    *,
    action_code: str,
    min_aal: int,
    step_up_max_age_min: int,
    updated_by: UUID | None,
) -> None:
    await conn.execute(
        _UPSERT_POLICY,
        {
            "id": new_id(),
            "action_code": action_code,
            "min_aal": min_aal,
            "max_age": step_up_max_age_min,
            "updated_by": updated_by,
        },
    )
