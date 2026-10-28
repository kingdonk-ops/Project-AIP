"""The cross-request cache of resolved grants (ACCESS-04, ADR 0039; Redis is a cache only, ADR 0003).

Keys, built with the TENANCY-02 ``redis_key`` builder, for tenant ``t`` and user ``u``:

- ``tenant:<t>:access:ver``: the tenant version (bumped when a change can touch anyone in the
  tenant, e.g. a role's permissions);
- ``tenant:<t>:access:ver:<u>``: the user version (bumped when the user's own assignments or team
  memberships change);
- ``tenant:<t>:access:grants:<u>:<user version>:<tenant version>``: the user's resolved grants,
  kept for ``CACHE_TTL_S``.

A bump orphans every older entry at once; the TTL bounds staleness if a bump is ever lost. The
versions are read before Postgres, so an entry written under a version never holds rows older
than that version. Every Redis error on a read (or an unreadable entry) is logged
(``access.cache_unavailable``) and treated as a miss, and Redis is then skipped for
``_BACKOFF_S``: the provider reads Postgres. ``bump`` always tries Redis and raises on failure (the
outbox subscriber then retries it).

Without ``REDIS_URL`` (unit tests, the e2e API) ``NullPolicyCache`` caches nothing.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Sequence
from typing import Any, Final, Protocol
from uuid import UUID

import structlog
from redis.asyncio import Redis

from aip.platform.db.tls import redis_tls_kwargs
from aip.platform.tenant_keys import redis_key

__all__ = [
    "CACHE_TTL_S",
    "GrantRow",
    "NullPolicyCache",
    "PolicyCache",
    "RedisPolicyCache",
    "Versions",
    "configure_policy_cache",
    "get_policy_cache",
    "grants_key",
    "version_key",
]

logger = structlog.stdlib.get_logger(__name__)

CACHE_TTL_S: Final = 300
# Version keys outlive every entry keyed by them, so an expired version (read as 0) can never
# revive an entry written under an earlier 0.
_VERSION_TTL_S: Final = 86_400
_TIMEOUT_S: Final = 0.5
_BACKOFF_S: Final = 5.0

GrantRow = tuple[str, str, str | None]
"""``(permission, "tenant" | "project", project id or None)``: one resolved grant."""

Versions = tuple[int, int]
"""``(user version, tenant version)``."""


def version_key(tenant_id: UUID | str, user_id: UUID | str | None = None) -> str:
    """The tenant version key, or with ``user_id`` that user's version key."""
    if user_id is None:
        return redis_key(tenant_id, "access", "ver")
    return redis_key(tenant_id, "access", "ver", str(user_id))


def grants_key(tenant_id: UUID | str, user_id: UUID | str, versions: Versions) -> str:
    user_version, tenant_version = versions
    return redis_key(
        tenant_id, "access", "grants", str(user_id), str(user_version), str(tenant_version)
    )


class PolicyCache(Protocol):
    async def versions(self, tenant_id: UUID, user_id: UUID) -> Versions | None:
        """The current versions, or ``None`` when the cache is unusable (bypass it)."""
        ...

    async def get(self, tenant_id: UUID, user_id: UUID, versions: Versions) -> list[GrantRow] | None:
        ...

    async def put(
        self, tenant_id: UUID, user_id: UUID, versions: Versions, rows: Sequence[GrantRow]
    ) -> None: ...

    async def bump(self, tenant_id: UUID, user_ids: Iterable[UUID] | None) -> None:
        """Invalidate the users' entries (``None``: the whole tenant). Raises if Redis fails."""
        ...


class NullPolicyCache:
    """No ``REDIS_URL``: every request resolves grants from Postgres."""

    async def versions(self, tenant_id: UUID, user_id: UUID) -> Versions | None:
        return None

    async def get(self, tenant_id: UUID, user_id: UUID, versions: Versions) -> list[GrantRow] | None:
        return None

    async def put(
        self, tenant_id: UUID, user_id: UUID, versions: Versions, rows: Sequence[GrantRow]
    ) -> None:
        return None

    async def bump(self, tenant_id: UUID, user_ids: Iterable[UUID] | None) -> None:
        return None


