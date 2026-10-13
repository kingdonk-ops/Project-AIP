"""Background jobs for identity (Procrastinate, ADR 0003).

``identity.revoke_keycloak_sessions`` (IDENTITY-03): ends the Keycloak SSO sessions behind revoked
app sessions. Enqueued by ``sessions.revoke_session`` / ``revoke_all_for_user`` in the same
transaction as the revocation, so a rollback queues nothing. Payload ``{kc_sids: [...]}``; the
tenant is the job's own. Idempotent: Keycloak's 404 for an already-ended session is success, and
a failure retries with backoff.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.identity import sessions
from aip.modules.identity.keycloak_admin import KeycloakAdmin, KeycloakAdminSettings
from aip.modules.ops import api as ops

__all__ = ["enqueue_keycloak_revocation", "revoke_keycloak_sessions"]


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


if sessions.REVOKE_KEYCLOAK_JOB not in ops.registered_types():
    ops.register(
        sessions.REVOKE_KEYCLOAK_JOB,
        revoke_keycloak_sessions,
        queue="default",
        timeout_s=30,
        max_attempts=8,
    )
