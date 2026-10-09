"""The shared real-Postgres fixtures (TESTING-01), documented in ``tests/README.md``.

Never mocks the database.

Server selection (``select_postgres_source``):

1. ``AIP_TEST_DATABASE_URL`` (a superuser URL): CI's db job service container, or the local
   cluster prepared by ``.claude/hooks/session-start.sh``.
2. Testcontainers ``pgvector/pgvector:pg16`` when the variable is unset and a Docker daemon is
   reachable.
3. Otherwise the tests are skipped locally and fail under CI (``CI`` is set).

Every test gets its own database (``CREATE DATABASE ... TEMPLATE template0``) that is dropped
afterwards; roles the session created are dropped at the end.

The bootstrap gives every AIP role a throwaway test password (``ROLE_PASSWORDS``) through the
``aip.*_password`` settings, exactly as deployments do; nothing reads a password from a file.

Layers, each building on the previous:

* ``pg_superuser_url`` (session) -> ``empty_db`` -> ``bootstrapped_db`` -> ``migrated_db``: a
  database at Alembic head, roles bootstrapped (``aip_owner`` migrates, ``aip_app`` is the
  runtime role).
* ``tenant_db`` -> a ``TenantDb``: an ``aip_app`` engine on ``migrated_db`` plus ``with_tenant``.
  This is what tenant-data assertions use. ``assert_unprivileged_role`` fails the test if the
  engine's role is a superuser, owner or BYPASSRLS role.
* ``owner_conn_for_seeding_only`` -> ``OwnerSeeder``: runs DDL/DML as ``aip_owner`` and returns
  nothing, so it cannot be used to assert on tenant data.

Cluster-wide DDL (roles, ``ALTER DATABASE``, grants on databases) updates shared catalogs. Agents
and CI jobs share one local cluster, so concurrent bootstraps used to fail with ``tuple
concurrently updated``. ``cluster_ddl_lock`` serialises them (an advisory lock taken in the
maintenance database, because advisory locks are per database) and ``retry_concurrent_update``
retries the rare leftover.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.session import TenantRef, with_tenant

REPO_ROOT = Path(__file__).resolve().parents[4]
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
# Advisory-lock key (any bigint) serialising cluster-wide DDL between concurrent test runs.
CLUSTER_DDL_LOCK_KEY = 7_340_113_001
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


class NoPostgresError(RuntimeError):
    """Neither ``AIP_TEST_DATABASE_URL`` nor a Docker daemon is available."""


def select_postgres_source(env_url: str | None, docker_reachable: bool) -> tuple[str, str | None]:
    """Pick the Postgres server: ``("url", <url>)``, ``("container", None)`` or raise.

    The URL wins even when Docker is reachable (CI's db job and local runs set it).
    """
    if env_url:
        return ("url", env_url)
    if docker_reachable:
        return ("container", None)
    raise NoPostgresError("no Postgres: set AIP_TEST_DATABASE_URL or start a Docker daemon")


def is_concurrent_update_error(exc: BaseException) -> bool:
    """True for Postgres' ``tuple concurrently updated`` (XX000) and its deadlock cousins."""
    text_ = str(exc).lower()
    return "tuple concurrently updated" in text_ or "deadlock detected" in text_


def retry_concurrent_update[T](fn: Callable[[], T], *, attempts: int = 8) -> T:
    """Run ``fn``; retry with a short jittered back-off when another run updated a shared row."""
    for attempt in range(attempts):
        try:
            return fn()
        except asyncpg.PostgresError as exc:
            if not is_concurrent_update_error(exc) or attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1) + (uuid.uuid4().int % 50) / 1000)
    raise AssertionError("unreachable")


@contextlib.asynccontextmanager
async def _cluster_lock(url: str) -> AsyncIterator[None]:
    conn: Any = await asyncpg.connect(with_db(url, "postgres"))  # pyright: ignore[reportUnknownMemberType]
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", CLUSTER_DDL_LOCK_KEY)
        try:
            yield
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", CLUSTER_DDL_LOCK_KEY)
    finally:
        await conn.close()


def cluster_ddl(url: str, sql: str) -> None:
    """Run cluster-wide DDL (role creation, bootstrap) safely beside other runs on the cluster.

    Holds a session advisory lock in the ``postgres`` database (advisory locks are per database,
    so a lock in the test database would not serialise two test databases), and retries a
    ``tuple concurrently updated`` raised by a writer outside the lock (for example the
    migrator's own ``ALTER ROLE`` revision).
    """

    async def run() -> None:
        async with _cluster_lock(url):
            await _execute(url, sql)

    retry_concurrent_update(lambda: asyncio.run(run()))


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
    try:
        kind, env_url = select_postgres_source(
            os.environ.get("AIP_TEST_DATABASE_URL"), _docker_reachable()
        )
    except NoPostgresError as exc:
        if os.environ.get("CI"):
            pytest.fail(str(exc))
        pytest.skip(str(exc))
    if kind == "url":
        assert env_url is not None
        yield from _with_role_cleanup(env_url)
        return
    from testcontainers.community.postgres import (  # pyright: ignore[reportMissingTypeStubs]
        PostgresContainer,
    )

    with PostgresContainer(
        PG_IMAGE, username="postgres", password="postgres", dbname="postgres", driver=None
    ) as container:
        yield container.get_connection_url()


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
                retry_concurrent_update(
                    lambda role=role: execute(url, f"DROP ROLE IF EXISTS {role}")
                )


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
        cluster_ddl(self.superuser_url, f"{settings}{sql}")

    def migrate(self) -> None:
        """Bootstrap the cluster, then ``aip-db migrate`` to head."""
        self.bootstrap()
        result = self.aip_db("migrate")
        for _ in range(4):  # the revisions also touch shared catalogs (roles, grants)
            if result.returncode == 0 or not is_concurrent_update_error(
                RuntimeError(result.stderr)
            ):
                break
            time.sleep(0.2)
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


