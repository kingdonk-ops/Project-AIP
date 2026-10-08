"""login_directory against real Postgres (IDENTITY-01 step 4). Never mocks the database.

Postgres comes from the DATABASE-08 fixtures (``AIP_TEST_DATABASE_URL``, else Testcontainers).
``aip_app`` belongs to DATABASE-02; until that lands this test creates the role (NOLOGIN) if it is
missing, before migrating, and checks privileges with ``SET ROLE aip_app``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from typing import Any

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import pytest
from tests.platform.db.conftest import (  # noqa: F401 - re-exported pytest fixtures
    FreshDb,
    empty_db,  # pyright: ignore[reportUnusedImport]
    execute,
    fetch,
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
)

from aip.modules.identity.repository import SqlLoginDirectory
from aip.modules.identity.seeds import TENANT_A_ID, TENANT_B_ID, SeedRefusedError, seed


@pytest.fixture(scope="module")
def aip_app_role(pg_superuser_url: str) -> Iterator[None]:  # noqa: F811
    created = not fetch(pg_superuser_url, "SELECT 1 FROM pg_roles WHERE rolname = 'aip_app'")
    if created:
        execute(pg_superuser_url, "CREATE ROLE aip_app NOLOGIN NOSUPERUSER NOBYPASSRLS")
    yield
    if created:
        with contextlib.suppress(asyncpg.PostgresError):
            execute(pg_superuser_url, "DROP ROLE IF EXISTS aip_app")


@pytest.fixture
def directory_db(empty_db: FreshDb, aip_app_role: None) -> FreshDb:  # noqa: F811
    empty_db.bootstrap()
    result = empty_db.aip_db("migrate")
    assert result.returncode == 0, result.stderr
    asyncio.run(seed(empty_db.owner_url, env="test"))
    return empty_db


async def _as_app(url: str, sql: str) -> list[tuple[Any, ...]]:
    conn: Any = await asyncpg.connect(url)  # pyright: ignore[reportUnknownMemberType]
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE aip_app")
            return [tuple(r) for r in await conn.fetch(sql)]
    finally:
        await conn.close()


def test_aip_app_cannot_read_the_table(directory_db: FreshDb) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        asyncio.run(_as_app(directory_db.superuser_url, "SELECT * FROM login_directory"))


def test_aip_app_resolves_through_the_function(directory_db: FreshDb) -> None:
    rows = asyncio.run(
        _as_app(
            directory_db.superuser_url,
            "SELECT * FROM identity_resolve_login('email_domain', 'kaefer.test')",
        )
    )
    assert rows == [(TENANT_A_ID, "kaefer-oidc")]
    rows = asyncio.run(
        _as_app(
            directory_db.superuser_url,
            "SELECT * FROM identity_resolve_login('email_domain', 'KAEFER.TEST')",
        )
    )
    assert rows == [(TENANT_A_ID, "kaefer-oidc")]


def test_function_is_security_definer_with_fixed_search_path(directory_db: FreshDb) -> None:
    rows = directory_db.fetch(
        "SELECT p.prosecdef, pg_get_userbyid(p.proowner), p.proconfig, "
        "has_function_privilege('public', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.proname = 'identity_resolve_login'"
    )
    assert rows == [(True, "aip_owner", ["search_path=pg_catalog, public"], False)]
    owner = directory_db.fetch("SELECT tableowner FROM pg_tables WHERE tablename = 'login_directory'")
    assert owner == [("aip_owner",)]


def test_repository_and_seeds(directory_db: FreshDb) -> None:
    async def run() -> None:
        directory = SqlLoginDirectory.from_url(directory_db.owner_url)
        try:
            acme = await directory.resolve("email_domain", "acme.test")
            assert acme is not None and acme.tenant_id == TENANT_B_ID and acme.idp_alias == "acme-oidc"
            slug = await directory.resolve("tenant_slug", "kaefer-demo")
            assert slug is not None and slug.tenant_id == TENANT_A_ID
            assert await directory.resolve("email_domain", "unknown.test") is None
        finally:
            await directory.dispose()
        assert await seed(directory_db.owner_url, env="test") == 4  # idempotent
        with pytest.raises(SeedRefusedError):
            await seed(directory_db.owner_url, env="production")

    asyncio.run(run())
    assert directory_db.fetch("SELECT count(*) FROM login_directory") == [(4,)]


def test_kind_is_checked(directory_db: FreshDb) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        execute(
            directory_db.superuser_url,
            "INSERT INTO login_directory (kind, key, tenant_id) "
            "VALUES ('nope', 'x.test', gen_random_uuid())",
        )
