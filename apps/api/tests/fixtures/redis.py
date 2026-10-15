"""A real Redis protocol server for tests that need one and may stop it mid-test.

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
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from tests.fixtures.postgres import _docker_reachable  # pyright: ignore[reportPrivateUsage]

__all__ = ["RedisServer", "redis_server"]


@dataclass
class RedisServer:
    url: str
    _stop: Callable[[], None]

    def stop(self) -> None:
        """Stop the server now (a Redis outage); later stops are no-ops."""
        self._stop()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def redis_server() -> Iterator[RedisServer]:
    if _docker_reachable():
        from testcontainers.redis import RedisContainer  # pyright: ignore[reportMissingTypeStubs]

        container = RedisContainer("valkey/valkey:8-alpine")
        container.start()
        stopped = False

        def stop_container() -> None:
            nonlocal stopped
            if not stopped:
                stopped = True
                container.stop()

        try:
            host: Any = container.get_container_host_ip()
            port: Any = container.get_exposed_port(6379)
            yield RedisServer(f"redis://{host}:{port}/0", stop_container)
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
        [binary, "--port", str(port), "--save", "", "--appendonly", "no", "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def stop_proc() -> None:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)

    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.2):
                break
            time.sleep(0.05)
        yield RedisServer(f"redis://127.0.0.1:{port}/0", stop_proc)
    finally:
        stop_proc()
