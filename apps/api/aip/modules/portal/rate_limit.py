"""Fixed-window rate limits on the portal routes (PORTAL-02 step 5).

Every ``/api/v1/portal/*`` request counts against two budgets: its session (default 120 per minute)
and its client IP (default 300 per minute), set by ``PORTAL_RATE_LIMIT_SESSION_PER_MIN`` and
``PORTAL_RATE_LIMIT_IP_PER_MIN``. A window is the clock minute, so a refused call waits
``60 - elapsed`` seconds (``Retry-After``). Over either budget the route answers 429
``{"code": "RATE_LIMITED"}`` and, for the first refused call of a key and window only, records a
``portal.rate_limited`` security event.

Counters live in Valkey (``REDIS_URL``), shared by every API process; without it (tests, a dev run
without Valkey) they live in this process. The same store gives ``once``: a key that is set only
the first time, which the ``portal.signed_in`` event uses (once per session, no table needed).
Sign-in attempts are limited by identity's own login limiter on the portal login routes.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

from redis.asyncio import Redis

from aip.platform.db.tls import redis_tls_kwargs

__all__ = [
    "IP_LIMIT_ENV",
    "SESSION_LIMIT_ENV",
    "FixedWindowLimiter",
    "Hit",
    "MemoryWindowStore",
    "PortalLimits",
    "RedisWindowStore",
    "WindowStore",
    "store_from_env",
]

logger = logging.getLogger(__name__)

SESSION_LIMIT_ENV: Final = "PORTAL_RATE_LIMIT_SESSION_PER_MIN"
IP_LIMIT_ENV: Final = "PORTAL_RATE_LIMIT_IP_PER_MIN"
DEFAULT_SESSION_LIMIT: Final = 120
DEFAULT_IP_LIMIT: Final = 300
WINDOW_SECONDS: Final = 60
_KEY_PREFIX: Final = "aip:portal:"


class WindowStore(Protocol):
    async def incr(self, key: str, ttl_seconds: int) -> int:
        """Add one to ``key`` (created with ``ttl_seconds``) and return the new count."""
        ...

    async def once(self, key: str, ttl_seconds: int) -> bool:
        """``True`` the first time ``key`` is set (until it expires), ``False`` after."""
        ...

    async def forget(self, key: str) -> None:
        """Remove ``key`` (a ``once`` whose work failed may be tried again)."""
        ...


class MemoryWindowStore:
    """This process only: tests and runs without Valkey. Expired keys are swept as it goes."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[int, float]] = {}

    def _live(self, key: str) -> int | None:
        entry = self._values.get(key)
        if entry is None or entry[1] <= self._clock():
            self._values.pop(key, None)
            return None
        return entry[0]

    def _sweep(self) -> None:
        if len(self._values) > 10_000:
            now = self._clock()
            self._values = {k: v for k, v in self._values.items() if v[1] > now}

    async def incr(self, key: str, ttl_seconds: int) -> int:
        self._sweep()
        current = self._live(key)
        if current is None:
            self._values[key] = (1, self._clock() + ttl_seconds)
            return 1
        self._values[key] = (current + 1, self._values[key][1])
        return current + 1

    async def once(self, key: str, ttl_seconds: int) -> bool:
        self._sweep()
        if self._live(key) is not None:
            return False
        self._values[key] = (1, self._clock() + ttl_seconds)
        return True

    async def forget(self, key: str) -> None:
        self._values.pop(key, None)


class RedisWindowStore:
    """Valkey, shared by every API process."""

    def __init__(self, client: Redis) -> None:
        self._redis = client

    @classmethod
    def from_url(cls, url: str) -> RedisWindowStore:
        return cls(Redis.from_url(url, **redis_tls_kwargs(url)))  # pyright: ignore[reportUnknownMemberType]

    async def incr(self, key: str, ttl_seconds: int) -> int:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(_KEY_PREFIX + key)
            pipe.expire(_KEY_PREFIX + key, ttl_seconds, nx=True)
            count, _ = await pipe.execute()
        return int(count)

    async def once(self, key: str, ttl_seconds: int) -> bool:
        return bool(await self._redis.set(_KEY_PREFIX + key, "1", ex=ttl_seconds, nx=True))

    async def forget(self, key: str) -> None:
        await self._redis.delete(_KEY_PREFIX + key)


def store_from_env() -> WindowStore:
    url = os.environ.get("REDIS_URL", "").strip()
    return RedisWindowStore.from_url(url) if url else MemoryWindowStore()


@dataclass(frozen=True, slots=True)
class Hit:
    allowed: bool
    retry_after: int  # seconds until the next window; 0 when allowed
    first_refusal: bool  # the first refused call of this key and window


class FixedWindowLimiter:
    """``limit`` calls per key per clock minute."""

    def __init__(
        self,
        store: WindowStore,
        limit: int,
        name: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if limit < 1:
            raise ValueError("a rate limit must be at least 1")
        self._store = store
        self.limit = limit
        self._name = name
        self._clock = clock

    async def hit(self, key: str) -> Hit:
        now = self._clock()
        window = int(now // WINDOW_SECONDS)
        count = await self._store.incr(f"rl:{self._name}:{key}:{window}", WINDOW_SECONDS + 5)
        if count <= self.limit:
            return Hit(allowed=True, retry_after=0, first_refusal=False)
        elapsed = now - window * WINDOW_SECONDS
        retry_after = max(1, int(WINDOW_SECONDS - elapsed))
        return Hit(allowed=False, retry_after=retry_after, first_refusal=count == self.limit + 1)


def _limit(env: str, default: int) -> int:
    raw = os.environ.get(env, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s is not a whole number; using %d", env, default)
        return default
    return value if value >= 1 else default


@dataclass(frozen=True, slots=True)
class PortalLimits:
    """The portal's two limiters and the store they (and ``once``) share."""

    store: WindowStore
    session: FixedWindowLimiter
    ip: FixedWindowLimiter

    @classmethod
    def from_env(cls, store: WindowStore | None = None) -> PortalLimits:
        store = store_from_env() if store is None else store
        return cls(
            store=store,
            session=FixedWindowLimiter(
                store, _limit(SESSION_LIMIT_ENV, DEFAULT_SESSION_LIMIT), "session"
            ),
            ip=FixedWindowLimiter(store, _limit(IP_LIMIT_ENV, DEFAULT_IP_LIMIT), "ip"),
        )
