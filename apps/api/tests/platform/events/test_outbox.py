"""ARCH-05: the ``domain_events`` outbox and ``emit``.

Unit tests use a fake connection. Integration tests run on real Postgres (migrations applied as
``aip_owner``) and connect as ``aip_app`` or ``aip_jobs``; row counts that must see every tenant
are read as the test superuser.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aip.platform.context import ContextMissingError, RequestContext, use_context
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.session import with_tenant
from aip.platform.db.templates import render_template
from aip.platform.events import Aggregate, EventValidationError, emit
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import APP, JOBS, READONLY, FreshDb, OwnerSeeder

from .fixtures import SCHEMAS

WIDGET_ID = UUID("00000000-0000-4000-8000-00000000d00d")


def ctx(tenant: UUID = TENANT_A_ID, actor: UUID | None = ALICE_ID) -> RequestContext:
    return RequestContext(tenant_id=tenant, request_id=f"test-{uuid.uuid4().hex}", actor_id=actor)


def sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


# --- unit -------------------------------------------------------------------------------------


class FakeConn:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def execute(self, statement: Any, *args: Any) -> None:
        self.calls.append(statement)


def as_conn(fake: FakeConn) -> AsyncConnection:
    return cast("AsyncConnection", fake)


async def test_an_invalid_payload_is_rejected_before_any_sql() -> None:
    conn = FakeConn()
    with use_context(ctx()), pytest.raises(EventValidationError) as caught:
        await emit(
            as_conn(conn),
            "widget.created",
            1,
            Aggregate("widget", WIDGET_ID),
            {"name": 5},
            schemas=SCHEMAS,
        )
    assert set(caught.value.fields) == {"widget_id", "name"}
    assert "widget_id" in str(caught.value) and "name" in str(caught.value)
    assert conn.calls == []


async def test_an_unknown_event_is_rejected_before_any_sql() -> None:
    conn = FakeConn()
    with use_context(ctx()), pytest.raises(EventValidationError, match="no payload model"):
        await emit(
            as_conn(conn), "widget.created", 2, Aggregate("widget", WIDGET_ID), {}, schemas=SCHEMAS
        )
    assert conn.calls == []


async def test_tenant_and_actor_come_from_the_request_context() -> None:
    conn = FakeConn()
    payload = {"widget_id": str(WIDGET_ID), "name": "w1"}
    with use_context(ctx(TENANT_A_ID, ALICE_ID)):
        event_id = await emit(
            as_conn(conn),
            "widget.created",
            1,
            Aggregate("widget", WIDGET_ID),
            payload,
            schemas=SCHEMAS,
        )
    (statement,) = conn.calls
    params = statement.compile().params
    assert params["id"] == event_id and event_id.version == 7
    assert params["tenant_id"] == TENANT_A_ID
    assert params["actor_id"] == ALICE_ID
    assert params["project_id"] is None
    assert (params["aggregate_type"], params["aggregate_id"]) == ("widget", WIDGET_ID)
    assert (params["event_name"], params["event_version"]) == ("widget.created", 1)
    assert params["payload"] == payload


async def test_emit_outside_a_request_context_fails() -> None:
    conn = FakeConn()
    payload = {"widget_id": str(WIDGET_ID), "name": "w1"}
    with pytest.raises(ContextMissingError):
        await emit(
            as_conn(conn),
            "widget.created",
            1,
            Aggregate("widget", WIDGET_ID),
            payload,
            schemas=SCHEMAS,
        )
    assert conn.calls == []


# --- integration ------------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def role_engine(db: FreshDb, role: str) -> AsyncIterator[AsyncEngine]:
    engine = create_app_engine(EngineSettings(url=db.role_url(role)))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def app_engine(migrated_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    async with role_engine(migrated_db, APP) as engine:
        yield engine


@pytest.fixture
async def jobs_engine(migrated_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    async with role_engine(migrated_db, JOBS) as engine:
        yield engine


async def emit_widget(conn: AsyncConnection, widget_id: UUID, name: str = "w1") -> UUID:
    return await emit(
        conn,
        "widget.created",
        1,
        Aggregate("widget", widget_id),
        {"widget_id": str(widget_id), "name": name},
        schemas=SCHEMAS,
    )


async def seed_events(engine: AsyncEngine, tenant: UUID, actor: UUID, count: int) -> None:
    c = ctx(tenant, actor)
    async with use_context(c), with_tenant(c, engine=engine) as conn:
        for _ in range(count):
            await emit_widget(conn, uuid.uuid4())


async def superuser_fetch(db: FreshDb, sql: str) -> list[tuple[Any, ...]]:
    """Read as the test superuser (sees every tenant). The helper runs its own event loop."""
    return await asyncio.to_thread(db.fetch, sql)


async def all_events(db: FreshDb) -> int:
    return int((await superuser_fetch(db, "SELECT count(*) FROM domain_events"))[0][0])


async def test_rolling_back_the_business_transaction_leaves_no_event(
    migrated_db: FreshDb, owner_conn_for_seeding_only: OwnerSeeder, app_engine: AsyncEngine
) -> None:
    await asyncio.to_thread(
        owner_conn_for_seeding_only.ddl,
        render_template("tenant_table", table="widgets", columns="name text NOT NULL"),
    )

    class RollbackError(Exception):
        pass

    c = ctx()
    with pytest.raises(RollbackError):
        async with use_context(c), with_tenant(c, engine=app_engine) as conn:
            await conn.execute(
                text("INSERT INTO widgets (id, tenant_id, name) VALUES (:id, :t, 'w1')"),
                {"id": WIDGET_ID, "t": TENANT_A_ID},
            )
            await emit_widget(conn, WIDGET_ID)
            raise RollbackError
    assert await all_events(migrated_db) == 0
    assert await superuser_fetch(migrated_db, "SELECT count(*) FROM widgets") == [(0,)]


async def test_a_committed_event_records_tenant_actor_and_aggregate(
    migrated_db: FreshDb, app_engine: AsyncEngine
) -> None:
    c = ctx(TENANT_A_ID, ALICE_ID)
    async with use_context(c), with_tenant(c, engine=app_engine) as conn:
        event_id = await emit_widget(conn, WIDGET_ID)
    rows = await superuser_fetch(
        migrated_db,
        "SELECT id, tenant_id, actor_id, aggregate_type, aggregate_id, payload->>'name',"
        " published_at, attempts FROM domain_events",
    )
    assert rows == [(event_id, TENANT_A_ID, ALICE_ID, "widget", WIDGET_ID, "w1", None, 0)]


async def test_aip_app_cannot_rewrite_or_delete_events(app_engine: AsyncEngine) -> None:
    await seed_events(app_engine, TENANT_A_ID, ALICE_ID, 1)
    for statement in (
        "UPDATE domain_events SET payload = '{}'",
        "UPDATE domain_events SET published_at = now()",
        "DELETE FROM domain_events",
    ):
        with pytest.raises(DBAPIError) as caught:
            async with with_tenant(TENANT_A_ID, engine=app_engine) as conn:
                await conn.execute(text(statement))
        assert sqlstate(caught.value) == "42501", statement


async def test_aip_jobs_may_update_only_the_publish_columns(
    migrated_db: FreshDb, app_engine: AsyncEngine, jobs_engine: AsyncEngine
) -> None:
    await seed_events(app_engine, TENANT_A_ID, ALICE_ID, 1)
    await seed_events(app_engine, TENANT_B_ID, BOB_ID, 1)
    for statement in (
        "UPDATE domain_events SET payload = '{}'",
        "UPDATE domain_events SET tenant_id = gen_random_uuid()",
        "DELETE FROM domain_events",
        "INSERT INTO domain_events (id, tenant_id, event_name, event_version, aggregate_type,"
        " aggregate_id, payload) VALUES (gen_random_uuid(), gen_random_uuid(), 'x', 1, 'x',"
        " gen_random_uuid(), '{}')",
    ):
        with pytest.raises(DBAPIError) as caught:
            async with jobs_engine.begin() as conn:
                await conn.execute(text(statement))
        assert sqlstate(caught.value) == "42501", statement

    # The dispatcher works across tenants, with no tenant set.
    async with jobs_engine.begin() as conn:
        result = await conn.execute(
            text(
                "UPDATE domain_events SET published_at = now(), attempts = attempts + 1,"
                " last_error = NULL, dead_lettered_at = NULL"
            )
        )
        assert result.rowcount == 2
    published = "SELECT count(*) FROM domain_events WHERE published_at IS NOT NULL AND attempts = 1"
    assert await superuser_fetch(migrated_db, published) == [(2,)]


async def test_a_tenant_sees_only_its_own_events(app_engine: AsyncEngine) -> None:
    await seed_events(app_engine, TENANT_A_ID, ALICE_ID, 3)
    await seed_events(app_engine, TENANT_B_ID, BOB_ID, 2)
    async with with_tenant(TENANT_A_ID, engine=app_engine) as conn:
        assert (await conn.execute(text("SELECT count(*) FROM domain_events"))).scalar() == 3
    async with with_tenant(TENANT_B_ID, engine=app_engine) as conn:
        assert (await conn.execute(text("SELECT count(*) FROM domain_events"))).scalar() == 2


async def test_with_no_tenant_set_reads_see_nothing_and_writes_fail(
    app_engine: AsyncEngine,
) -> None:
    await seed_events(app_engine, TENANT_A_ID, ALICE_ID, 1)
    async with app_engine.begin() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM domain_events"))).scalar() == 0

    # The context names tenant A but the connection has no app.tenant_id: WITH CHECK refuses.
    with pytest.raises(DBAPIError) as caught:
        async with use_context(ctx()), app_engine.begin() as conn:
            await emit_widget(conn, WIDGET_ID)
    assert sqlstate(caught.value) == "42501"


async def test_an_event_written_for_another_tenant_is_refused(app_engine: AsyncEngine) -> None:
    # The context says tenant B while the connection is bound to tenant A.
    with pytest.raises(DBAPIError) as caught:
        async with (
            use_context(ctx(TENANT_B_ID, BOB_ID)),
            with_tenant(TENANT_A_ID, engine=app_engine) as conn,
        ):
            await emit_widget(conn, WIDGET_ID)
    assert sqlstate(caught.value) == "42501"


async def test_aip_readonly_reads_only_the_bound_tenant(
    migrated_db: FreshDb, app_engine: AsyncEngine
) -> None:
    await seed_events(app_engine, TENANT_A_ID, ALICE_ID, 3)
    await seed_events(app_engine, TENANT_B_ID, BOB_ID, 2)
    async with role_engine(migrated_db, READONLY) as readonly:
        async with with_tenant(TENANT_A_ID, engine=readonly) as conn:
            assert (await conn.execute(text("SELECT count(*) FROM domain_events"))).scalar() == 3
        async with readonly.begin() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM domain_events"))).scalar() == 0
        with pytest.raises(DBAPIError) as caught:
            async with use_context(ctx()), with_tenant(TENANT_A_ID, engine=readonly) as conn:
                await emit_widget(conn, WIDGET_ID)
        # aip_readonly sessions are read-only (25006) before privileges are even checked.
        assert sqlstate(caught.value) == "25006"
