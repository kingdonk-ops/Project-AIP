"""``GET /api/v1/platform/version``: build evidence for releases and audits (STACK-05).

- ``build`` / ``commit``: ``BUILD_ID`` / ``GIT_SHA``, baked into the image as env and labels at
  build time (``apps/api/Dockerfile``). Unset means a local run: ``dev`` / ``unknown``.
- ``dependencies``: library versions from ``importlib.metadata`` (``not-installed`` when a library
  is absent, e.g. Procrastinate before OPS-02), ``python`` from ``platform.python_version()``, and
  ``postgres`` from ``SHOW server_version`` over ``DATABASE_URL``. When the database is unset,
  unreachable or slower than 2 s, ``postgres`` is ``"unavailable"`` and the status is still 200.

Unauthenticated and not tenant-scoped, like the health probes: it reveals versions only, no data.
"""

from __future__ import annotations

import asyncio
import os
import platform
from importlib import metadata
from typing import Protocol, cast

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import structlog
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.engine import make_url

__all__ = ["Dependencies", "VersionResponse", "router"]

UNAVAILABLE = "unavailable"
NOT_INSTALLED = "not-installed"
DB_TIMEOUT_S = 2.0
LIBRARIES = ("fastapi", "pydantic", "sqlalchemy", "alembic", "procrastinate")

logger = structlog.stdlib.get_logger(__name__)


class Dependencies(BaseModel):
    python: str
    fastapi: str
    pydantic: str
    sqlalchemy: str
    alembic: str
    procrastinate: str
    postgres: str


class VersionResponse(BaseModel):
    """Body of GET /api/v1/platform/version. Changing it changes the generated client."""

    build: str
    commit: str
    dependencies: Dependencies


def _library_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return NOT_INSTALLED


class _Connection(Protocol):
    """The two asyncpg connection methods used here (asyncpg ships no type stubs)."""

    async def fetchval(self, query: str) -> object: ...

    async def close(self) -> None: ...


async def _server_version(database_url: str) -> str:
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    conn = cast(
        _Connection,
        await asyncpg.connect(  # pyright: ignore[reportUnknownMemberType]
            url,
            timeout=DB_TIMEOUT_S,  # pyright: ignore[reportArgumentType] - asyncpg takes float
            statement_cache_size=0,
        ),
    )
    try:
        return str(await conn.fetchval("SHOW server_version"))
    finally:
        await conn.close()


async def postgres_version() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return UNAVAILABLE
    try:
        return await asyncio.wait_for(_server_version(database_url), DB_TIMEOUT_S)
    except Exception as exc:
        # Class name only: the URL (with its password) must never reach the log.
        logger.warning("postgres version unavailable", error=type(exc).__name__)
        return UNAVAILABLE


router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/version")
async def version() -> VersionResponse:
    libraries = {name: _library_version(name) for name in LIBRARIES}
    return VersionResponse(
        build=os.environ.get("BUILD_ID") or "dev",
        commit=os.environ.get("GIT_SHA") or "unknown",
        dependencies=Dependencies(
            python=platform.python_version(),
            postgres=await postgres_version(),
            **libraries,
        ),
    )
