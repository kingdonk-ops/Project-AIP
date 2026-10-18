"""App-issued browser sessions (IDENTITY-03, ADR 0005 rev 2).

After Keycloak signs a user in, the backend issues an opaque ``__Host-aip_sid`` cookie backed by a
``user_session`` row; the browser never holds a JWT. Only the SHA-256 of the cookie value is
stored. A second cookie, ``__Host-aip_csrf`` (readable by JS), carries the CSRF token that unsafe
requests echo in ``X-CSRF-Token`` (``csrf.py``).

- Pure rules: ``derive_aal``, ``compute_expiry`` and ``touch`` (idle expiry slides, the absolute
  expiry never moves), plus the cookie writers.
- ``issue_session`` / ``rotate_session``: a new sid on every login and elevation; a sid presented
  with the login is revoked with reason ``rotated`` (no fixation).
- ``revoke_session`` / ``revoke_all_for_user``: update rows in the caller's transaction, purge the
  cache after commit, and enqueue ``identity.revoke_keycloak_sessions`` in the same transaction
  (ADR 0003) so the Keycloak SSO session ends too.

Every function that touches the database takes the caller's ``with_tenant`` connection.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
from collections.abc import Awaitable, Callable, Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.responses import Response

from aip.platform.context import new_request_id

__all__ = [
    "CSRF_COOKIE",
    "DEFAULT_POLICY",
    "REVOKE_KEYCLOAK_JOB",
    "SID_COOKIE",
    "Audience",
    "Expiry",
    "IssuedSession",
    "SessionPolicy",
    "clear_session_cookies",
    "compute_expiry",
    "derive_aal",
    "hash_sid",
    "issue_session",
    "list_user_sessions",
    "load_policy",
    "on_revoked",
    "owns_live_session",
    "revoke_all_for_user",
    "revoke_session",
    "rotate_session",
    "set_session_cookies",
    "touch",
]

logger = logging.getLogger(__name__)

SID_COOKIE: Final = "__Host-aip_sid"
CSRF_COOKIE: Final = "__Host-aip_csrf"
REVOKE_KEYCLOAK_JOB: Final = "identity.revoke_keycloak_sessions"
# ``amr`` values that prove a second factor: Keycloak's own (otp, hwk) and what an upstream IdP
# reports (RFC 8176 mfa, otp, hwk, swk; fido from some IdPs).
_MFA_METHODS: Final = frozenset({"otp", "hwk", "mfa", "swk", "fido"})
_USER_AGENT_MAX: Final = 512

Audience = Literal["app", "portal", "device"]


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    idle: timedelta
    absolute: timedelta


# The migration's column default; a tenant without a ``tenant_auth_policy`` row uses this.
DEFAULT_POLICY: Final[Mapping[str, SessionPolicy]] = {
    "staff": SessionPolicy(idle=timedelta(minutes=30), absolute=timedelta(hours=12)),
    "field": SessionPolicy(idle=timedelta(minutes=5), absolute=timedelta(hours=12)),
    "portal": SessionPolicy(idle=timedelta(minutes=15), absolute=timedelta(hours=8)),
}


@dataclass(frozen=True, slots=True)
class Expiry:
    idle_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session_id: UUID
    sid: str  # the raw cookie value: hand it to the browser, never store or log it
    csrf: str
    expiry: Expiry


def derive_aal(
    acr: str | None, amr: Sequence[str], upstream_amr: Sequence[str] = ()
) -> Literal[1, 2]:
    """2 when the sign-in used a second factor: ``acr`` aal2, a second factor in Keycloak's
    ``amr``, or (brokered sign-in, IDENTITY-04) one in the upstream IdP's ``amr``. Keycloak gives
    a brokered sign-in ``acr`` aal1 and an empty ``amr``, so only the upstream IdP can lift it."""
    return 2 if acr == "aal2" or _MFA_METHODS & (set(amr) | set(upstream_amr)) else 1


def compute_expiry(now: datetime, policy: SessionPolicy) -> Expiry:
    absolute = now + policy.absolute
    return Expiry(idle_expires_at=min(now + policy.idle, absolute), absolute_expires_at=absolute)


def touch(now: datetime, session: Expiry, policy: SessionPolicy) -> Expiry:
    """Activity slides the idle expiry; it is capped by, and never moves, the absolute expiry."""
    absolute = session.absolute_expires_at
    return Expiry(idle_expires_at=min(now + policy.idle, absolute), absolute_expires_at=absolute)


def hash_sid(sid: str) -> bytes:
    return hashlib.sha256(sid.encode("ascii")).digest()


def _token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def set_session_cookies(response: Response, issued: IssuedSession) -> None:
    """``__Host-`` cookies: Secure, Path=/, no Domain. Only the sid cookie is HttpOnly."""
    max_age = None  # session cookies: the server-side expiry decides, the browser drops on close
    response.set_cookie(
        SID_COOKIE,
        issued.sid,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )


def clear_session_cookies(response: Response) -> None:
    for name, http_only in ((SID_COOKIE, True), (CSRF_COOKIE, False)):
        response.delete_cookie(name, path="/", secure=True, httponly=http_only, samesite="lax")


_POLICY = text("SELECT session_policy FROM tenant_auth_policy WHERE deleted_at IS NULL")


def _policy_from(raw: Mapping[str, Any], user_class: str) -> SessionPolicy:
    default = DEFAULT_POLICY.get(user_class, DEFAULT_POLICY["staff"])
    entry = raw.get(user_class)
    if not isinstance(entry, Mapping):
        return default
    try:
        idle = timedelta(minutes=float(entry.get("idleMin", default.idle.total_seconds() / 60)))
        absolute = timedelta(
            hours=float(entry.get("absoluteH", default.absolute.total_seconds() / 3600))
        )
    except (TypeError, ValueError):
        logger.warning("tenant session policy for %s is malformed; using the default", user_class)
        return default
    if idle <= timedelta(0) or absolute <= timedelta(0):
        return default
    return SessionPolicy(idle=idle, absolute=absolute)


async def load_policy(conn: AsyncConnection, user_class: str) -> SessionPolicy:
    """The bound tenant's policy for ``user_class`` (defaults when it has none)."""
    raw = (await conn.execute(_POLICY)).scalar_one_or_none()
    return _policy_from(raw if isinstance(raw, Mapping) else {}, user_class)


