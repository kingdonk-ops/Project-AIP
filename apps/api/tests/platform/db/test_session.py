"""DATABASE-02: runtime roles, ``with_tenant`` and fail-closed row-level security.

Integration tests run against real Postgres 16 (see ``conftest.py``). ``rls_probe`` is created
from ``db/templates/tenant_table.sql.tpl`` as ``aip_owner`` and seeded with one row for tenant A
(``kaefer-demo``) and one for tenant B (``tenant-b``), the shared fixtures from AGENTS.md.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.platform.db.conftest import APP, JOBS, OWNER, READONLY, execute

from aip.main import create_app
from aip.platform.context import RequestContext, get_context
from aip.platform.db.engine import EngineSettings, PoolMode, connect_args, create_app_engine
from aip.platform.db.errors import DatabaseConfigError, InvalidTenantError
from aip.platform.db.session import tenant_uuid, with_tenant
from aip.platform.db.templates import render_template

if TYPE_CHECKING:  # fixtures come from conftest.py; this import is for type hints only
    from tests.conftest import FixtureMembershipResolver, FixturePrincipalResolver
    from tests.platform.db.conftest import FreshDb

AIP_DIR = Path(__file__).resolve().parents[3] / "aip"

ROW_A = UUID("00000000-0000-4000-8000-0000000000aa")
ROW_B = UUID("00000000-0000-4000-8000-0000000000bb")
COUNT = text("SELECT count(*) FROM rls_probe")
TENANTS = text("SELECT tenant_id FROM rls_probe ORDER BY tenant_id")


def sqlstate(exc: BaseException) -> str | None:
    """The SQLSTATE of an asyncpg error, raw or wrapped by SQLAlchemy."""
    orig = exc.orig if isinstance(exc, DBAPIError) else exc
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


# --- unit --------------------------------------------------------------------------------------


class NoCheckoutEngine:
    """An engine stand-in that fails the test if anything asks it for a connection."""

    def begin(self) -> Any:
        raise AssertionError("with_tenant took a connection before validating the tenant")

    def connect(self) -> Any:
        raise AssertionError("with_tenant took a connection before validating the tenant")


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-uuid",
        "",
        " ",
        None,
        42,
        b"\x00" * 16,
        "00000000-0000-0000-0000-000000000000",
        UUID(int=0),
    ],
)
async def test_with_tenant_rejects_a_bad_tenant_before_any_checkout(bad: object) -> None:
    engine = cast(AsyncEngine, NoCheckoutEngine())
    with pytest.raises(InvalidTenantError):
        async with with_tenant(cast(Any, bad), engine=engine):
            pytest.fail("the block must not run")


def test_tenant_uuid_accepts_a_uuid_a_string_or_a_request_context() -> None:
    assert tenant_uuid(TENANT_A_ID) == TENANT_A_ID
    assert tenant_uuid(str(TENANT_B_ID)) == TENANT_B_ID
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id="r-1")
    assert tenant_uuid(ctx) == TENANT_A_ID


_SESSION_SET = re.compile(r"\bSET\s+(?:SESSION\s+|LOCAL\s+)?app\.tenant_id\b", re.IGNORECASE)
_SET_CONFIG_FALSE = re.compile(r"set_config\s*\([^)]*,\s*false\s*\)", re.IGNORECASE)


def test_no_session_level_tenant_setting_anywhere_in_aip() -> None:
    """The tenant is set only by with_tenant's set_config(..., true) (ADR 0002)."""
    offenders: list[str] = []
    for path in sorted(AIP_DIR.rglob("*")):
        if path.suffix not in {".py", ".sql", ".tpl"} or "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _SESSION_SET.search(line) or _SET_CONFIG_FALSE.search(line):
                offenders.append(f"{path.relative_to(AIP_DIR.parent)}:{lineno}: {line.strip()}")
    assert offenders == []


def test_the_ban_patterns_catch_what_they_should() -> None:
    assert _SESSION_SET.search("SET app.tenant_id = 'x'")
    assert _SESSION_SET.search("set session app.tenant_id to 'x'")
    assert _SET_CONFIG_FALSE.search("select set_config('app.tenant_id', :t, false)")
    assert not _SET_CONFIG_FALSE.search("select set_config('app.tenant_id', :t, true)")


