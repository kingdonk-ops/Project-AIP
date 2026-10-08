"""Fixtures for the ops tests (OPS-04): a migrated Postgres database and a Redis server.

Postgres comes from the DATABASE-08 fixtures (``AIP_TEST_DATABASE_URL``, else Testcontainers).

Redis, in order:

1. Testcontainers ``valkey/valkey:8-alpine`` (BSD-3, a Redis drop-in; ADR 0009) when Docker runs;
2. a local ``redis-server`` / ``valkey-server`` binary on a free port;
3. otherwise the tests are skipped locally and fail under CI (``CI`` is set).

Each test gets its own server so it can stop it.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    FreshDb,
    _docker_reachable,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    migrations_copy,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
)

REDIS_IMAGE = "valkey/valkey:8-alpine"


@dataclass
class RedisServer:
    url: str
    stop: Callable[[], None]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.2):
            return
        time.sleep(0.05)
    raise RuntimeError(f"redis did not start on port {port}")


@pytest.fixture
def redis_server() -> Iterator[RedisServer]:
    if _docker_reachable():
        from testcontainers.community.redis import (  # pyright: ignore[reportMissingTypeStubs]
            RedisContainer,
        )

        container: Any = RedisContainer(REDIS_IMAGE)
        container.start()
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        stopped = False

        def stop_container() -> None:
            nonlocal stopped
            if not stopped:
                stopped = True
                container.stop()

        try:
            yield RedisServer(url=f"redis://{host}:{port}/0", stop=stop_container)
        finally:
            stop_container()
        return

    binary = shutil.which("valkey-server") or shutil.which("redis-server")
    if binary is None:
        message = "no Redis: start a Docker daemon or install redis-server"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)

    port = _free_port()
    proc = subprocess.Popen(
        [binary, "--port", str(port), "--bind", "127.0.0.1", "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def stop_process() -> None:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)

    try:
        _wait_for_port(port)
        yield RedisServer(url=f"redis://127.0.0.1:{port}/0", stop=stop_process)
    finally:
        stop_process()
