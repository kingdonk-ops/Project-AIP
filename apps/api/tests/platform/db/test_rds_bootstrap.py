"""OPS-16: ``db/bootstrap/00_cluster.sql`` run the way the RDS bootstrap runbook runs it.

Amazon RDS gives no SUPERUSER. Its master user has ``rds_superuser`` with CREATEROLE and CREATEDB,
and owns the database it creates. The closest local stand-in is a role with exactly those
attributes, on a fresh cluster of its own (roles are cluster-wide, so the shared test server, where
the ``aip_*`` roles already exist, would not show what a new RDS instance does).

Each statement of the script runs separately as the stand-in, and the statements that fail are the
ones the runbook (docs/runbooks/rds-bootstrap.md) calls out:

- without ``createrole_self_grant = 'set, inherit'`` the bootstrap block fails at ``ALTER DATABASE
  ... OWNER TO aip_owner`` (the master cannot ``SET ROLE aip_owner``), and nothing is created;
- with it, only ``CREATE EXTENSION vector`` fails (pgvector is not a trusted extension). On RDS
  ``rds_superuser`` may create it, because it is on RDS's extension allow-list.

Then ``aip-db migrate`` runs as ``aip_owner``, so the platform-roles revision's privilege check is
exercised against roles the stand-in created.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from tests.fixtures.postgres import _docker_reachable  # pyright: ignore[reportPrivateUsage]

from aip.platform.db.migrator.lint import _segments  # pyright: ignore[reportPrivateUsage]

ROOT = Path(__file__).resolve().parents[5]
BOOTSTRAP = ROOT / "db" / "bootstrap" / "00_cluster.sql"
IMAGE = os.environ.get("AIP_TEST_POSTGRES_IMAGE", "pgvector/pgvector:pg16")
MASTER, MASTER_PW = "rds_master", "rds_master_test_only"
PASSWORDS = {
    "aip.owner_password": "owner_test_only",
    "aip.app_password": "app_test_only",
    "aip.jobs_password": "jobs_test_only",
    "aip.readonly_password": "readonly_test_only",
    "aip.audit_writer_password": "audit_test_only",
}
AIP_ROLES = ("aip_app", "aip_audit_writer", "aip_jobs", "aip_owner", "aip_readonly")


def statements(sql: str) -> list[str]:
    """Split on ``;`` outside comments, strings and dollar-quoted bodies (the DO block is one)."""
    out: list[str] = []
    current = ""
    for kind, text in _segments(sql):
        if kind == "comment":
            continue
        if kind != "code":
            current += text
            continue
        first, *rest = text.split(";")  # only this code segment: never inside a quoted body
        if not rest:
            current += first
            continue
        out.append(current + first)
        out.extend(rest[:-1])
        current = rest[-1]
    out.append(current)
    return [s.strip() for s in out if s.strip()]


def test_the_splitter_keeps_the_bootstrap_block_whole() -> None:
    parts = statements(BOOTSTRAP.read_text(encoding="utf-8"))
    assert parts[0].startswith("DO $bootstrap$") and parts[0].endswith("$bootstrap$")
    assert parts[-1] == "CREATE EXTENSION IF NOT EXISTS vector"
    assert len(parts) == 5


@pytest.fixture(scope="module")
def cluster() -> Iterator[str]:
    """A fresh Postgres cluster; yields its superuser URL (host:port, database ``postgres``)."""
    if not _docker_reachable():
        if os.environ.get("CI"):
            pytest.fail("Docker is needed for the RDS bootstrap test")
        pytest.skip("Docker is needed for the RDS bootstrap test")
    from testcontainers.core.container import (  # pyright: ignore[reportMissingTypeStubs]
        DockerContainer,
    )

    container: Any = DockerContainer(IMAGE)
    container.with_exposed_ports(5432)
    container.with_env("POSTGRES_PASSWORD", "postgres")
    with container:
        host = container.get_container_host_ip()
        url = f"postgresql://postgres:postgres@{host}:{container.get_exposed_port(5432)}/postgres"
        deadline = time.monotonic() + 90
        while True:
            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        f"import asyncio,asyncpg; asyncio.run(asyncpg.connect('{url}'))",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
                break
            except subprocess.SubprocessError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        yield url


def _url(base: str, user: str, password: str, database: str) -> str:
    host = base.split("@", 1)[1].rsplit("/", 1)[0]
    return f"postgresql://{user}:{password}@{host}/{database}"


async def _fresh_database(superuser: str, name: str) -> None:
    conn: Any = await asyncpg.connect(superuser)  # pyright: ignore[reportUnknownMemberType]
    try:
        for role in AIP_ROLES:  # every case starts from a cluster with no AIP roles
            exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
            if exists:
                for db in await conn.fetch(
                    "SELECT datname FROM pg_database WHERE NOT datistemplate"
                ):
                    target: Any = await asyncpg.connect(
                        _url(superuser, "postgres", "postgres", db[0])
                    )  # pyright: ignore[reportUnknownMemberType]
                    try:
                        await target.execute(f'DROP OWNED BY "{role}" CASCADE')
                    finally:
                        await target.close()
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        for role in AIP_ROLES:
            await conn.execute(f'DROP ROLE IF EXISTS "{role}"')
        if not await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", MASTER):
            await conn.execute(
                f"CREATE ROLE {MASTER} LOGIN PASSWORD '{MASTER_PW}' CREATEROLE CREATEDB"
            )
        await conn.execute(f'CREATE DATABASE "{name}" OWNER {MASTER}')
    finally:
        await conn.close()


async def _run_as_master(cluster: str, database: str, *, self_grant: bool) -> list[tuple[str, str]]:
    """Run each bootstrap statement as the stand-in; return (statement head, error) failures."""
    settings = dict(PASSWORDS)
    if self_grant:
        settings["createrole_self_grant"] = "set, inherit"
    conn: Any = await asyncpg.connect(  # pyright: ignore[reportUnknownMemberType]
        _url(cluster, MASTER, MASTER_PW, database), server_settings=settings
    )
    failures: list[tuple[str, str]] = []
    try:
        for statement in statements(BOOTSTRAP.read_text(encoding="utf-8")):
            try:
                await conn.execute(statement)
            except asyncpg.PostgresError as exc:
                # The first line only: the HINT that follows varies by server version.
                failures.append((statement.split("\n", 1)[0][:60], str(exc).split("\n", 1)[0]))
    finally:
        await conn.close()
    return failures


async def test_without_the_self_grant_the_master_cannot_hand_the_database_to_aip_owner(
    cluster: str,
) -> None:
    await _fresh_database(cluster, "aip_no_grant")
    failures = await _run_as_master(cluster, "aip_no_grant", self_grant=False)
    heads = [head for head, _ in failures]
    assert heads[0] == "DO $bootstrap$"
    assert 'must be able to SET ROLE "aip_owner"' in failures[0][1]
    assert "CREATE EXTENSION IF NOT EXISTS vector" in heads


async def test_with_the_self_grant_only_pgvector_needs_more_than_rds_superuser(
    cluster: str,
) -> None:
    await _fresh_database(cluster, "aip_rds")
    failures = await _run_as_master(cluster, "aip_rds", self_grant=True)
    assert failures == [
        ("CREATE EXTENSION IF NOT EXISTS vector", 'permission denied to create extension "vector"')
    ]
    conn: Any = await asyncpg.connect(cluster)  # pyright: ignore[reportUnknownMemberType]
    try:
        roles = await conn.fetch(
            "SELECT rolname, rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication"
            " OR rolbypassrls FROM pg_roles WHERE rolname LIKE 'aip\\_%' ORDER BY 1"
        )
        owner = await conn.fetchval(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = 'aip_rds'"
        )
        public_connect = await conn.fetchval(
            "SELECT has_database_privilege('public', 'aip_rds', 'CONNECT')"
        )
    finally:
        await conn.close()
    assert [(r[0], r[1]) for r in roles] == [(role, False) for role in AIP_ROLES]
    assert owner == "aip_owner"
    assert public_connect is False

    # On RDS the master user creates pgvector (allow-listed); here the superuser stands in for it.
    db: Any = await asyncpg.connect(_url(cluster, "postgres", "postgres", "aip_rds"))  # pyright: ignore[reportUnknownMemberType]
    try:
        await db.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await db.close()

    env = {
        **os.environ,
        "DATABASE_MIGRATOR_URL": _url(
            cluster, "aip_owner", PASSWORDS["aip.owner_password"], "aip_rds"
        ),
    }
    env.pop("AIP_ENV", None)
    result = subprocess.run(
        [sys.executable, "-m", "aip.platform.db.migrator.cli", "migrate"],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