def test_engine_settings_from_env() -> None:
    with pytest.raises(DatabaseConfigError, match="DATABASE_URL is not set"):
        EngineSettings.from_env({})
    with pytest.raises(DatabaseConfigError, match="DB_POOL_MODE"):
        EngineSettings.from_env({"DATABASE_URL": "postgresql://x@h/d", "DB_POOL_MODE": "rds"})
    with pytest.raises(DatabaseConfigError, match="DB_POOL_SIZE"):
        EngineSettings.from_env({"DATABASE_URL": "postgresql://x@h/d", "DB_POOL_SIZE": "0"})
    settings = EngineSettings.from_env(
        {"DATABASE_URL": "postgresql://x@h/d", "DB_POOL_MODE": "PgBouncer", "DB_POOL_SIZE": "3"}
    )
    assert settings.pool_mode is PoolMode.PGBOUNCER
    assert settings.pool_size == 3
    assert settings.max_overflow == 0


def test_pgbouncer_mode_disables_statement_caches() -> None:
    args = connect_args(PoolMode.PGBOUNCER)
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_cache_size"] == 0
    names = {args["prepared_statement_name_func"]() for _ in range(3)}
    assert len(names) == 3
    assert connect_args(PoolMode.DIRECT) == {}


def test_engine_rejects_a_non_postgres_url() -> None:
    with pytest.raises(DatabaseConfigError):
        create_app_engine(EngineSettings(url="sqlite:///x.db"))


# --- integration (real Postgres 16) ------------------------------------------------------------


def _seed_sql(tenant: UUID, row: UUID, note: str) -> str:
    return (
        "BEGIN;\n"
        f"SELECT set_config('app.tenant_id', '{tenant}', true);\n"
        f"INSERT INTO rls_probe (id, tenant_id, note) VALUES ('{row}', '{tenant}', '{note}');\n"
        "COMMIT;\n"
    )


@pytest.fixture
def rls_db(empty_db: FreshDb) -> Iterator[FreshDb]:
    """A migrated database with ``rls_probe`` (from the template) and one row per tenant."""
    empty_db.migrate()
    execute(
        empty_db.owner_url, render_template("tenant_table", table="rls_probe", columns="note text")
    )
    # FORCE ROW LEVEL SECURITY binds the owner too, so even seeding needs the tenant set.
    execute(empty_db.owner_url, _seed_sql(TENANT_A_ID, ROW_A, "kaefer-demo"))
    execute(empty_db.owner_url, _seed_sql(TENANT_B_ID, ROW_B, "tenant-b"))
    yield empty_db


