"""Background jobs for identity (Procrastinate, ADR 0003).

``identity.revoke_keycloak_sessions`` (IDENTITY-03): ends the Keycloak SSO sessions behind revoked
app sessions. Enqueued by ``sessions.revoke_session`` / ``revoke_all_for_user`` in the same
transaction as the revocation, so a rollback queues nothing. Payload ``{kc_sids: [...]}``; the
tenant is the job's own. Idempotent: Keycloak's 404 for an already-ended session is success, and
a failure retries with backoff.

IDENTITY-04 (all idempotent; handlers run inside the job's tenant):

- ``identity.send_invite`` ``{tenant_id, invite_id}``: skips an invite that is not ``pending`` or
  ``sent``; creates the Keycloak user (an existing one with that email is reused, so a rerun makes
  no second account) with ``VERIFY_EMAIL``, ``UPDATE_PASSWORD`` and ``CONFIGURE_TOTP`` and the
  ``aip_user_id`` attribute, links it, and has Keycloak email the action link (7 days; its "back
  to the application" link is the ``aip-api`` client's base URL, ``/login?invited=1``).
  ``KeycloakUnavailable`` re-raises so Procrastinate retries (5 attempts); ``KeycloakRejected``
  marks the invite ``failed`` with Keycloak's message.
  The account is enabled again first, so a re-invite after a revoke works.
- ``identity.disable_keycloak_user`` ``{keycloak_user_id, user_id}``: a revoked invite's unused
  account; skipped when the user has a newer live invite (a re-invite queued after the revoke).
- ``identity.reset_keycloak_mfa`` ``{keycloak_user_id}``: an admin MFA reset.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.identity import repository as repo
from aip.modules.identity import sessions
from aip.modules.identity.invites import (
    DISABLE_KEYCLOAK_USER_JOB,
    INVITE_REQUIRED_ACTIONS,
    INVITE_TTL,
    RESET_KEYCLOAK_MFA_JOB,
    SEND_INVITE_JOB,
)
from aip.modules.identity.keycloak_admin import (
    KeycloakAdmin,
    KeycloakAdminSettings,
    KeycloakRejected,
)
from aip.modules.ops import api as ops

__all__ = [
    "disable_keycloak_user",
    "enqueue_keycloak_revocation",
    "reset_keycloak_mfa",
    "revoke_keycloak_sessions",
    "send_invite",
    "set_admin_factory",
]

_admin_factory: Callable[[], KeycloakAdmin] | None = None


def set_admin_factory(factory: Callable[[], KeycloakAdmin] | None) -> None:
    """Tests: build the Keycloak admin client the IDENTITY-04 handlers use."""
    global _admin_factory
    _admin_factory = factory


@asynccontextmanager
async def _client(admin: KeycloakAdmin | None) -> AsyncIterator[KeycloakAdmin]:
    if admin is not None:
        yield admin
        return
    if _admin_factory is not None:
        yield _admin_factory()
        return
    client = KeycloakAdmin(KeycloakAdminSettings())  # pyright: ignore[reportCallIssue]
    try:
        yield client
    finally:
        await client.aclose()


async def revoke_keycloak_sessions(
    conn: AsyncConnection, job: ops.JobView, admin: KeycloakAdmin | None = None
) -> str | None:
    kc_sids = [str(sid) for sid in job.payload.get("kc_sids", []) if sid]
    client = admin or KeycloakAdmin(KeycloakAdminSettings())  # pyright: ignore[reportCallIssue]
    try:
        for kc_sid in kc_sids:
            await client.revoke_kc_session(kc_sid)
    finally:
        if admin is None:
            await client.aclose()
    return None


async def enqueue_keycloak_revocation(conn: AsyncConnection, kc_sids: list[str]) -> None:
    await ops.enqueue(conn, sessions.REVOKE_KEYCLOAK_JOB, {"kc_sids": kc_sids})


def _names(display_name: str) -> tuple[str, str]:
    first, _, last = display_name.strip().partition(" ")
    return first, last.strip()


async def send_invite(
    conn: AsyncConnection, job: ops.JobView, admin: KeycloakAdmin | None = None
) -> str | None:
    invite = await repo.get_invite(conn, UUID(str(job.payload["invite_id"])), for_update=True)
    if invite is None or invite.status not in ("pending", "sent") or invite.method != "local":
        return None
    user = await repo.get_user(conn, invite.user_id)
    if user is None or user.status != "invited":
        return None
    first, last = _names(user.display_name)
    async with _client(admin) as client:
        try:
            keycloak_id = await client.create_user(
                invite.email,
                first_name=first,
                last_name=last,
                required_actions=INVITE_REQUIRED_ACTIONS,
                attributes={"aip_user_id": [str(user.id)]},
            )
            await client.enable_user(keycloak_id)  # a revoked earlier invite disabled it
            await repo.update_invite(conn, invite.id, keycloak_user_id=keycloak_id)
            if user.keycloak_user_id is None:
                await repo.set_keycloak_link(conn, user.id, keycloak_id)
            await client.send_actions_email(
                keycloak_id,
                INVITE_REQUIRED_ACTIONS,
                lifespan_s=int(INVITE_TTL.total_seconds()),
            )
        except KeycloakRejected as exc:
            await repo.update_invite(conn, invite.id, status="failed", last_error=exc.message[:500])
            await repo.record_auth_event(
                conn,
                tenant_id=invite.tenant_id,
                event_type="invite.failed",
                user_id=invite.user_id,
                detail={"inviteId": str(invite.id), "status": exc.status_code},
            )
            return None
    await repo.update_invite(conn, invite.id, status="sent", sent_at=func.now(), last_error=None)
    return str(keycloak_id)


async def disable_keycloak_user(
    conn: AsyncConnection, job: ops.JobView, admin: KeycloakAdmin | None = None
) -> str | None:
    user_id = job.payload.get("user_id")
    if user_id is not None:
        latest = await repo.latest_invite_for_user(conn, UUID(str(user_id)))
        if latest is not None and latest.status in ("pending", "sent"):
            return None  # re-invited since the revoke: the send job owns the account now
    async with _client(admin) as client:
        await client.disable_user(str(job.payload["keycloak_user_id"]))
    return None


async def reset_keycloak_mfa(
    conn: AsyncConnection, job: ops.JobView, admin: KeycloakAdmin | None = None
) -> str | None:
    async with _client(admin) as client:
        await client.reset_mfa(str(job.payload["keycloak_user_id"]))
    return None


for _job_type, _handler, _attempts in (
    (sessions.REVOKE_KEYCLOAK_JOB, revoke_keycloak_sessions, 8),
    (SEND_INVITE_JOB, send_invite, 5),
    (DISABLE_KEYCLOAK_USER_JOB, disable_keycloak_user, 8),
    (RESET_KEYCLOAK_MFA_JOB, reset_keycloak_mfa, 8),
):
    if _job_type not in ops.registered_types():
        ops.register(_job_type, _handler, queue="default", timeout_s=30, max_attempts=_attempts)
