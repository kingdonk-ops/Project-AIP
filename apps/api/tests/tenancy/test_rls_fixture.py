"""TESTING-01: the shared Postgres fixture, the ``aip_app`` role and the privilege guard.

Unit tests need no database. Integration tests use ``tenant_db`` (a freshly migrated database and
an ``aip_app`` engine) and double as the tenant-isolation example: ``rls_probe`` holds one row for
tenant A (``kaefer-demo``) and one for tenant B (``tenant-b``). Seeding goes through
``owner_conn_for_seeding_only``; every assertion goes through ``tenant_db``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from aip.platform.db.templates import render_template
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (
    FreshDb,
    NoPostgresError,
    OwnerSeeder,
    PrivilegedConnectionError,
    TenantDb,
    assert_unprivileged_role,
    assert_unprivileged_url,
    cluster_ddl,
    execute,
    fetch,
    is_concurrent_update_error,
    privileged_role_problem,
    retry_concurrent_update,
    select_postgres_source,
    with_db,
)

ROW_A = UUID("00000000-0000-4000-8000-0000000000aa")
ROW_B = UUID("00000000-0000-4000-8000-0000000000bb")
NOTES = text("SELECT note FROM rls_probe ORDER BY note")
COUNT = text("SELECT count(*) FROM rls_probe")

# --- unit: server selection --------------------------------------------------------------------


def test_url_wins_even_when_docker_is_reachable() -> None:
    assert select_postgres_source("postgresql://u@h/d", True) == ("url", "postgresql://u@h/d")
    assert select_postgres_source("postgresql://u@h/d", False) == ("url", "postgresql://u@h/d")


def test_container_is_used_when_the_url_is_unset_and_docker_runs() -> None:
    assert select_postgres_source(None, True) == ("container", None)
    assert select_postgres_source("", True) == ("container", None)


def test_neither_url_nor_docker_is_a_clear_error() -> None:
    with pytest.raises(NoPostgresError, match="AIP_TEST_DATABASE_URL"):
        select_postgres_source(None, False)


# --- unit: the privilege guard and the retry ---------------------------------------------------


def _problem(user: str, *, su: bool = False, bypass: bool = False, owns: bool = False) -> str:
    found = privileged_role_problem(user=user, rolsuper=su, rolbypassrls=bypass, owns_tables=owns)
    assert found is not None
    return found


def test_guard_rejects_superusers_bypassrls_and_owners() -> None:
    assert "SUPERUSER" in _problem("aip_test", su=True)
    assert "BYPASSRLS" in _problem("x", bypass=True)
    assert "owns" in _problem("aip_owner")
    assert "owns" in _problem("someone", owns=True)
    ok = privileged_role_problem(
        user="aip_app", rolsuper=False, rolbypassrls=False, owns_tables=False
    )
    assert ok is None


def test_guard_rejects_owner_and_superuser_urls_but_allows_runtime_roles() -> None:
    for user in ("aip_owner", "postgres", "aip_test"):
        with pytest.raises(PrivilegedConnectionError):
            assert_unprivileged_url(f"postgresql://{user}:pw@localhost/db")
    for user in ("aip_app", "aip_jobs", "aip_readonly"):
        assert_unprivileged_url(f"postgresql://{user}:pw@localhost/db")


def test_retry_retries_a_concurrent_update_and_nothing_else() -> None:
    calls = 0

    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise asyncpg.InternalServerError("tuple concurrently updated")
        return "ok"

    assert retry_concurrent_update(flaky) == "ok"
    assert calls == 3

    def broken() -> None:
        raise asyncpg.InternalServerError("disk full")

    with pytest.raises(asyncpg.InternalServerError, match="disk full"):
        retry_concurrent_update(broken)

    def always() -> None:
        raise asyncpg.InternalServerError("tuple concurrently updated")

    with pytest.raises(asyncpg.InternalServerError):
        retry_concurrent_update(always, attempts=2)
    assert is_concurrent_update_error(RuntimeError("ERROR: tuple concurrently updated"))
    assert not is_concurrent_update_error(RuntimeError("syntax error"))


# --- integration: bootstrap and role creation are safe under concurrency -----------------------


def test_concurrent_role_ddl_does_not_fail(pg_superuser_url: str) -> None:
    """Many runs creating and altering the same cluster roles at once (the old failure mode)."""
    suffix = uuid.uuid4().hex[:10]
    roles = [f"aip_race_{suffix}_{i}" for i in range(3)]
    sql = "".join(
        f"""
        DO $r$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{r}') THEN
            CREATE ROLE {r} LOGIN NOSUPERUSER NOBYPASSRLS;
          END IF;
        END $r$;
        ALTER ROLE {r} PASSWORD 'throwaway_{suffix}';
        """
        for r in roles
    )
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for future in [pool.submit(cluster_ddl, pg_superuser_url, sql) for _ in range(16)]:
                future.result()
        found = fetch(
            pg_superuser_url, "SELECT count(*) FROM pg_roles WHERE rolname = ANY($1)", roles
        )
        assert found == [(3,)]
    finally:
        for r in roles:
            execute(pg_superuser_url, f"DROP ROLE IF EXISTS {r}")


def test_bootstrap_runs_concurrently_on_separate_databases(pg_superuser_url: str) -> None:
    names = [f"aip_test_{uuid.uuid4().hex[:12]}" for _ in range(6)]
    dbs: list[FreshDb] = []
    try:
        for name in names:
            execute(pg_superuser_url, f'CREATE DATABASE "{name}" TEMPLATE template0')
            dbs.append(FreshDb(name=name, superuser_url=with_db(pg_superuser_url, name)))
        with ThreadPoolExecutor(max_workers=6) as pool:
            for future in [pool.submit(db.bootstrap) for db in dbs]:
                future.result()
        for db in dbs:
            roles = db.fetch("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='aip_app'")
            assert roles == [(False, False)]
    finally:
        for name in names:
            execute(pg_superuser_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


# --- integration: the fixture and tenant isolation ---------------------------------------------


@pytest.fixture
def rls_probe(owner_conn_for_seeding_only: OwnerSeeder) -> Iterator[OwnerSeeder]:
    """``rls_probe`` from the tenant-table template, one row each for kaefer-demo and tenant-b."""
    seeder = owner_conn_for_seeding_only
    seeder.ddl(render_template("tenant_table", table="rls_probe", columns="note text"))
    for tenant, row, note in (
        (TENANT_A_ID, ROW_A, "kaefer-demo"),
        (TENANT_B_ID, ROW_B, "tenant-b"),
    ):
        seeder.insert(
            tenant,
            f"INSERT INTO rls_probe (id, tenant_id, note) VALUES ('{row}', '{tenant}', '{note}');",
        )
    yield seeder


async def test_aip_app_is_not_owner_superuser_or_bypassrls(tenant_db: TenantDb) -> None:
    async with tenant_db.no_tenant() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
        assert tuple(row) == ("aip_app", False, False, False, False)
        owned = (
            await conn.execute(
                text("SELECT count(*) FROM pg_class WHERE relowner = 'aip_app'::regrole")
            )
        ).scalar_one()
        assert owned == 0


async def test_each_tenant_sees_only_its_own_rows(
    tenant_db: TenantDb, rls_probe: OwnerSeeder
) -> None:
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        assert (await conn.execute(NOTES)).scalars().all() == ["kaefer-demo"]
    async with tenant_db.with_tenant(TENANT_B_ID) as conn:
        assert (await conn.execute(NOTES)).scalars().all() == ["tenant-b"]


async def test_no_tenant_reads_zero_rows_and_cannot_insert(
    tenant_db: TenantDb, rls_probe: OwnerSeeder
) -> None:
    async with tenant_db.no_tenant() as conn:
        assert (await conn.execute(COUNT)).scalar_one() == 0
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.no_tenant() as conn:
            await conn.execute(
                text("INSERT INTO rls_probe (id, tenant_id) VALUES (:id, :t)"),
                {"id": uuid.uuid4(), "t": TENANT_A_ID},
            )
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"


async def test_the_tenant_does_not_leak_between_transactions_on_a_pooled_connection(
    tenant_db: TenantDb, rls_probe: OwnerSeeder
) -> None:
    async def one(i: int) -> None:
        tenant, note = (TENANT_A_ID, "kaefer-demo") if i % 2 == 0 else (TENANT_B_ID, "tenant-b")
        async with tenant_db.with_tenant(tenant) as conn:
            assert (await conn.execute(NOTES)).scalars().all() == [note]

    # Pool of 2, 50 transactions alternating tenants: every one reuses a connection.
    await asyncio.gather(*(one(i) for i in range(50)))
    async with tenant_db.no_tenant() as conn:
        assert (await conn.execute(COUNT)).scalar_one() == 0


async def test_guard_fails_a_tenant_data_assertion_made_as_owner_or_superuser(
    tenant_db: TenantDb, rls_probe: OwnerSeeder
) -> None:
    for url in (tenant_db.db.owner_url, tenant_db.db.superuser_url):
        # A bare engine: create_app_engine itself refuses these roles at connect time.
        engine = create_async_engine(make_url(url).set(drivername="postgresql+asyncpg"))
        try:
            async with engine.begin() as conn:
                with pytest.raises(PrivilegedConnectionError):
                    await assert_unprivileged_role(conn)
        finally:
            await engine.dispose()
        with pytest.raises(PrivilegedConnectionError):
            assert_unprivileged_url(url)