@pytest.fixture
async def app_engine(rls_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    engine = create_app_engine(EngineSettings(url=rls_db.app_url))
    try:
        yield engine
    finally:
        await engine.dispose()


async def _connect(url: str) -> Any:
    return await asyncpg.connect(url)  # pyright: ignore[reportUnknownMemberType]


async def test_app_role_without_a_tenant_sees_zero_rows(rls_db: FreshDb) -> None:
    conn = await _connect(rls_db.app_url)
    try:
        assert await conn.fetchval("SELECT current_setting('app.tenant_id', true)") is None
        assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 0
        # An empty setting (what a finished set_config(..., true) leaves behind) is the same.
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', '', true)")
            assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 0
        assert await conn.execute("UPDATE rls_probe SET note = 'x'") == "UPDATE 0"
        assert await conn.execute("DELETE FROM rls_probe") == "DELETE 0"
    finally:
        await conn.close()
    # The rows are there: a superuser (which bypasses RLS) sees both.
    su = await _connect(rls_db.superuser_url)
    try:
        assert await su.fetchval("SELECT count(*) FROM rls_probe") == 2
    finally:
        await su.close()


async def test_app_role_without_a_tenant_cannot_insert(rls_db: FreshDb) -> None:
    conn = await _connect(rls_db.app_url)
    try:
        with pytest.raises(asyncpg.PostgresError) as caught:
            await conn.execute(
                "INSERT INTO rls_probe (id, tenant_id) VALUES ($1, $2)", uuid.uuid4(), TENANT_A_ID
            )
        assert sqlstate(caught.value) == "42501"
    finally:
        await conn.close()


async def test_each_tenant_sees_and_writes_only_its_own_rows(app_engine: AsyncEngine) -> None:
    async with with_tenant(TENANT_A_ID, engine=app_engine) as conn:
        assert (await conn.execute(TENANTS)).scalars().all() == [TENANT_A_ID]
        # Tenant A cannot touch tenant B's row ...
        result = await conn.execute(
            text("UPDATE rls_probe SET note = 'hijacked' WHERE id = :id"), {"id": ROW_B}
        )
        assert result.rowcount == 0
    async with with_tenant(str(TENANT_B_ID), engine=app_engine) as conn:
        rows = (await conn.execute(text("SELECT id, note FROM rls_probe"))).all()
        assert [tuple(r) for r in rows] == [(ROW_B, "tenant-b")]

    # ... cannot write a row for tenant B ...
    with pytest.raises(DBAPIError) as caught:
        async with with_tenant(TENANT_A_ID, engine=app_engine) as conn:
            await conn.execute(
                text("INSERT INTO rls_probe (id, tenant_id) VALUES (:id, :t)"),
                {"id": uuid.uuid4(), "t": TENANT_B_ID},
            )
    assert sqlstate(caught.value) == "42501"

    # ... and cannot move its own row to tenant B.
    with pytest.raises(DBAPIError) as caught:
        async with with_tenant(TENANT_A_ID, engine=app_engine) as conn:
            await conn.execute(
                text("UPDATE rls_probe SET tenant_id = :t WHERE id = :id"),
                {"t": TENANT_B_ID, "id": ROW_A},
            )
    assert sqlstate(caught.value) == "42501"

    # A tenant inserts its own rows normally.
    async with with_tenant(TENANT_A_ID, engine=app_engine) as conn:
        await conn.execute(
            text("INSERT INTO rls_probe (id, tenant_id) VALUES (:id, :t)"),
            {"id": uuid.uuid4(), "t": TENANT_A_ID},
        )
        assert (await conn.execute(COUNT)).scalar_one() == 2
    async with with_tenant(TENANT_B_ID, engine=app_engine) as conn:
        assert (await conn.execute(COUNT)).scalar_one() == 1


async def test_tenant_does_not_leak_between_transactions_on_one_connection(rls_db: FreshDb) -> None:
    engine = create_app_engine(EngineSettings(url=rls_db.app_url, pool_size=1, max_overflow=0))
    pid = text("SELECT pg_backend_pid()")
    try:
        async with with_tenant(TENANT_A_ID, engine=engine) as conn:
            pid_a = (await conn.execute(pid)).scalar_one()
            assert (await conn.execute(TENANTS)).scalars().all() == [TENANT_A_ID]
        async with with_tenant(TENANT_B_ID, engine=engine) as conn:
            assert (await conn.execute(pid)).scalar_one() == pid_a  # same physical connection
            assert (await conn.execute(TENANTS)).scalars().all() == [TENANT_B_ID]
        async with engine.connect() as conn:
            assert (await conn.execute(pid)).scalar_one() == pid_a
            setting = text("SELECT current_setting('app.tenant_id', true)")
            assert (await conn.execute(setting)).scalar_one() in ("", None)
            assert (await conn.execute(COUNT)).scalar_one() == 0
    finally:
        await engine.dispose()


async def test_error_inside_with_tenant_rolls_back_and_leaves_no_tenant(rls_db: FreshDb) -> None:
    engine = create_app_engine(EngineSettings(url=rls_db.app_url, pool_size=1, max_overflow=0))
    new_row = uuid.uuid4()
    try:
        with pytest.raises(RuntimeError, match="boom"):
            async with with_tenant(TENANT_A_ID, engine=engine) as conn:
                await conn.execute(
                    text("INSERT INTO rls_probe (id, tenant_id) VALUES (:id, :t)"),
                    {"id": new_row, "t": TENANT_A_ID},
                )
                raise RuntimeError("boom")
        async with with_tenant(TENANT_A_ID, engine=engine) as conn:
            found = text("SELECT count(*) FROM rls_probe WHERE id = :id")
            assert (await conn.execute(found, {"id": new_row})).scalar_one() == 0
        async with engine.connect() as conn:
            assert (await conn.execute(COUNT)).scalar_one() == 0
    finally:
        await engine.dispose()


async def test_commit_inside_the_block_cannot_continue_without_the_tenant(
    app_engine: AsyncEngine,
) -> None:
    with pytest.raises(InvalidRequestError):
        async with with_tenant(TENANT_A_ID, engine=app_engine) as conn:
            assert (await conn.execute(COUNT)).scalar_one() == 1
            await conn.commit()  # ends the transaction, and with it app.tenant_id
            await conn.execute(COUNT)
    # Outside with_tenant the same role still sees nothing.
    async with app_engine.connect() as conn:
        assert (await conn.execute(COUNT)).scalar_one() == 0


def test_runtime_roles_are_unprivileged_and_own_nothing(rls_db: FreshDb) -> None:
    rows = rls_db.fetch(
        "SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
        "FROM pg_roles WHERE rolname = ANY($1) ORDER BY rolname",
        [OWNER, APP, JOBS, READONLY],
    )
    assert rows == [
        (APP, True, False, False, False, False),
        (JOBS, True, False, False, False, False),
        (OWNER, True, False, False, False, False),
        (READONLY, True, False, False, False, False),
    ]
    assert rls_db.fetch("SELECT count(*) FROM pg_tables WHERE tableowner = $1", APP) == [(0,)]
    owned = rls_db.fetch(
        "SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner "
        "WHERE r.rolname = ANY($1)",
        [APP, JOBS, READONLY],
    )
    assert owned == [(0,)]
    table = rls_db.fetch(
        "SELECT r.rolname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_roles r ON r.oid = c.relowner WHERE c.oid = 'public.rls_probe'::regclass"
    )
    assert table == [(OWNER, True, True)]
    members = rls_db.fetch(
        "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member "
        "WHERE r.rolname = ANY($1)",
        [APP, JOBS, READONLY],
    )
    assert members == [(0,)]


async def test_readonly_role_reads_its_tenant_only_and_cannot_write(rls_db: FreshDb) -> None:
    conn = await _connect(rls_db.role_url(READONLY))
    try:
        assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 0
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(TENANT_B_ID))
            assert await conn.fetchval("SELECT note FROM rls_probe") == "tenant-b"
            assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 1
        with pytest.raises(asyncpg.PostgresError):
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(TENANT_B_ID))
                await conn.execute(
                    "INSERT INTO rls_probe (id, tenant_id) VALUES ($1, $2)",
                    uuid.uuid4(),
                    TENANT_B_ID,
                )
    finally:
        await conn.close()


