"""Build evidence for releases and audits (STACK-05).

- ``GET /api/v1/platform/version`` (public, like the health probes): ``build`` / ``commit``, from
  ``BUILD_ID`` / ``GIT_SHA`` baked into the image as env and labels at build time
  (``apps/api/Dockerfile``). Unset means a local run: ``dev`` / ``unknown``. Deploy checks
  (``tools/smoke.py --expect-commit``) read ``commit`` anonymously.
- ``GET /api/v1/platform/version/dependencies`` (any signed-in user): library versions from
  ``importlib.metadata`` (``not-installed`` when a library is absent), ``python`` from
  ``platform.python_version()``, and ``postgres`` from ``SHOW server_version`` over
  ``DATABASE_URL``. When the database is unset, unreachable or slower than 2 s, ``postgres`` is
  ``"unavailable"`` and the status is still 200.

Review 11 M5: dependency versions are not public (fingerprinting), and the Postgres version is
read once per process (the first success is kept), not over a fresh connection per request.
"""

from __future__ import annotations

import asyncio
import os
import platform
from importlib import metadata
from typing import Protocol, cast

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.engine import make_url

from aip.platform.access import authenticated, public
from aip.platform.db.tls import DbTls

__all__ = ["Dependencies", "VersionResponse", "dependencies_router", "router"]

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
            ssl=DbTls.from_env().asyncpg_ssl(),  # STACK-07
        ),
    )
    try:
        return str(await conn.fetchval("SHOW server_version"))
    finally:
        await conn.close()


# The server version does not change under a running process (a major upgrade restarts it), so
# the first successful read is kept for the process lifetime. Failures are not cached.
_postgres_version: str | None = None


async def postgres_version() -> str:
    global _postgres_version
    if _postgres_version is not None:
        return _postgres_version
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return UNAVAILABLE
    try:
        _postgres_version = await asyncio.wait_for(_server_version(database_url), DB_TIMEOUT_S)
    except Exception as exc:
        # Class name only: the URL (with its password) must never reach the log.
        logger.warning("postgres version unavailable", error=type(exc).__name__)
        return UNAVAILABLE
    return _postgres_version


def reset_postgres_version_cache() -> None:
    """Forget the cached server version (tests switch databases within one process)."""
    global _postgres_version
    _postgres_version = None


router = APIRouter(prefix="/platform", tags=["platform"], dependencies=[Depends(public())])
dependencies_router = APIRouter(
    prefix="/platform", tags=["platform"], dependencies=[Depends(authenticated())]
)


@router.get("/version")
async def version() -> VersionResponse:
    return VersionResponse(
        build=os.environ.get("BUILD_ID") or "dev",
        commit=os.environ.get("GIT_SHA") or "unknown",
    )


@dependencies_router.get("/version/dependencies")
async def version_dependencies() -> Dependencies:
    libraries = {name: _library_version(name) for name in LIBRARIES}
    return Dependencies(
        python=platform.python_version(),
        postgres=await postgres_version(),
        **libraries,
    )