_INSERT = text(
    """
    INSERT INTO user_session (id, tenant_id, user_id, sid_hash, audience, aal, amr,
      authenticated_at, kc_sid, ip, user_agent, idle_seconds, idle_expires_at, absolute_expires_at)
    VALUES (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid, :user_id, :sid_hash,
      :audience, :aal, CAST(:amr AS text[]), :authenticated_at, :kc_sid, CAST(:ip AS inet),
      :user_agent, :idle_seconds, :idle_expires_at, :absolute_expires_at)
    """
)
_NOW = text("SELECT now()")
_REVOKE_SQL = """
    UPDATE user_session SET revoked_at = now(), revoke_reason = :reason, updated_at = now()
    WHERE revoked_at IS NULL AND {predicate}
    RETURNING id, sid_hash, kc_sid
"""
# The only predicates revocation uses (never caller-supplied SQL).
_REVOKE: Final[Mapping[str, Any]] = {
    key: text(_REVOKE_SQL.format(predicate=predicate))
    for key, predicate in (
        ("id", "id = :value"),
        ("sid_hash", "sid_hash = :value"),
        ("user_id", "user_id = :value"),
    )
}
RevokeBy = Literal["id", "sid_hash", "user_id"]


async def issue_session(
    conn: AsyncConnection,
    *,
    user_id: UUID,
    user_class: str,
    aal: int,
    amr: Sequence[str],
    authenticated_at: datetime,
    kc_sid: str | None,
    audience: Audience = "app",
    ip: str | None = None,
    user_agent: str | None = None,
    presented_sid: str | None = None,
) -> IssuedSession:
    """Insert a new session for ``user_id`` in the bound tenant and return its cookie values.

    A sid presented with the login (``presented_sid``) is revoked with reason ``rotated``, without
    ending the Keycloak session the new sign-in just created.
    """
    if presented_sid:
        await _revoke(conn, "sid_hash", hash_sid(presented_sid), "rotated", end_keycloak=False)
    now: datetime = (await conn.execute(_NOW)).scalar_one()
    policy = await load_policy(conn, user_class)
    expiry = compute_expiry(now, policy)
    issued = IssuedSession(
        session_id=UUID(new_request_id()), sid=_token(), csrf=_token(), expiry=expiry
    )
    await conn.execute(
        _INSERT,
        {
            "id": issued.session_id,
            "user_id": user_id,
            "sid_hash": hash_sid(issued.sid),
            "audience": audience,
            "aal": aal,
            "amr": list(amr),
            "authenticated_at": authenticated_at,
            "kc_sid": kc_sid,
            "ip": ip,
            "user_agent": None if user_agent is None else user_agent[:_USER_AGENT_MAX],
            "idle_seconds": int(policy.idle.total_seconds()),
            "idle_expires_at": expiry.idle_expires_at,
            "absolute_expires_at": expiry.absolute_expires_at,
        },
    )
    return issued


_SESSION = text(
    "SELECT s.user_id, s.audience, s.kc_sid, host(s.ip) AS ip, s.user_agent, u.user_class"
    " FROM user_session s JOIN app_user u ON u.id = s.user_id"
    " WHERE s.id = :id AND s.revoked_at IS NULL"
)