@pytest.fixture
def bootstrapped_db(empty_db: FreshDb) -> FreshDb:
    """An empty database after the cluster bootstrap, with no revision applied."""
    empty_db.bootstrap()
    return empty_db


@pytest.fixture
def migrated_db(bootstrapped_db: FreshDb) -> FreshDb:
    """A freshly bootstrapped database migrated to head with ``aip-db migrate`` (as aip_owner)."""
    result = bootstrapped_db.aip_db("migrate")
    for _ in range(4):  # revisions also touch shared catalogs; see cluster_ddl
        if result.returncode == 0 or not is_concurrent_update_error(RuntimeError(result.stderr)):
            break
        time.sleep(0.2)
        result = bootstrapped_db.aip_db("migrate")
    assert result.returncode == 0, result.stderr
    return bootstrapped_db


# --- the non-owner ``aip_app`` connection and the privilege guard ------------------------------


class PrivilegedConnectionError(AssertionError):
    """A tenant-data assertion went through a role that bypasses or owns row-level security."""


def privileged_role_problem(
    *, user: str, rolsuper: bool, rolbypassrls: bool, owns_tables: bool
) -> str | None:
    """Why ``user`` may not be used for tenant-data assertions, or ``None`` if it may."""
    if rolsuper:
        return f"{user} is a SUPERUSER (bypasses row-level security)"
    if rolbypassrls:
        return f"{user} has BYPASSRLS"
    if user == OWNER or owns_tables:
        return f"{user} owns the tables (use it to seed, never to assert)"
    return None


def assert_unprivileged_url(url: str) -> None:
    """Fail unless ``url`` names a runtime role (``aip_app``/``aip_jobs``/``aip_readonly``).

    Static check on the user name; ``assert_unprivileged_role`` checks the live connection.
    """
    user = make_url(url).username
    if user not in (APP, JOBS, READONLY):
        raise PrivilegedConnectionError(
            f"tenant-data assertions must connect as {APP}, not {user!r}; "
            "use the tenant_db fixture (owner_conn_for_seeding_only is for seeding only)"
        )


_ROLE_POSTURE = text(
    """
    SELECT r.rolname, r.rolsuper, r.rolbypassrls,
           EXISTS (SELECT 1 FROM pg_class c WHERE c.relowner = r.oid
                   AND c.relnamespace = 'public'::regnamespace)
    FROM pg_roles r WHERE r.rolname = current_user
    """
)


async def assert_unprivileged_role(conn: AsyncConnection) -> None:
    """Fail unless the connection's role is neither superuser, BYPASSRLS nor a table owner."""
    row = (await conn.execute(_ROLE_POSTURE)).one()
    problem = privileged_role_problem(
        user=row[0], rolsuper=row[1], rolbypassrls=row[2], owns_tables=row[3]
    )
    if problem:
        raise PrivilegedConnectionError(problem)


@dataclass
class TenantDb:
    """An ``aip_app`` engine on a freshly migrated database, with ``with_tenant`` bound to it.

    ::

        async with tenant_db.with_tenant(TENANT_A_ID) as conn:
            rows = (await conn.execute(text("SELECT ..."))).all()

    Every ``with_tenant`` / ``no_tenant`` call checks the role posture
    (``assert_unprivileged_role``), so a fixture wired to the owner or a superuser fails loudly
    instead of passing for the wrong reason.
    """

    db: FreshDb
    engine: AsyncEngine

    @asynccontextmanager
    async def with_tenant(self, tenant: TenantRef) -> AsyncIterator[AsyncConnection]:
        async with with_tenant(tenant, engine=self.engine) as conn:
            await assert_unprivileged_role(conn)
            yield conn

    @asynccontextmanager
    async def no_tenant(self) -> AsyncIterator[AsyncConnection]:
        """An ``aip_app`` transaction with no tenant set: tenant tables must show 0 rows."""
        async with self.engine.begin() as conn:
            await assert_unprivileged_role(conn)
            yield conn


@pytest.fixture
async def tenant_db(migrated_db: FreshDb) -> AsyncIterator[TenantDb]:
    """The documented entry point: a fresh migrated database and an ``aip_app`` connection.

    ``aip_app`` is NOSUPERUSER, NOBYPASSRLS and owns nothing, so RLS always applies. Pool: 2
    connections, no overflow (small on purpose, so a tenant leaking between transactions on a
    reused connection would show).
    """
    assert_unprivileged_url(migrated_db.app_url)
    engine = create_app_engine(EngineSettings(url=migrated_db.app_url, pool_size=2, max_overflow=0))
    try:
        yield TenantDb(db=migrated_db, engine=engine)
    finally:
        await engine.dispose()


@dataclass(frozen=True)
class OwnerSeeder:
    """Seeds as ``aip_owner``. Returns nothing, so it cannot back an assertion on tenant data."""

    db: FreshDb

    def ddl(self, sql: str) -> None:
        """Create test-only tables etc. as the owner (for example from ``render_template``)."""
        execute(self.db.owner_url, sql)

    def insert(self, tenant: UUID, sql: str) -> None:
        """Run ``sql`` in a transaction with ``app.tenant_id`` set (FORCE RLS binds the owner)."""
        execute(
            self.db.owner_url,
            f"BEGIN;\nSELECT set_config('app.tenant_id', '{tenant}', true);\n{sql}\nCOMMIT;\n",
        )


@pytest.fixture
def owner_conn_for_seeding_only(migrated_db: FreshDb) -> OwnerSeeder:
    return OwnerSeeder(migrated_db)
