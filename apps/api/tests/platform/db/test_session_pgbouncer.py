"""DATABASE-02: ``with_tenant`` through PgBouncer in transaction-pooling mode (ADR 0002).

20 concurrent ``with_tenant`` transactions, alternating tenants A and B, share a PgBouncer pool of
a few server connections. Each must see only its own tenant's row, and none may hit a
prepared-statement error.

PgBouncer comes from, in order: a local ``pgbouncer`` binary (``AIP_TEST_PGBOUNCER`` or on
``PATH``), or a generic Testcontainers ``DockerContainer`` running ``PGBOUNCER_IMAGE`` on the host
network. Without either the test is skipped locally and fails under CI.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.platform.db.conftest import APP, ROLE_PASSWORDS, execute

from aip.platform.db.engine import EngineSettings, PoolMode, create_app_engine
from aip.platform.db.session import with_tenant
from aip.platform.db.templates import render_template

if TYPE_CHECKING:
    from tests.platform.db.conftest import FreshDb

PGBOUNCER_IMAGE = "edoburu/pgbouncer:v1.24.1-p1"
SERVER_POOL_SIZE = 4  # fewer server connections than concurrent transactions
PARALLEL = 20


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_port(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"PgBouncer did not listen on {port}")


def _pgbouncer_binary() -> str | None:
    explicit = os.environ.get("AIP_TEST_PGBOUNCER")
    if explicit:
        return explicit
    return shutil.which("pgbouncer") or shutil.which("pgbouncer", path="/usr/sbin:/usr/local/sbin")


def _docker_reachable() -> bool:
    try:
        import docker  # pyright: ignore[reportMissingTypeStubs]

        client: Any = docker.from_env()  # pyright: ignore[reportUnknownMemberType]
        client.ping()
        return True
    except Exception:
        return False


@contextmanager
def _run_binary(binary: str, db: FreshDb, port: int) -> Iterator[None]:
    server = make_url(db.superuser_url)
    workdir = Path(tempfile.mkdtemp(prefix="aip-pgbouncer-"))
    # PgBouncer refuses to run as root; then it runs as nobody and must read its files.
    workdir.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    (workdir / "userlist.txt").write_text(f'"{APP}" "{ROLE_PASSWORDS[APP]}"\n', encoding="utf-8")
    (workdir / "pgbouncer.ini").write_text(
        "\n".join(
            [
                "[databases]",
                f"{db.name} = host={server.host or '127.0.0.1'} port={server.port or 5432}"
                f" dbname={db.name}",
                "[pgbouncer]",
                "listen_addr = 127.0.0.1",
                f"listen_port = {port}",
                "unix_socket_dir =",
                "auth_type = scram-sha-256",
                f"auth_file = {workdir / 'userlist.txt'}",
                "pool_mode = transaction",
                f"default_pool_size = {SERVER_POOL_SIZE}",
                "max_client_conn = 200",
                "max_prepared_statements = 0",
                "ignore_startup_parameters = extra_float_digits",
                "",
            ]
        ),
        encoding="utf-8",
    )
    for name in ("userlist.txt", "pgbouncer.ini"):
        (workdir / name).chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    command = [binary, str(workdir / "pgbouncer.ini")]
    if os.geteuid() == 0:
        command[1:1] = ["-u", "nobody"]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_for_port(port)
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(workdir, ignore_errors=True)


@contextmanager
def _run_container(db: FreshDb, port: int) -> Iterator[None]:
    from testcontainers.core.container import (  # pyright: ignore[reportMissingTypeStubs]
        DockerContainer,
    )

    server = make_url(db.superuser_url)
    container: Any = (
        DockerContainer(PGBOUNCER_IMAGE)
        .with_env("DB_HOST", "127.0.0.1" if server.host in (None, "localhost") else server.host)
        .with_env("DB_PORT", str(server.port or 5432))
        .with_env("DB_NAME", db.name)
        .with_env("DB_USER", APP)
        .with_env("DB_PASSWORD", ROLE_PASSWORDS[APP])
        .with_env("AUTH_TYPE", "scram-sha-256")
        .with_env("POOL_MODE", "transaction")
        .with_env("DEFAULT_POOL_SIZE", str(SERVER_POOL_SIZE))
        .with_env("MAX_PREPARED_STATEMENTS", "0")
        .with_env("LISTEN_PORT", str(port))
        .with_kwargs(network_mode="host")
    )
    with container:
        _wait_for_port(port, timeout=60)
        yield


@pytest.fixture
def pgbouncer_url(empty_db: FreshDb) -> Iterator[str]:
    """``aip_app`` URL through PgBouncer (transaction mode) to a migrated, seeded database."""
    empty_db.migrate()
    execute(
        empty_db.owner_url, render_template("tenant_table", table="rls_probe", columns="note text")
    )
    for tenant in (TENANT_A_ID, TENANT_B_ID):
        execute(
            empty_db.owner_url,
            "BEGIN;\n"
            f"SELECT set_config('app.tenant_id', '{tenant}', true);\n"
            f"INSERT INTO rls_probe (id, tenant_id) VALUES (gen_random_uuid(), '{tenant}');\n"
            "COMMIT;\n",
        )

    port = _free_port()
    binary = _pgbouncer_binary()
    if binary is not None:
        runner = _run_binary(binary, empty_db, port)
    elif _docker_reachable():
        runner = _run_container(empty_db, port)
    else:
        message = "no PgBouncer: install pgbouncer, set AIP_TEST_PGBOUNCER or start Docker"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    url = (
        make_url(empty_db.app_url)
        .set(host="127.0.0.1", port=port)
        .render_as_string(hide_password=False)
    )
    with runner:
        yield url


@pytest.fixture
async def bouncer_engine(pgbouncer_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_app_engine(
        EngineSettings(url=pgbouncer_url, pool_mode=PoolMode.PGBOUNCER, pool_size=PARALLEL)
    )
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_parallel_tenants_through_pgbouncer_never_cross(bouncer_engine: AsyncEngine) -> None:
    async def read(i: int) -> tuple[Any, list[Any], int]:
        tenant = TENANT_A_ID if i % 2 == 0 else TENANT_B_ID
        async with with_tenant(tenant, engine=bouncer_engine) as conn:
            await conn.execute(text("SELECT pg_sleep(0.02)"))  # hold the server connection
            seen = (await conn.execute(text("SELECT tenant_id FROM rls_probe"))).scalars().all()
            pid = (await conn.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        return tenant, list(seen), int(pid)

    for _round in range(3):
        results = await asyncio.gather(*(read(i) for i in range(PARALLEL)))
        for tenant, seen, _pid in results:
            assert seen == [tenant]
        # PgBouncer really multiplexed: fewer server backends than concurrent transactions.
        assert len({pid for *_, pid in results}) <= SERVER_POOL_SIZE

    # And outside with_tenant, a pooled server connection carries no tenant.
    async with bouncer_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM rls_probe"))).scalar_one() == 0
