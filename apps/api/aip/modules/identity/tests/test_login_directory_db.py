"""login_directory against real Postgres (IDENTITY-01 step 4). Never mocks the database.

Postgres comes from the DATABASE-08/02 fixtures (``AIP_TEST_DATABASE_URL``, else Testcontainers);
the cluster bootstrap creates ``aip_app`` (ADR 0012) and the tests log in as it.
"""

from __future__ import annotations

import asyncio
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
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.session import before_tenant


@pytest.fixture
def directory_db(empty_db: FreshDb) -> FreshDb:  # noqa: F811
    empty_db.migrate()
    asyncio.run(seed(empty_db.owner_url, env="test"))
    return empty_db


def test_aip_app_cannot_read_the_table(directory_db: FreshDb) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        fetch(directory_db.app_url, "SELECT * FROM login_directory")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        execute(
            directory_db.app_url,
            "INSERT INTO login_directory (kind, key, tenant_id) "
            "VALUES ('email_domain', 'evil.test', gen_random_uuid())",
        )


def test_aip_app_resolves_through_the_function(directory_db: FreshDb) -> None:
    sql = "SELECT * FROM identity_resolve_login($1, $2)"
    assert fetch(directory_db.app_url, sql, "email_domain", "kaefer.test") == [
        (TENANT_A_ID, "kaefer-oidc")
    ]
    assert fetch(directory_db.app_url, sql, "email_domain", "KAEFER.TEST") == [
        (TENANT_A_ID, "kaefer-oidc")
    ]
    assert fetch(directory_db.app_url, sql, "email_domain", "unknown.test") == []


def test_function_is_security_definer_with_fixed_search_path(directory_db: FreshDb) -> None:
    rows = directory_db.fetch(
        "SELECT p.prosecdef, pg_get_userbyid(p.proowner), p.proconfig, "
        "has_function_privilege('public', p.oid, 'EXECUTE'), "
        "has_function_privilege('aip_readonly', p.oid, 'EXECUTE') "
        "FROM pg_proc p WHERE p.proname = 'identity_resolve_login'"
    )
    assert rows == [(True, "aip_owner", ["search_path=pg_catalog, public"], False, False)]
    owner = directory_db.fetch("SELECT tableowner FROM pg_tables WHERE tablename = 'login_directory'")
    assert owner == [("aip_owner",)]


def test_repository_as_aip_app_and_idempotent_seeds(directory_db: FreshDb) -> None:
    async def run() -> None:
        engine = create_app_engine(EngineSettings(url=directory_db.app_url, pool_size=1))
        try:
            directory = SqlLoginDirectory(lambda: before_tenant(engine=engine))
            acme = await directory.resolve("email_domain", "acme.test")
            assert acme is not None
            assert (acme.tenant_id, acme.idp_alias) == (TENANT_B_ID, "acme-oidc")
            slug = await directory.resolve("tenant_slug", "kaefer-demo")
            assert slug is not None and slug.tenant_id == TENANT_A_ID
            assert await directory.resolve("email_domain", "unknown.test") is None
        finally:
            await engine.dispose()
        assert await seed(directory_db.owner_url, env="test") == 4
        with pytest.raises(SeedRefusedError):
            await seed(directory_db.owner_url, env="production")

    asyncio.run(run())
    assert directory_db.fetch("SELECT count(*) FROM login_directory") == [(4,)]


def test_kind_is_checked(directory_db: FreshDb) -> None:
    sql: Any = (
        "INSERT INTO login_directory (kind, key, tenant_id) VALUES ('nope', 'x.test', gen_random_uuid())"
    )
    with pytest.raises(asyncpg.CheckViolationError):
        execute(directory_db.owner_url, sql)
