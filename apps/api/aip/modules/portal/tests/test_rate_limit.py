"""The portal's fixed-window limiter (PORTAL-02 step 5), on a fixed clock; the Valkey store
against a Testcontainers Valkey."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from tests.platform.db.conftest import _docker_reachable  # pyright: ignore[reportPrivateUsage]

from aip.modules.portal.rate_limit import (
    IP_LIMIT_ENV,
    SESSION_LIMIT_ENV,
    FixedWindowLimiter,
    MemoryWindowStore,
    PortalLimits,
    RedisWindowStore,
)


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


async def test_three_per_minute_then_retry_after_the_window() -> None:
    clock = Clock(6_000_000 + 15.0)  # 15 s into a clock minute
    limiter = FixedWindowLimiter(MemoryWindowStore(clock), 3, "session", clock=clock)
    hits = [await limiter.hit("s1") for _ in range(3)]
    assert all(h.allowed for h in hits)
    fourth = await limiter.hit("s1")
    assert (fourth.allowed, fourth.retry_after, fourth.first_refusal) == (False, 45, True)
    fifth = await limiter.hit("s1")
    assert (fifth.allowed, fifth.first_refusal) == (False, False)  # one event per key and window

    clock.now += 45  # the next window
    assert (await limiter.hit("s1")).allowed


async def test_two_keys_do_not_share_a_budget() -> None:
    clock = Clock(6_000_000.0)
    limiter = FixedWindowLimiter(MemoryWindowStore(clock), 3, "session", clock=clock)
    for _ in range(3):
        await limiter.hit("s1")
    assert not (await limiter.hit("s1")).allowed
    assert (await limiter.hit("s2")).allowed


async def test_once_is_true_only_the_first_time_until_forgotten() -> None:
    store = MemoryWindowStore(Clock(0.0))
    assert await store.once("k", 60)
    assert not await store.once("k", 60)
    await store.forget("k")
    assert await store.once("k", 60)


def test_limits_come_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    defaults = PortalLimits.from_env()
    assert (defaults.session.limit, defaults.ip.limit) == (120, 300)
    monkeypatch.setenv(SESSION_LIMIT_ENV, "10")
    monkeypatch.setenv(IP_LIMIT_ENV, "nonsense")
    limits = PortalLimits.from_env()
    assert (limits.session.limit, limits.ip.limit) == (10, 300)


@pytest.fixture
def valkey_url() -> Iterator[str]:
    """Testcontainers Valkey; skipped locally without Docker, failed under CI."""
    if not _docker_reachable():
        if os.environ.get("CI"):
            pytest.fail("no Docker: the shared rate-limit store cannot be tested")
        pytest.skip("no Docker for a Valkey container")
    from testcontainers.redis import RedisContainer  # pyright: ignore[reportMissingTypeStubs]

    with RedisContainer("valkey/valkey:8-alpine") as container:
        host: Any = container.get_container_host_ip()
        port: Any = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


async def test_the_valkey_store_shares_counts_and_once_between_limiters(valkey_url: str) -> None:
    clock = Clock(6_000_000.0)
    first, second = RedisWindowStore.from_url(valkey_url), RedisWindowStore.from_url(valkey_url)
    a = FixedWindowLimiter(first, 2, "session", clock=clock)
    b = FixedWindowLimiter(second, 2, "session", clock=clock)  # another API process
    assert (await a.hit("s1")).allowed
    assert (await b.hit("s1")).allowed
    refused = await a.hit("s1")
    assert (refused.allowed, refused.first_refusal, refused.retry_after) == (False, True, 60)
    assert await first.once("signed_in:s1", 60)
    assert not await second.once("signed_in:s1", 60)