async def test_only_aip_roles_may_connect(rls_db: FreshDb) -> None:
    probe = f"probe_{rls_db.name[-12:]}"
    su = await _connect(rls_db.superuser_url)
    await su.execute(f"CREATE ROLE {probe} LOGIN PASSWORD 'probe_test_only'")
    try:
        url = rls_db.app_url.replace(f"{APP}:", f"{probe}:", 1).replace(
            ":aip_app_test_only@", ":probe_test_only@", 1
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await _connect(url)
    finally:
        await su.execute(f"DROP ROLE {probe}")
        await su.close()


@pytest.mark.parametrize("who", ["superuser", "owner"])
async def test_engine_refuses_a_login_that_escapes_rls(rls_db: FreshDb, who: str) -> None:
    url = rls_db.superuser_url if who == "superuser" else rls_db.owner_url
    engine = create_app_engine(EngineSettings(url=url))
    try:
        with pytest.raises(DatabaseConfigError, match="refusing to use role"):
            async with with_tenant(TENANT_A_ID, engine=engine):
                pytest.fail("the block must not run")
    finally:
        await engine.dispose()


async def test_app_role_can_read_the_applied_revision_for_readiness(rls_db: FreshDb) -> None:
    conn = await _connect(rls_db.app_url)
    try:
        assert await conn.fetchval("SELECT count(*) FROM aip_meta.alembic_version") == 1
    finally:
        await conn.close()


# --- e2e (FastAPI app, fixture route using with_tenant) ----------------------------------------


async def test_route_without_a_tenant_principal_gets_401_and_never_checks_out(
    app_engine: AsyncEngine,
    principal_resolver: FixturePrincipalResolver,
    membership_resolver: FixtureMembershipResolver,
) -> None:
    checkouts: list[object] = []
    event.listen(app_engine.sync_engine, "checkout", lambda *args: checkouts.append(args))

    app = create_app(
        principal_resolver=principal_resolver,
        membership_resolver=membership_resolver,
        env="test",
        tracing=False,
    )

    @app.get("/api/v1/_fixture/rls-probe")
    async def rls_probe() -> dict[str, list[str]]:  # pyright: ignore[reportUnusedFunction]
        async with with_tenant(get_context(), engine=app_engine) as conn:
            tenants = (await conn.execute(TENANTS)).scalars().all()
        return {"tenants": [str(t) for t in tenants]}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        anonymous = await client.get("/api/v1/_fixture/rls-probe")
        assert anonymous.status_code == 401
        forged = await client.get(
            "/api/v1/_fixture/rls-probe", headers={"Authorization": "Bearer not-a-token"}
        )
        assert forged.status_code == 401
        assert checkouts == []

        alice = await client.get(
            "/api/v1/_fixture/rls-probe", headers={"Authorization": "Bearer token-alice"}
        )
        assert alice.status_code == 200
        assert alice.json() == {"tenants": [str(TENANT_A_ID)]}
        bob = await client.get(
            "/api/v1/_fixture/rls-probe", headers={"Authorization": "Bearer token-bob"}
        )
        assert bob.json() == {"tenants": [str(TENANT_B_ID)]}
        assert len(checkouts) == 2
