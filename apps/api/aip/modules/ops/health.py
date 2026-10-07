"""Liveness and readiness endpoints (OPS-04), mounted at ``/api/v1/health``.

- ``GET /api/v1/health/live``: 200 ``{"status": "ok"}`` whenever the process serves HTTP. It
  touches no dependency, so a database outage never gets healthy tasks killed.
- ``GET /api/v1/health/ready``: checks, concurrently and each within ``timeout`` (2 s):

  - ``db``: ``select 1`` over ``DATABASE_URL`` (the ``aip_app`` connection in deployed envs);
  - ``redis``: ``PING`` over ``REDIS_URL``;
  - ``migrations``: the database's ``alembic_version`` equals the head(s) of the Alembic script
    directory shipped with this build (``AIP_ALEMBIC_CONFIG``, default ``apps/api/alembic.ini``).

  All ok: 200 ``{"status": "ok", "checks": {...}}``; any failure: 503 with
  ``{"status": "fail", "checks": {"db": "ok", "redis": "fail: ...", "migrations": "ok"}}``.
  Failure text is only the error class, ``timeout``, ``... not set`` or ``not at head``;
  details (exceptions, both revision sets) go to the log, because the endpoint is
  unauthenticated.

- ``GET /api/v1/health``: the original ARCH-01 probe, kept as an alias of ``live``.

All routes are unauthenticated and not tenant-scoped. They are mounted directly by ``main.py``
(not through the module registry) so ``AIP_DISABLED_MODULES`` can never switch probes off.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.engine import make_url

__all__ = ["DEFAULT_ALEMBIC_CONFIG", "ReadinessChecker", "router"]

DEFAULT_ALEMBIC_CONFIG = Path(__file__).resolve().parents[3] / "alembic.ini"
DATABASE_URL_ENV = "DATABASE_URL"
REDIS_URL_ENV = "REDIS_URL"
ALEMBIC_CONFIG_ENV = "AIP_ALEMBIC_CONFIG"
DEFAULT_TIMEOUT = 2.0

logger = structlog.stdlib.get_logger(__name__)


NOT_AT_HEAD = "not at head"


class CheckFailedError(Exception):
    """A check failure whose message is safe to return from the endpoint.

    ``detail`` is logged server-side only.
    """

    def __init__(self, message: str, **detail: str) -> None:
        super().__init__(message)
        self.detail = detail


def _libpq_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


class ReadinessChecker:
    """Runs the readiness checks. Build one per app; ``from_env()`` reads the environment."""

    def __init__(
        self,
        *,
        database_url: str | None,
        redis_url: str | None,
        alembic_config: Path = DEFAULT_ALEMBIC_CONFIG,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.database_url = database_url
        self.redis_url = redis_url
        self.alembic_config = alembic_config
        self.timeout = timeout
        self._heads: frozenset[str] | None = None
        self._version_table: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ReadinessChecker:
        env = os.environ if environ is None else environ
        return cls(
            database_url=env.get(DATABASE_URL_ENV) or None,
            redis_url=env.get(REDIS_URL_ENV) or None,
            alembic_config=Path(env.get(ALEMBIC_CONFIG_ENV) or DEFAULT_ALEMBIC_CONFIG),
        )

    def _script_heads(self) -> tuple[frozenset[str], str]:
        if self._heads is None or self._version_table is None:
            config = Config(str(self.alembic_config))
            schema = config.get_main_option("version_table_schema")
            self._heads = frozenset(ScriptDirectory.from_config(config).get_heads())
            self._version_table = f"{schema}.alembic_version" if schema else "alembic_version"
        return self._heads, self._version_table

    async def _connect(self) -> Any:
        if not self.database_url:
            raise CheckFailedError(f"{DATABASE_URL_ENV} not set")
        return await asyncpg.connect(  # pyright: ignore[reportUnknownMemberType]
            _libpq_url(self.database_url),
            timeout=self.timeout,  # pyright: ignore[reportArgumentType] - asyncpg takes float
            statement_cache_size=0,
        )

    async def check_db(self) -> None:
        conn = await self._connect()
        try:
            await conn.fetchval("select 1")
        finally:
            await conn.close()

    async def check_redis(self) -> None:
        if not self.redis_url:
            raise CheckFailedError(f"{REDIS_URL_ENV} not set")
        client = Redis.from_url(
            self.redis_url, socket_connect_timeout=self.timeout, socket_timeout=self.timeout
        )
        try:
            await client.ping()  # pyright: ignore[reportUnknownMemberType]
        finally:
            await client.aclose()

    async def check_migrations(self) -> None:
        heads, table = self._script_heads()
        conn = await self._connect()
        try:
            try:
                rows = await conn.fetch(f"select version_num from {table}")
            except asyncpg.UndefinedTableError:
                raise CheckFailedError(
                    NOT_AT_HEAD, db_revisions="none (no alembic_version table)"
                ) from None
        finally:
            await conn.close()
        current = frozenset(str(row[0]) for row in rows)
        if current != heads:
            # Revisions go to the server log only; the unauthenticated endpoint says "not at head".
            raise CheckFailedError(
                NOT_AT_HEAD,
                db_revisions=",".join(sorted(current)) or "none",
                code_heads=",".join(sorted(heads)),
            )

    async def _run_one(self, name: str, check: Callable[[], Awaitable[None]]) -> str:
        try:
            await asyncio.wait_for(check(), self.timeout)
        except TimeoutError:
            logger.warning("readiness check timed out", check=name, timeout_s=self.timeout)
            return "fail: timeout"
        except CheckFailedError as exc:
            logger.warning("readiness check failed", check=name, reason=str(exc), **exc.detail)
            return f"fail: {exc}"
        except Exception as exc:
            logger.warning("readiness check failed", check=name, exc_info=True)
            return f"fail: {type(exc).__name__}"
        return "ok"

    async def run(self) -> dict[str, str]:
        names = ("db", "redis", "migrations")
        results = await asyncio.gather(
            self._run_one("db", self.check_db),
            self._run_one("redis", self.check_redis),
            self._run_one("migrations", self.check_migrations),
        )
        return dict(zip(names, results, strict=True))


router = APIRouter(prefix="/health", tags=["platform"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", responses={503: {"description": "A dependency check failed"}})
async def ready(request: Request) -> JSONResponse:
    checker: ReadinessChecker = request.app.state.readiness
    checks = await checker.run()
    healthy = all(result == "ok" for result in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "fail", "checks": checks},
        status_code=200 if healthy else 503,
    )
