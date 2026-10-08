"""login/start rate limit against a real Redis protocol server (IDENTITY-01 step 5).

Server, in order: Testcontainers ``valkey/valkey:8-alpine`` when Docker runs; a local
``redis-server``/``valkey-server`` binary; otherwise skipped locally and failed under CI.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from tests.platform.db.conftest import _docker_reachable  # pyright: ignore[reportPrivateUsage]

from aip.modules.identity.routes import get_login_rate_limiter
from aip.modules.identity.service import LoginRateLimiter


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def redis_url() -> Iterator[str]:
    if _docker_reachable():
        from testcontainers.redis import RedisContainer  # pyright: ignore[reportMissingTypeStubs]

        with RedisContainer("valkey/valkey:8-alpine") as container:
            host: Any = container.get_container_host_ip()
            port: Any = container.get_exposed_port(6379)
            yield f"redis://{host}:{port}/0"
        return
    binary = shutil.which("valkey-server") or shutil.which("redis-server")
    if binary is None:
        message = "no Redis: start a Docker daemon or install redis-server"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    port = _free_port()
    proc = subprocess.Popen(
        [binary, "--port", str(port), "--save", "", "--appendonly", "no", "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.2):
                break
            time.sleep(0.05)
        yield f"redis://127.0.0.1:{port}/0"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture
async def redis_client(app: FastAPI, redis_url: str) -> AsyncIterator[httpx.AsyncClient]:
    limiter = LoginRateLimiter.from_redis_url(redis_url)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("203.0.113.7", 1234)),
        base_url="https://app.example.test",
    ) as c:
        yield c


async def test_eleventh_call_in_a_minute_is_429(redis_client: httpx.AsyncClient) -> None:
    for i in range(10):
        r = await redis_client.post("/api/v1/auth/login/start", json={"email": "x@unknown.test"})
        assert r.status_code == 200, (i, r.text)
    r = await redis_client.post("/api/v1/auth/login/start", json={"email": "x@unknown.test"})
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"