def _decode(raw: Any) -> list[GrantRow]:
    rows: list[GrantRow] = []
    for item in json.loads(raw):
        permission, scope, project = item
        if not isinstance(permission, str) or scope not in ("tenant", "project"):
            raise ValueError("unreadable grant entry")
        rows.append((permission, scope, None if project is None else str(project)))
    return rows


class RedisPolicyCache:
    def __init__(self, client: Redis) -> None:
        self._redis = client
        self._down_until = 0.0

    @classmethod
    def from_url(cls, url: str) -> RedisPolicyCache:
        client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            url,
            socket_connect_timeout=_TIMEOUT_S,
            socket_timeout=_TIMEOUT_S,
            **redis_tls_kwargs(url),  # STACK-07
        )
        return cls(client)

    def _down(self) -> bool:
        return time.monotonic() < self._down_until

    def _failed(self, op: str) -> None:
        # Skip Redis for a moment, so an unreachable server costs one timeout, not one per call.
        self._down_until = time.monotonic() + _BACKOFF_S
        logger.warning("access.cache_unavailable", op=op, exc_info=True)

    async def versions(self, tenant_id: UUID, user_id: UUID) -> Versions | None:
        if self._down():
            return None
        try:
            raw: list[Any] = await self._redis.mget(  # pyright: ignore[reportUnknownMemberType]
                [version_key(tenant_id, user_id), version_key(tenant_id)]
            )
            user_raw, tenant_raw = raw
            return (
                0 if user_raw is None else int(user_raw),
                0 if tenant_raw is None else int(tenant_raw),
            )
        except Exception:
            self._failed("versions")
            return None

    async def get(self, tenant_id: UUID, user_id: UUID, versions: Versions) -> list[GrantRow] | None:
        if self._down():
            return None
        try:
            raw: bytes | str | None = await self._redis.get(grants_key(tenant_id, user_id, versions))
            return None if raw is None else _decode(raw)
        except Exception:
            self._failed("get")
            return None

    async def put(
        self, tenant_id: UUID, user_id: UUID, versions: Versions, rows: Sequence[GrantRow]
    ) -> None:
        if self._down():
            return
        try:
            await self._redis.set(
                grants_key(tenant_id, user_id, versions),
                json.dumps([list(row) for row in rows]),
                ex=CACHE_TTL_S,
            )
        except Exception:
            self._failed("put")

    async def bump(self, tenant_id: UUID, user_ids: Iterable[UUID] | None) -> None:
        keys = (
            [version_key(tenant_id)]
            if user_ids is None
            else [version_key(tenant_id, user) for user in sorted(set(user_ids))]
        )
        if not keys:
            return
        async with self._redis.pipeline(transaction=False) as pipe:
            for key in keys:
                pipe.incr(key)  # pyright: ignore[reportUnknownMemberType]
                pipe.expire(key, _VERSION_TTL_S)  # pyright: ignore[reportUnknownMemberType]
            await pipe.execute()  # pyright: ignore[reportUnknownMemberType]

    async def aclose(self) -> None:
        await self._redis.aclose()


_cache: PolicyCache | None = None


def configure_policy_cache(cache: PolicyCache | None) -> None:
    """Use ``cache`` (``None``: rebuild from ``REDIS_URL`` on next use)."""
    global _cache
    _cache = cache


def get_policy_cache() -> PolicyCache:
    """The process cache, built from ``REDIS_URL`` on first use (none set: no cache)."""
    global _cache
    if _cache is None:
        url = os.environ.get("REDIS_URL")
        _cache = RedisPolicyCache.from_url(url) if url else NullPolicyCache()
    return _cache
