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
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy import ColumnElement, Select, Uuid, cast, func, insert, or_, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.identity.tables import app_user, auth_event, tenant_membership
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


def _users_in_bound_tenant() -> Select[Any]:
    return select(*_USER_COLUMNS).where(app_user.c.tenant_id == _bound_tenant())


async def _one_user(conn: AsyncConnection, stmt: Select[Any]) -> UserRow | None:
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else _user(row)


async def get_user(conn: AsyncConnection, user_id: UUID) -> UserRow | None:
    """The live user ``user_id`` in the bound tenant, or ``None`` (also for another tenant's id)."""
    stmt = _users_in_bound_tenant().where(app_user.c.id == user_id, app_user.c.deleted_at.is_(None))
    return await _one_user(conn, stmt)


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


_REGISTER = text("SELECT identity_register_email(CAST(:email AS citext), :tenant_id)")


async def register_email(conn: AsyncConnection, email: str, tenant_id: UUID) -> None:
    """Map a local account's email to the bound tenant in ``login_directory``.

    ``EmailInOtherTenantError`` when another tenant already holds the email. Any error aborts the
    surrounding transaction, so the user change that needed the registration rolls back with it.
    """
    try:
        await conn.execute(_REGISTER, {"email": email.strip(), "tenant_id": tenant_id})
    except DBAPIError as exc:
        if "EMAIL_IN_OTHER_TENANT" in str(exc.orig):
            raise EmailInOtherTenantError("email is registered to another tenant") from None
        raise


_LOCK = text("SELECT pg_advisory_xact_lock(:key)")


async def advisory_xact_lock(conn: AsyncConnection, key: int) -> None:
    """``pg_advisory_xact_lock(key)``: held until the transaction ends."""
    await conn.execute(_LOCK, {"key": key})
