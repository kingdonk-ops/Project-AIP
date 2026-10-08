"""GET /api/v1/platform/version (STACK-05).

Unit tests drive ``create_app()`` through ``httpx.AsyncClient``; the integration test reads the
server version from a real Postgres (``AIP_TEST_DATABASE_URL`` or Testcontainers, never mocked).
"""

from __future__ import annotations

import platform
import socket
import sys
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from aip.main import create_app
from tests.platform.db.conftest import pg_superuser_url  # noqa: F401 - pytest fixture

URL = "/api/v1/platform/version"
DEPENDENCIES = {
    "python",
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "procrastinate",
    "postgres",
}


def _closed_port() -> int:
    """A local TCP port nothing listens on (bound, then released)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def app() -> FastAPI:
    return create_app(tracing=False)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"postgresql://aip:aip@127.0.0.1:{_closed_port()}/aip")


async def test_commit_comes_from_git_sha(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, db_down: None
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("BUILD_ID", "build-42")

    response = await client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["commit"] == "abc123"
    assert body["build"] == "build-42"
    assert set(body["dependencies"]) == DEPENDENCIES
    # The spec pins 3.12 (the image's Python); CI also runs 3.13, so match the running minor.
    python = body["dependencies"]["python"]
    assert python == platform.python_version()
    assert python.startswith(f"{sys.version_info.major}.{sys.version_info.minor}.")
    if sys.version_info[:2] == (3, 12):
        assert python.startswith("3.12")


async def test_library_versions_come_from_installed_metadata(
    client: httpx.AsyncClient, db_down: None
) -> None:
    from importlib.metadata import version

    deps = (await client.get(URL)).json()["dependencies"]

    for name in ("fastapi", "pydantic", "sqlalchemy", "alembic"):
        assert deps[name] == version(name)
    # Procrastinate lands with OPS-02; until then it is reported, not an error.
    assert isinstance(deps["procrastinate"], str) and deps["procrastinate"]


async def test_db_unreachable_reports_unavailable_with_200(
    client: httpx.AsyncClient, db_down: None
) -> None:
    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json()["dependencies"]["postgres"] == "unavailable"


async def test_database_url_unset_reports_unavailable(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json()["dependencies"]["postgres"] == "unavailable"


async def test_defaults_without_build_env(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, db_down: None
) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("BUILD_ID", raising=False)

    body = (await client.get(URL)).json()

    assert body["commit"] == "unknown"
    assert body["build"] == "dev"


async def test_route_is_public_and_in_openapi(app: FastAPI) -> None:
    schema = app.openapi()
    operation = schema["paths"][URL]["get"]
    assert operation["operationId"] == "platform_version"


async def test_postgres_version_from_real_server(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    pg_superuser_url: str,  # noqa: F811
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_superuser_url)

    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json()["dependencies"]["postgres"].startswith("16")
