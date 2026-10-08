"""Real-Postgres fixtures for the migrator tests (DATABASE-08). Never mocks the database.

Server selection, in order:

1. ``AIP_TEST_DATABASE_URL`` (a superuser URL): CI's ``pgvector/pgvector:pg16`` service container,
   or the local cluster prepared by ``.claude/hooks/session-start.sh``.
2. Testcontainers ``pgvector/pgvector:pg16`` when a Docker daemon is reachable.
3. Otherwise the tests are skipped locally and fail under CI (``CI`` is set).

Every test gets its own empty database (``CREATE DATABASE ... TEMPLATE template0``) that is
dropped afterwards; roles the session created are dropped at the end.

The bootstrap gives every AIP role a throwaway test password (``ROLE_PASSWORDS``) through the
``aip.*_password`` settings, exactly as deployments do; nothing reads a password from a file.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[5]
API_DIR = REPO_ROOT / "apps" / "api"
BOOTSTRAP_SQL = REPO_ROOT / "db" / "bootstrap" / "00_cluster.sql"
PG_IMAGE = "pgvector/pgvector:pg16"
OWNER = "aip_owner"
OWNER_PASSWORD = "aip_owner_test_only"  # throwaway test credential, not a secret
APP = "aip_app"
JOBS = "aip_jobs"
READONLY = "aip_readonly"
# Throwaway test credentials (not secrets), passed to the bootstrap as aip.<role>_password.
ROLE_PASSWORDS = {
    OWNER: OWNER_PASSWORD,
    APP: "aip_app_test_only",
    JOBS: "aip_jobs_test_only",
    READONLY: "aip_readonly_test_only",
}
_PASSWORD_SETTINGS = {
    OWNER: "aip.owner_password",
    APP: "aip.app_password",
    JOBS: "aip.jobs_password",
    READONLY: "aip.readonly_password",
}


def with_db(url: str, database: str, user: str | None = None, password: str | None = None) -> str:
    """Return ``url`` pointing at ``database`` (optionally as another user)."""
    u = make_url(url).set(drivername="postgresql", database=database)
    if user is not None:
        u = u.set(username=user, password=password)
    return u.render_as_string(hide_password=False)


async def _execute(url: str, sql: str) -> None:
    conn: Any = await asyncpg.connect(url)  # pyright: ignore[reportUnknownMemberType]
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _fetch(url: str, sql: str, *args: object) -> list[tuple[Any, ...]]:
    conn: Any = await asyncpg.connect(url)  # pyright: ignore[reportUnknownMemberType]
    try:
        rows = await conn.fetch(sql, *args)
        return [tuple(r) for r in rows]
    finally:
        await conn.close()


def execute(url: str, sql: str) -> None:
    """Run one or more statements (simple query protocol)."""
    asyncio.run(_execute(url, sql))


def fetch(url: str, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return asyncio.run(_fetch(url, sql, *args))


def _docker_reachable() -> bool:
    try:
        import docker  # pyright: ignore[reportMissingTypeStubs]

        client: Any = docker.from_env()  # pyright: ignore[reportUnknownMemberType]
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def pg_superuser_url() -> Iterator[str]:
    """Superuser URL of a Postgres 16 server with pgvector available."""
    env_url = os.environ.get("AIP_TEST_DATABASE_URL")
    if env_url:
        yield from _with_role_cleanup(env_url)
        return
    if _docker_reachable():
        from testcontainers.community.postgres import (  # pyright: ignore[reportMissingTypeStubs]
            PostgresContainer,
        )

        with PostgresContainer(
            PG_IMAGE, username="postgres", password="postgres", dbname="postgres", driver=None
        ) as container:
            yield container.get_connection_url()
        return
    message = "no Postgres: set AIP_TEST_DATABASE_URL or start a Docker daemon"
    if os.environ.get("CI"):
        pytest.fail(message)
    pytest.skip(message)


def _with_role_cleanup(url: str) -> Iterator[str]:
    roles = (APP, JOBS, READONLY, OWNER)  # runtime roles first: they hold grants, not objects
    existed = {
        r[0] for r in fetch(url, "SELECT rolname FROM pg_roles WHERE rolname = ANY($1)", roles)
    }
    yield url
    for role in roles:
        if role not in existed:
            # It may still own (or be granted) something in a concurrent run: then leave it.
            with contextlib.suppress(asyncpg.PostgresError):
                execute(url, f"DROP ROLE IF EXISTS {role}")


@dataclass(frozen=True)
class FreshDb:
    """An empty database on the test server, dropped after the test."""

    name: str
    superuser_url: str

    @property
    def owner_url(self) -> str:
        return with_db(self.superuser_url, self.name, OWNER, OWNER_PASSWORD)

    def role_url(self, role: str) -> str:
        """URL of this database as one of the AIP roles (after ``bootstrap()``)."""
        return with_db(self.superuser_url, self.name, role, ROLE_PASSWORDS[role])

    @property
    def app_url(self) -> str:
        return self.role_url(APP)

    def execute(self, sql: str) -> None:
        execute(self.superuser_url, sql)

    def fetch(self, sql: str, *args: object) -> list[tuple[Any, ...]]:
        return fetch(self.superuser_url, sql, *args)

    def bootstrap(self, *, skip_vector: bool = False) -> None:
        sql = BOOTSTRAP_SQL.read_text(encoding="utf-8")
        if skip_vector:
            lines = sql.splitlines()
            sql = "\n".join(ln for ln in lines if "CREATE EXTENSION IF NOT EXISTS vector" not in ln)
        settings = "".join(
            f"SELECT set_config('{_PASSWORD_SETTINGS[role]}', '{password}', false);\n"
            for role, password in ROLE_PASSWORDS.items()
        )
        self.execute(f"{settings}{sql}")

    def migrate(self) -> None:
        """Bootstrap the cluster, then ``aip-db migrate`` to head."""
        self.bootstrap()
        result = self.aip_db("migrate")
        assert result.returncode == 0, result.stderr

    def aip_db_env(self, url: str | None = None) -> dict[str, str]:
        return {**os.environ, "DATABASE_MIGRATOR_URL": url or self.owner_url}

    def aip_db(
        self, *args: str, url: str | None = None, timeout: float = 120
    ) -> subprocess.CompletedProcess[str]:
        """Run ``aip-db`` in a subprocess (Alembic's env.py owns its own event loop)."""
        return subprocess.run(
            aip_db_command(*args),
            env=self.aip_db_env(url),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def aip_db_popen(self, *args: str) -> subprocess.Popen[str]:
        return subprocess.Popen(
            aip_db_command(*args),
            env=self.aip_db_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


@pytest.fixture
def empty_db(pg_superuser_url: str) -> Iterator[FreshDb]:
    name = f"aip_test_{uuid.uuid4().hex[:12]}"
    execute(pg_superuser_url, f'CREATE DATABASE "{name}" TEMPLATE template0')
    try:
        yield FreshDb(name=name, superuser_url=with_db(pg_superuser_url, name))
    finally:
        execute(pg_superuser_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def aip_db_command(*args: str) -> list[str]:
    return [sys.executable, "-m", "aip.platform.db.migrator.cli", *args]


@pytest.fixture
def migrations_copy(tmp_path: Path) -> Path:
    """Copy alembic.ini and migrations/ into tmp (tests never write into the repo tree).

    Returns the copied ``alembic.ini``.
    """
    shutil.copy2(API_DIR / "alembic.ini", tmp_path / "alembic.ini")
    shutil.copytree(
        API_DIR / "migrations",
        tmp_path / "migrations",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return tmp_path / "alembic.ini"
