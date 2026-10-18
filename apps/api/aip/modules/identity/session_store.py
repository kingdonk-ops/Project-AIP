"""Resolving the session cookie on each request (IDENTITY-03).

``SessionMiddleware`` (pure ASGI, outermost of the auth layers) reads ``__Host-aip_sid`` once per
request and asks ``SessionStore.resolve``:

1. the Redis cache ``aip:sess:<sid_hash hex>`` (TTL = min(60 s, time left)), else
2. ``identity_resolve_session`` (SECURITY DEFINER, the tenant is not known yet), then, inside the
   session's own ``with_tenant`` transaction (RLS on), that the user is still active.

Postgres is the truth: a revoked session is purged from the cache after commit, and even if that
purge fails the cache holds it for at most 60 s. A presented cookie that resolves to nothing marks
the request ``expired``; ``get_principal`` then answers 401 ``SESSION_EXPIRED`` and clears both
cookies. Activity updates ``last_seen_at`` at most once per 60 s and slides the idle expiry,
never the absolute one.

The result travels to ``SessionPrincipalResolver`` (the identity ``PrincipalResolver``) through a
context variable, so the platform middleware and ``get_principal`` see the same session without
resolving it twice.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from http.cookies import CookieError, SimpleCookie
from typing import Any, Final, Literal, Protocol
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from aip.modules.identity import repository as repo
from aip.modules.identity.principal import Principal, PrincipalResolver
from aip.modules.identity.sessions import SID_COOKIE, hash_sid
from aip.platform.db.session import before_tenant, with_tenant
from aip.platform.db.tls import redis_tls_kwargs

__all__ = [
    "CACHE_TTL",
    "TOUCH_INTERVAL",
    "RedisSessionCache",
    "ResolvedSession",
    "SessionCache",
    "SessionMiddleware",
    "SessionPrincipalResolver",
    "SessionStore",
    "current_session",
    "session_expired",
]

logger = logging.getLogger(__name__)

CACHE_TTL: Final = timedelta(seconds=60)
TOUCH_INTERVAL: Final = timedelta(seconds=60)
_KEY_PREFIX: Final = "aip:sess:"
_MAX_SID_LEN: Final = 128


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    tenant_id: UUID
    user_id: UUID
    session_id: UUID
    user_class: Literal["staff", "field", "portal"]
    aal: int
    amr: tuple[str, ...]
    authenticated_at: datetime
    audience: str
    last_seen_at: datetime
    idle_seconds: int
    idle_expires_at: datetime
    absolute_expires_at: datetime

    def live_at(self, now: datetime) -> bool:
        return now < self.idle_expires_at and now < self.absolute_expires_at

    def to_json(self) -> str:
        data = asdict(self)
        return json.dumps({k: _encode(v) for k, v in data.items()})

    @classmethod
    def from_json(cls, raw: str | bytes) -> ResolvedSession:
        d = json.loads(raw)
        return cls(
            tenant_id=UUID(d["tenant_id"]),
            user_id=UUID(d["user_id"]),
            session_id=UUID(d["session_id"]),
            user_class=d["user_class"],
            aal=int(d["aal"]),
            amr=tuple(d["amr"]),
            authenticated_at=datetime.fromisoformat(d["authenticated_at"]),
            audience=d["audience"],
            last_seen_at=datetime.fromisoformat(d["last_seen_at"]),
            idle_seconds=int(d["idle_seconds"]),
            idle_expires_at=datetime.fromisoformat(d["idle_expires_at"]),
            absolute_expires_at=datetime.fromisoformat(d["absolute_expires_at"]),
        )


def _encode(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)  # pyright: ignore[reportUnknownArgumentType]
    return value


class SessionCache(Protocol):
    async def get(self, sid_hash: bytes) -> ResolvedSession | None: ...
    async def put(self, sid_hash: bytes, session: ResolvedSession, ttl: timedelta) -> None: ...
    async def delete(self, sid_hashes: Iterable[bytes]) -> None: ...


class NullSessionCache:
    """No Redis configured: every request reads Postgres."""

    async def get(self, sid_hash: bytes) -> ResolvedSession | None:
        return None

    async def put(self, sid_hash: bytes, session: ResolvedSession, ttl: timedelta) -> None:
        return None

    async def delete(self, sid_hashes: Iterable[bytes]) -> None:
        return None


class RedisSessionCache:
    def __init__(self, client: Redis) -> None:
        self._redis = client

    @classmethod
    def from_url(cls, url: str) -> RedisSessionCache:
        return cls(Redis.from_url(url, **redis_tls_kwargs(url)))  # pyright: ignore[reportUnknownMemberType]

    @staticmethod
    def key(sid_hash: bytes) -> str:
        return _KEY_PREFIX + sid_hash.hex()

    async def get(self, sid_hash: bytes) -> ResolvedSession | None:
        try:
            raw: bytes | str | None = await self._redis.get(self.key(sid_hash))
        except Exception:  # a cache outage must not lock users out: fall back to Postgres
            logger.warning("session cache read failed", exc_info=True)
            return None
        if raw is None:
            return None
        try:
            return ResolvedSession.from_json(raw)
        except (KeyError, TypeError, ValueError):
            return None

    async def put(self, sid_hash: bytes, session: ResolvedSession, ttl: timedelta) -> None:
        ms = int(ttl.total_seconds() * 1000)
        if ms <= 0:
            return
        try:
            await self._redis.set(self.key(sid_hash), session.to_json(), px=ms)
        except Exception:
            logger.warning("session cache write failed", exc_info=True)

    async def delete(self, sid_hashes: Iterable[bytes]) -> None:
        keys = [self.key(h) for h in sid_hashes]
        if keys:
            await self._redis.delete(*keys)


_RESOLVE = text(
    "SELECT tenant_id, user_id, session_id, aal, amr, authenticated_at, audience, last_seen_at,"
    " idle_seconds, idle_expires_at, absolute_expires_at"
    " FROM identity_resolve_session(:sid_hash)"
)
_TOUCH = text(
    """
    UPDATE user_session
    SET last_seen_at = CAST(:now AS timestamptz), updated_at = CAST(:now AS timestamptz),
        idle_expires_at = LEAST(
          CAST(:now AS timestamptz) + make_interval(secs => idle_seconds), absolute_expires_at)
    WHERE id = :id AND revoked_at IS NULL
      AND idle_expires_at > CAST(:now AS timestamptz)
      AND absolute_expires_at > CAST(:now AS timestamptz)
      AND last_seen_at <= CAST(:now AS timestamptz) - interval '60 seconds'
    RETURNING last_seen_at, idle_expires_at
    """
)


class SessionStore:
    def __init__(self, cache: SessionCache | None = None, cache_ttl: timedelta = CACHE_TTL) -> None:
        self.cache: SessionCache = cache or NullSessionCache()
        self.cache_ttl = cache_ttl

    def _ttl(self, session: ResolvedSession, now: datetime) -> timedelta:
        left = min(session.idle_expires_at, session.absolute_expires_at) - now
        return min(self.cache_ttl, left)

    async def resolve(self, sid: str, now: datetime | None = None) -> ResolvedSession | None:
        """The live session behind ``sid``, or ``None`` (unknown, revoked, expired, inactive)."""
        now = now or datetime.now(UTC)
        sid_hash = hash_sid(sid)
        cached = await self.cache.get(sid_hash)
        if cached is not None:
            return cached if cached.live_at(now) else None
        async with before_tenant() as conn:
            row = (await conn.execute(_RESOLVE, {"sid_hash": sid_hash})).mappings().first()
        if row is None:
            return None
        async with with_tenant(row["tenant_id"]) as conn:
            user = await repo.get_user(conn, row["user_id"])
        if user is None or user.status != "active":
            return None
        session = ResolvedSession(
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            user_class=user.user_class,
            aal=int(row["aal"]),
            amr=tuple(row["amr"] or ()),
            authenticated_at=row["authenticated_at"],
            audience=row["audience"],
            last_seen_at=row["last_seen_at"],
            idle_seconds=int(row["idle_seconds"]),
            idle_expires_at=row["idle_expires_at"],
            absolute_expires_at=row["absolute_expires_at"],
        )
        if not session.live_at(now):
            return None
        await self.cache.put(sid_hash, session, self._ttl(session, now))
        return session

    async def touch(self, sid: str, session: ResolvedSession, now: datetime | None = None) -> None:
        """Record activity at most once per ``TOUCH_INTERVAL``; slide the idle expiry."""
        now = now or datetime.now(UTC)
        if now - session.last_seen_at < TOUCH_INTERVAL:
            return
        async with with_tenant(session.tenant_id) as conn:
            row = (await conn.execute(_TOUCH, {"now": now, "id": session.session_id})).first()
        if row is None:
            return
        updated = replace(session, last_seen_at=row[0], idle_expires_at=row[1])
        await self.cache.put(hash_sid(sid), updated, self._ttl(updated, now))


# --- per-request hand-over --------------------------------------------------------------------

_Expired = Literal["expired"]
_current: ContextVar[ResolvedSession | _Expired | None] = ContextVar(
    "aip_identity_session", default=None
)


def current_session() -> ResolvedSession | None:
    value = _current.get()
    return value if isinstance(value, ResolvedSession) else None


def session_expired() -> bool:
    """A session cookie was presented on this request but did not resolve."""
    return _current.get() == "expired"


def read_sid(headers: Headers) -> str | None:
    raw = headers.get("cookie")
    if not raw:
        return None
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(raw)
    except CookieError:
        return None
    morsel = jar.get(SID_COOKIE)
    if morsel is None or not morsel.value or len(morsel.value) > _MAX_SID_LEN:
        return None
    return morsel.value


class SessionMiddleware:
    """Resolve the session cookie once per HTTP request; see the module docstring."""

    def __init__(self, app: ASGIApp, *, store: SessionStore) -> None:
        self.app = app
        self.store = store

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sid = read_sid(Headers(scope=scope))
        if sid is None:
            await self.app(scope, receive, send)
            return
        session = await self.store.resolve(sid)
        token = _current.set(session if session is not None else "expired")
        try:
            if session is not None:
                await self.store.touch(sid, session)
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)


class SessionPrincipalResolver:
    """The identity ``PrincipalResolver``: the request's resolved session, else ``fallback``.

    ``fallback`` is the test-only header stub (``AIP_ENV=test`` + ``AUTH_TEST_STUB=1``) or nothing.
    """

    def __init__(self, fallback: PrincipalResolver | None = None) -> None:
        self._fallback = fallback

    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        session = current_session()
        if session is not None:
            return Principal(
                kind="user",
                tenant_id=session.tenant_id,
                user_id=session.user_id,
                user_class=session.user_class,
                session_id=session.session_id,
                aal=2 if session.aal >= 2 else 1,
                amr=list(session.amr),
                authenticated_at=session.authenticated_at,
            )
        if session_expired() or self._fallback is None:
            return None
        return await self._fallback.resolve(headers)