async def rotate_session(
    conn: AsyncConnection,
    session_id: UUID,
    *,
    aal: int,
    amr: Sequence[str],
    authenticated_at: datetime,
) -> IssuedSession:
    """Replace a live session with a new sid (step-up, privilege change); the old one is revoked
    with reason ``rotated``. The Keycloak session carries over. ``LookupError`` if not live."""
    row = (await conn.execute(_SESSION, {"id": session_id})).mappings().first()
    if row is None:
        raise LookupError(f"session {session_id} is not live")
    await _revoke(conn, "id", session_id, "rotated", end_keycloak=False)
    return await issue_session(
        conn,
        user_id=row["user_id"],
        user_class=row["user_class"],
        aal=aal,
        amr=amr,
        authenticated_at=authenticated_at,
        kc_sid=row["kc_sid"],
        audience=row["audience"],
        ip=row["ip"],
        user_agent=row["user_agent"],
    )


# --- revocation -------------------------------------------------------------------------------

CachePurge = Callable[[Iterable[bytes]], Coroutine[Any, Any, None]]
KeycloakEnqueue = Callable[[AsyncConnection, list[str]], Awaitable[None]]

_cache_purge: CachePurge | None = None
_keycloak_enqueue: KeycloakEnqueue | None = None


def on_revoked(*, purge: CachePurge | None, enqueue: KeycloakEnqueue | None) -> None:
    """Wire the cache purge (``session_store``) and the Keycloak job enqueue (``jobs``)."""
    global _cache_purge, _keycloak_enqueue
    _cache_purge = purge
    _keycloak_enqueue = enqueue


def _purge_after_commit(conn: AsyncConnection, hashes: list[bytes]) -> None:
    purge = _cache_purge
    if purge is None or not hashes:
        return
    loop = asyncio.get_running_loop()

    def _after_commit(_conn: object) -> None:
        task = loop.create_task(purge(hashes))
        task.add_done_callback(_log_purge_failure)

    event.listen(conn.sync_connection, "commit", _after_commit, once=True)


def _log_purge_failure(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception() is not None:
        # The cache TTL (at most 60 s) still bounds how long a revoked session is honoured.
        logger.warning("session cache purge failed: %s", task.exception())


async def _revoke(
    conn: AsyncConnection,
    by: RevokeBy,
    value: object,
    reason: str,
    *,
    end_keycloak: bool,
) -> list[UUID]:
    rows = (await conn.execute(_REVOKE[by], {"value": value, "reason": reason})).all()
    _purge_after_commit(conn, [bytes(r.sid_hash) for r in rows])
    kc_sids = sorted({r.kc_sid for r in rows if r.kc_sid})
    if end_keycloak and kc_sids:
        if _keycloak_enqueue is None:
            logger.warning("no Keycloak revocation is wired; %d SSO sessions stay", len(kc_sids))
        else:
            await _keycloak_enqueue(conn, kc_sids)
    return [r.id for r in rows]


async def revoke_session(
    conn: AsyncConnection, session_id: UUID, reason: str, *, end_keycloak: bool = True
) -> bool:
    """Revoke one live session; False when it was not live (already revoked or unknown)."""
    return bool(await _revoke(conn, "id", session_id, reason, end_keycloak=end_keycloak))


async def revoke_all_for_user(
    conn: AsyncConnection, user_id: UUID, reason: str, *, end_keycloak: bool = True
) -> list[UUID]:
    """Revoke every live session of ``user_id``; returns the revoked session ids."""
    return await _revoke(conn, "user_id", user_id, reason, end_keycloak=end_keycloak)


_LIST = text(
    """
    SELECT id, audience, aal, host(ip) AS ip, user_agent, created_at, last_seen_at
    FROM user_session
    WHERE user_id = :user_id AND revoked_at IS NULL AND deleted_at IS NULL
      AND idle_expires_at > now() AND absolute_expires_at > now()
    ORDER BY last_seen_at DESC, id
    LIMIT 100
    """
)


async def list_user_sessions(conn: AsyncConnection, user_id: UUID) -> list[dict[str, Any]]:
    """``user_id``'s live sessions in the bound tenant, most recently used first."""
    return [dict(r) for r in (await conn.execute(_LIST, {"user_id": user_id})).mappings()]


_OWNED = text(
    "SELECT 1 FROM user_session WHERE id = :id AND user_id = :user_id AND revoked_at IS NULL"
)


async def owns_live_session(conn: AsyncConnection, session_id: UUID, user_id: UUID) -> bool:
    return (await conn.execute(_OWNED, {"id": session_id, "user_id": user_id})).first() is not None
