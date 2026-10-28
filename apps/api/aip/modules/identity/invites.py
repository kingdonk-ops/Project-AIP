"""Staff invitations and admin MFA reset (IDENTITY-04 steps 3, 4, 5 and 7; ADR 0005 rev 2).

Keycloak holds every staff password and second factor; the app keeps ``app_user``,
``tenant_membership`` and ``user_invite``. Every function takes the caller's ``with_tenant``
connection, so an invite and its queued job commit together or not at all (ADR 0003).

- ``invite_method`` (pure): ``sso`` when the email domain belongs to an IdP in the login
  directory, else ``local``.
- ``create_invite``: an ``invited`` user (SSO-managed for ``sso``; a local user with its email
  registered to the tenant for ``local``), a ``pending`` invite, the ``identity.send_invite`` job
  (``local`` only: an SSO user's Keycloak account appears at their first company sign-in) and an
  ``invite.created`` auth event. Re-inviting the same email revokes the previous live invite.
- ``resend_invite`` / ``revoke_invite``: re-queue the email; revoke (and disable a Keycloak account
  that was never used).
- ``accept_on_login``: JIT (IDENTITY-02 rule (a)/(b)) calls it for an ``invited`` user. The latest
  invite must be live (``sent``, or ``pending``/``sent`` for SSO) and unexpired, else
  ``INVITE_INVALID``; a revoked or expired invite stays refused even if the Keycloak account works.
- ``reset_mfa``: queue the Keycloak credential reset, revoke every session, clear
  ``mfa_enrolled_at``; SSO users' MFA belongs to their IdP (``MFA_MANAGED_BY_IDP``).

IDENTITY-10: ``create_invite(..., user_class="portal")`` (PORTAL-01's client invite) is always
``local`` (clients have their own Keycloak account on the ``aip-portal`` client, never company SSO;
a domain an SSO IdP claims is still refused by the email registration, ``EMAIL_DOMAIN_SSO``), gets a
``client`` membership, and its email's "back to the application" link is the portal
(``identity.send_invite`` uses the ``aip-portal`` client). Re-inviting an invited user of another
class is ``USER_EXISTS``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.identity import repository as repo
from aip.modules.identity.oidc import domain_of
from aip.modules.identity.repository import (
    EmailDomainSsoError,
    EmailInOtherTenantError,
    InviteRow,
    UserRow,
)
from aip.modules.identity.sessions import revoke_all_for_user
from aip.modules.ops import api as ops

__all__ = [
    "DISABLE_KEYCLOAK_USER_JOB",
    "INVITE_REQUIRED_ACTIONS",
    "INVITE_TTL",
    "RESET_KEYCLOAK_MFA_JOB",
    "SEND_INVITE_JOB",
    "CreatedInvite",
    "InviteError",
    "accept_on_login",
    "create_invite",
    "invite_method",
    "resend_invite",
    "reset_mfa",
    "revoke_invite",
]

SEND_INVITE_JOB: Final = "identity.send_invite"
DISABLE_KEYCLOAK_USER_JOB: Final = "identity.disable_keycloak_user"
RESET_KEYCLOAK_MFA_JOB: Final = "identity.reset_keycloak_mfa"
INVITE_TTL: Final = timedelta(days=7)
INVITE_REQUIRED_ACTIONS: Final = ("VERIFY_EMAIL", "UPDATE_PASSWORD", "CONFIGURE_TOTP")

InviteMethod = Literal["local", "sso"]


class InviteError(Exception):
    """A refused invite operation; ``code`` and ``message`` are safe to return."""

    def __init__(self, code: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class CreatedInvite:
    invite_id: UUID
    user_id: UUID
    method: InviteMethod


def invite_method(email: str, directory: Mapping[str, str | None]) -> InviteMethod:
    """``sso`` when ``directory`` (email domain -> IdP alias) names an IdP for the domain."""
    return "sso" if directory.get(domain_of(email)) else "local"


def _display_name(first_name: str, last_name: str, email: str) -> str:
    name = f"{first_name.strip()} {last_name.strip()}".strip()
    return (name or email.split("@", 1)[0])[:200]


async def _enqueue_send(conn: AsyncConnection, tenant_id: UUID, invite_id: UUID) -> None:
    await ops.enqueue(
        conn, SEND_INVITE_JOB, {"tenant_id": str(tenant_id), "invite_id": str(invite_id)}
    )


async def create_invite(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    email: str,
    user_class: repo.UserClass = "staff",
    first_name: str = "",
    last_name: str = "",
    organisation_id: UUID | None = None,
    invited_by: UUID | None = None,
) -> CreatedInvite:
    """Invite ``email`` to the bound tenant (``conn`` from ``with_tenant(tenant_id)``).

    No step-up here: the route adds it, and TENANCY-05's first-admin invite calls this directly.
    ``InviteError`` for a refusal; the caller's transaction must then roll back.
    A ``portal`` invite is always ``local`` with a ``client`` membership (IDENTITY-10).
    """
    email = email.strip()
    try:
        domain = domain_of(email)
    except ValueError:
        raise InviteError("INVALID_EMAIL", 422, "enter a valid email address") from None
    portal = user_class == "portal"
    membership_type: repo.MembershipType = "client" if portal else "member"
    target = await repo.resolve_login(conn, "email_domain", domain)
    idp_alias = target.idp_alias if target is not None else None
    if idp_alias is not None and target is not None and target.tenant_id != tenant_id:
        raise InviteError(
            "EMAIL_DOMAIN_SSO", 409, "people with this email domain sign in with company SSO"
        )
    method: InviteMethod = "sso" if idp_alias is not None and not portal else "local"

    existing = await repo.find_by_email(conn, email)
    if existing is not None and existing.status != "invited":
        code = "USER_DEACTIVATED" if existing.status == "deactivated" else "USER_EXISTS"
        raise InviteError(code, 409, "this person already has an account")
    if existing is not None and existing.user_class != user_class:
        raise InviteError("USER_EXISTS", 409, "this person already has an account")
    await repo.revoke_live_invites(conn, email)

    if existing is not None:
        user_id = existing.id
        method = "sso" if existing.sso_managed else "local"
    elif method == "sso":
        user_id = await repo.insert_user(
            conn,
            tenant_id=tenant_id,
            email=email,
            display_name=_display_name(first_name, last_name, email),
            user_class=user_class,
            status="invited",
            sso_managed=True,
            idp_alias=idp_alias,
            organisation_id=organisation_id,
        )
        await repo.insert_membership(
            conn,
            tenant_id=tenant_id,
            user_id=user_id,
            membership_type="member",
            organisation_id=organisation_id,
        )
    else:
        user_id = await repo.insert_user(
            conn,
            tenant_id=tenant_id,
            email=email,
            display_name=_display_name(first_name, last_name, email),
            user_class=user_class,
            status="invited",
            sso_managed=False,
            organisation_id=organisation_id,
        )
        await repo.insert_membership(
            conn,
            tenant_id=tenant_id,
            user_id=user_id,
            membership_type=membership_type,
            organisation_id=organisation_id,
        )
        try:
            await repo.register_email(conn, email, tenant_id)
        except EmailInOtherTenantError:
            raise InviteError(
                "EMAIL_IN_OTHER_TENANT", 409, "this email address cannot be invited here"
            ) from None
        except EmailDomainSsoError:
            raise InviteError(
                "EMAIL_DOMAIN_SSO", 409, "people with this email domain sign in with company SSO"
            ) from None

    invite_id = await repo.insert_invite(
        conn,
        tenant_id=tenant_id,
        user_id=user_id,
        email=email,
        user_class=user_class,
        method=method,
        expires_at=func.now() + INVITE_TTL,
        organisation_id=organisation_id,
        invited_by=invited_by,
    )
    if method == "local":
        await _enqueue_send(conn, tenant_id, invite_id)
    detail: dict[str, object] = {"inviteId": str(invite_id), "method": method}
    if portal:
        detail["audience"] = "portal"
    await repo.record_auth_event(
        conn,
        tenant_id=tenant_id,
        event_type="invite.created",
        user_id=user_id,
        detail=detail,
    )

    return CreatedInvite(invite_id=invite_id, user_id=user_id, method=method)


async def _live_invite(conn: AsyncConnection, invite_id: UUID) -> InviteRow:
    invite = await repo.get_invite(conn, invite_id, for_update=True)
    if invite is None:
        raise InviteError("NOT_FOUND", 404, "no such invite")
    return invite


async def resend_invite(conn: AsyncConnection, invite_id: UUID) -> InviteRow:
    """Queue the invite email again with a fresh 7-day expiry (local invites only)."""
    invite = await _live_invite(conn, invite_id)
    if invite.method != "local":
        raise InviteError("INVITE_NOT_LOCAL", 409, "company SSO invites send no email")
    if invite.status not in ("pending", "sent", "failed"):
        raise InviteError("INVITE_NOT_LIVE", 409, "this invite was accepted or revoked")
    latest = await repo.latest_invite_for_user(conn, invite.user_id)
    if latest is not None and latest.id != invite_id:
        raise InviteError("INVITE_SUPERSEDED", 409, "a newer invite exists for this person")
    await repo.update_invite(
        conn,
        invite_id,
        status="pending" if invite.status == "failed" else invite.status,
        last_error=None,
        expires_at=func.now() + INVITE_TTL,
    )
    await _enqueue_send(conn, invite.tenant_id, invite_id)
    await repo.record_auth_event(
        conn,
        tenant_id=invite.tenant_id,
        event_type="invite.resent",
        user_id=invite.user_id,
        detail={"inviteId": str(invite_id)},
    )
    refreshed = await repo.get_invite(conn, invite_id)
    assert refreshed is not None
    return refreshed


async def revoke_invite(conn: AsyncConnection, invite_id: UUID) -> InviteRow:
    """Revoke an invite (idempotent). A Keycloak account the invitee never used is disabled."""
    invite = await _live_invite(conn, invite_id)
    if invite.status == "accepted":
        raise InviteError("INVITE_NOT_LIVE", 409, "this invite was already accepted")
    if invite.status != "revoked":
        await repo.update_invite(conn, invite_id, status="revoked", revoked_at=func.now())
        user = await repo.get_user(conn, invite.user_id)
        keycloak_id = invite.keycloak_user_id or (user.keycloak_user_id if user else None)
        if user is not None and user.status == "invited" and keycloak_id is not None:
            await ops.enqueue(
                conn,
                DISABLE_KEYCLOAK_USER_JOB,
                {"keycloak_user_id": str(keycloak_id), "user_id": str(user.id)},
            )
        await repo.record_auth_event(
            conn,
            tenant_id=invite.tenant_id,
            event_type="invite.revoked",
            user_id=invite.user_id,
            detail={"inviteId": str(invite_id)},
        )
    refreshed = await repo.get_invite(conn, invite_id)
    assert refreshed is not None
    return refreshed


def invite_usable(invite: InviteRow, now: datetime) -> bool:
    """A local invite is usable once its email went out; an SSO invite sends none."""
    live = ("sent",) if invite.method == "local" else ("pending", "sent")
    return invite.status in live and invite.expires_at > now


async def accept_on_login(conn: AsyncConnection, user: UserRow) -> str | None:
    """For an ``invited`` user signing in: accept their invite, or return ``INVITE_INVALID``.

    A user with no invite row at all (the dev/demo admin bootstrap, ``ensure_invited_sso_user``)
    is not refused here.
    """
    invite = await repo.latest_invite_for_user(conn, user.id)
    if invite is None:
        return None
    if not invite_usable(invite, datetime.now(UTC)):
        return "INVITE_INVALID"
    await repo.update_invite(conn, invite.id, status="accepted", accepted_at=func.now())
    await repo.record_auth_event(
        conn,
        tenant_id=user.tenant_id,
        event_type="invite.accepted",
        user_id=user.id,
        detail={"inviteId": str(invite.id), "method": invite.method},
    )
    return None


async def reset_mfa(conn: AsyncConnection, user_id: UUID) -> None:
    """Admin MFA reset (step 7): Keycloak drops the second factor; every session ends now."""
    user = await repo.get_user(conn, user_id)
    if user is None:
        raise InviteError("NOT_FOUND", 404, "no such user")
    if user.sso_managed:
        raise InviteError(
            "MFA_MANAGED_BY_IDP", 409, "this person's second factor is managed by their company"
        )
    if user.keycloak_user_id is not None:
        await ops.enqueue(
            conn, RESET_KEYCLOAK_MFA_JOB, {"keycloak_user_id": str(user.keycloak_user_id)}
        )
    await revoke_all_for_user(conn, user_id, "mfa_reset")
    await repo.clear_mfa_enrolled(conn, user_id)
    await repo.record_auth_event(
        conn, tenant_id=user.tenant_id, event_type="mfa.reset", user_id=user_id, detail={}
    )
