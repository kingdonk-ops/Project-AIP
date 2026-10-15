"""The per-tenant Redis cache of resolved terminology (TERMS-02, ADR 0003: Redis is a cache only).

Keys, for tenant ``t`` at cache version ``v`` (a per-tenant counter, ``t:{t}:terms:version``):

- ``t:{t}:terms:{v}``: the tenant's merged map (default, active packs, tenant overrides) plus its
  default locale;
- ``t:{t}:terms:{v}:client:{id}`` and ``t:{t}:terms:{v}:project:{id}``: that scope's overrides.

Invalidation bumps the counter, so every older entry is orphaned at once and expires by its TTL.
Every Redis error is logged (``terms.cache_unavailable``) and treated as a miss: the resolver
then reads Postgres. The TTL also bounds staleness if a bump is lost during a Redis outage.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol
from uuid import UUID

import structlog
from redis.asyncio import Redis

__all__ = [
    "CACHE_TTL_S",
    "NullTermsCache",
    "RedisTermsCache",
    "TermsCache",
    "configure_cache",
    "get_cache",
]

logger = structlog.stdlib.get_logger(__name__)

CACHE_TTL_S = 300
_TIMEOUT_S = 0.5


def version_key(tenant_id: UUID) -> str:
    return f"t:{tenant_id}:terms:version"


def map_key(tenant_id: UUID, version: int, scope: str = "") -> str:
    return f"t:{tenant_id}:terms:{version}{scope}"


class TermsCache(Protocol):
    async def version(self, tenant_id: UUID) -> int | None:
        """The tenant's cache version, or ``None`` when the cache is unusable (bypass it)."""
        ...

    async def get(self, tenant_id: UUID, version: int, scope: str) -> Any | None: ...

    async def put(self, tenant_id: UUID, version: int, scope: str, value: Any) -> None: ...

    async def bump(self, tenant_id: UUID) -> None:
        """Invalidate every cached entry of the tenant. Raises if Redis is unreachable."""
        ...


class NullTermsCache:
    """No ``REDIS_URL``: every resolve reads Postgres."""

    async def version(self, tenant_id: UUID) -> int | None:
        return None

    async def get(self, tenant_id: UUID, version: int, scope: str) -> Any | None:
        return None

    async def put(self, tenant_id: UUID, version: int, scope: str, value: Any) -> None:
        return None

    async def bump(self, tenant_id: UUID) -> None:
        return None


class RedisTermsCache:
    def __init__(self, client: Redis) -> None:
        self._redis = client

    @classmethod
    def from_url(cls, url: str) -> RedisTermsCache:
        client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            url, socket_connect_timeout=_TIMEOUT_S, socket_timeout=_TIMEOUT_S
        )
        return cls(client)

    async def version(self, tenant_id: UUID) -> int | None:
        try:
            raw: bytes | str | None = await self._redis.get(version_key(tenant_id))
        except Exception:
            logger.warning("terms.cache_unavailable", op="version", exc_info=True)
            return None
        return 0 if raw is None else int(raw)

    async def get(self, tenant_id: UUID, version: int, scope: str) -> Any | None:
        try:
            raw: bytes | str | None = await self._redis.get(map_key(tenant_id, version, scope))
        except Exception:
            logger.warning("terms.cache_unavailable", op="get", exc_info=True)
            return None
        return None if raw is None else json.loads(raw)

    async def put(self, tenant_id: UUID, version: int, scope: str, value: Any) -> None:
        try:
            await self._redis.set(
                map_key(tenant_id, version, scope), json.dumps(value), ex=CACHE_TTL_S
            )
        except Exception:
            logger.warning("terms.cache_unavailable", op="put", exc_info=True)

    async def bump(self, tenant_id: UUID) -> None:
        await self._redis.incr(version_key(tenant_id))

    async def aclose(self) -> None:
        await self._redis.aclose()


_cache: TermsCache | None = None


def configure_cache(cache: TermsCache | None) -> None:
    """Use ``cache`` (``None``: rebuild from ``REDIS_URL`` on next use)."""
    global _cache
    _cache = cache


def get_cache() -> TermsCache:
    """The process cache, built from ``REDIS_URL`` on first use (none set: no cache)."""
    global _cache
    if _cache is None:
        url = os.environ.get("REDIS_URL")
        _cache = RedisTermsCache.from_url(url) if url else NullTermsCache()
    return _cache
