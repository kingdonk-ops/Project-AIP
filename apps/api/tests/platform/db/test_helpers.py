"""DATABASE-04: optimistic concurrency, ltree, soft delete, idempotent create, JSONB validation.

Unit tests use a fake connection. Integration tests run as ``aip_app`` inside ``with_tenant``
against real Postgres 16 on ``helper_probe``, a table rendered from the tenant template with
``sync=True`` plus ``path ltree`` and ``attributes jsonb``. Tenants are the shared fixtures:
A (``kaefer-demo``) and B (``tenant-b``).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    text,
)
from sqlalchemy import Uuid as SqlUuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.platform.db.conftest import execute

from aip.main import create_app
from aip.platform.context import get_context
from aip.platform.db.concurrency import update_with_version
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.errors import (
    ConflictError,
    CycleError,
    InvalidSchemaError,
    NotFoundError,
)
from aip.platform.db.idempotency import create_idempotent
from aip.platform.db.jsonb_schema import validate_attributes
from aip.platform.db.ltree import ancestors, descendants, move_subtree
from aip.platform.db.session import with_tenant
from aip.platform.db.soft_delete import active, restore, soft_delete
from aip.platform.db.templates import render_template

if TYPE_CHECKING:
    from tests.conftest import FixtureMembershipResolver, FixturePrincipalResolver
    from tests.platform.db.conftest import FreshDb

probe = Table(
    "helper_probe",
    MetaData(),
    Column("id", SqlUuid, primary_key=True),
    Column("tenant_id", SqlUuid, nullable=False),
    Column("name", Text),
    Column("path", Text),  # ltree in the database; read back as text
    Column("attributes", JSONB),
    Column("client_generated_id", SqlUuid),
    Column("sync_version", Integer),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
    Column("deleted_at", DateTime(timezone=True)),
)


# --- unit --------------------------------------------------------------------------------------


class FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def first(self) -> dict[str, Any] | None:
        return self._row


class FakeConn:
    """Returns the queued results in order; fails the test if it is used when it must not be."""

    def __init__(self, *rows: dict[str, Any] | None) -> None:
        self.queue = list(rows)
        self.executed = 0

    async def execute(self, *args: object, **kwargs: object) -> FakeResult:
        self.executed += 1
        return FakeResult(self.queue.pop(0))


async def test_update_with_version_raises_conflict_with_the_current_row() -> None:
    row_id = uuid.uuid4()
    stored = {"id": row_id, "name": "x", "sync_version": 4, "deleted_at": None}
    conn = FakeConn(None, stored)  # the UPDATE matches nothing, then the re-select finds the row
    with pytest.raises(ConflictError) as caught:
        await update_with_version(conn, probe, row_id, 3, {"name": "y"})  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert caught.value.current["sync_version"] == 4
    assert conn.executed == 2


async def test_update_with_version_raises_not_found_for_a_missing_or_deleted_row() -> None:
    row_id = uuid.uuid4()
    for second in (None, {"id": row_id, "sync_version": 1, "deleted_at": "2026-01-01"}):
        conn = FakeConn(None, second)
        with pytest.raises(NotFoundError):
            await update_with_version(conn, probe, row_id, 1, {"name": "y"})  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("patch", [{"sync_version": 9}, {"tenant_id": uuid.uuid4()}, {"nope": 1}])
async def test_update_with_version_refuses_protected_and_unknown_columns(
    patch: dict[str, Any],
) -> None:
    conn = FakeConn()
    with pytest.raises(ValueError, match="cannot patch"):
        await update_with_version(conn, probe, uuid.uuid4(), 1, patch)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert conn.executed == 0


@pytest.mark.parametrize("target", ["a.b", "a.b.c", "a.b.c.d"])
async def test_move_subtree_rejects_a_cycle_without_running_sql(target: str) -> None:
    conn = FakeConn()
    with pytest.raises(CycleError):
        await move_subtree(conn, "helper_probe", "a.b", target)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert conn.executed == 0


@pytest.mark.parametrize("bad", ["", "a..b", "a.b;drop", "a b", "a.b."])
async def test_ltree_helpers_reject_malformed_paths(bad: str) -> None:
    conn = FakeConn()
    with pytest.raises(ValueError, match="ltree path"):
        await descendants(conn, "helper_probe", bad)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="ltree path"):
        await move_subtree(conn, "helper_probe", "a", bad)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="table name"):
        await descendants(conn, "helper_probe; drop table x", "a")  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert conn.executed == 0


def test_validate_attributes_reports_the_json_path_and_a_terminology_key() -> None:
    schema = {"type": "object", "properties": {"wall_loss_mm": {"type": "number"}}}
    errors = validate_attributes(schema, {"wall_loss_mm": "x"})
    assert len(errors) == 1
    assert errors[0].path == "$.wall_loss_mm"
    assert errors[0].term_key == "validation.attribute.type"
    assert errors[0].params == {"type": "number"}


def test_validate_attributes_accepts_a_valid_value() -> None:
    schema = {"type": "object", "properties": {"wall_loss_mm": {"type": "number"}}}
    assert validate_attributes(schema, {"wall_loss_mm": 1.5}) == []


def test_validate_attributes_points_at_missing_properties_and_array_items() -> None:
    schema = {
        "type": "object",
        "required": ["grade", "owner"],
        "properties": {"readings": {"type": "array", "items": {"type": "integer"}}},
    }
    errors = validate_attributes(schema, {"readings": [1, "two"]})
    assert [(e.path, e.term_key) for e in errors] == [
        ("$.grade", "validation.attribute.required"),
        ("$.owner", "validation.attribute.required"),
        ("$.readings[1]", "validation.attribute.type"),
    ]


def test_validate_attributes_rejects_an_invalid_stored_schema() -> None:
    with pytest.raises(InvalidSchemaError):
        validate_attributes({"type": "no-such-type"}, {})


# --- integration (real Postgres 16, as aip_app inside with_tenant) -----------------------------


@pytest.fixture
def helper_db(empty_db: FreshDb) -> Iterator[FreshDb]:
    empty_db.migrate()
    columns = "name text, path ltree, attributes jsonb"
    execute(
        empty_db.owner_url,
        render_template("tenant_table", table="helper_probe", columns=columns, sync=True)
        + "CREATE INDEX ix_helper_probe_path ON helper_probe USING gist (path);\n",
    )
    yield empty_db


@pytest.fixture
async def engine(helper_db: FreshDb) -> AsyncIterator[AsyncEngine]:
    app_engine = create_app_engine(EngineSettings(url=helper_db.app_url))
    try:
        yield app_engine
    finally:
        await app_engine.dispose()


_INSERT_NODE = text(
    "INSERT INTO helper_probe (id, tenant_id, name, path) "
    "VALUES (:id, :t, :name, CAST(CAST(:path AS text) AS ltree))"
)


async def seed_tree(engine: AsyncEngine, tenant: UUID, paths: list[str]) -> dict[str, UUID]:
    ids = {p: uuid.uuid4() for p in paths}
    async with with_tenant(tenant, engine=engine) as conn:
        for p, row_id in ids.items():
            await conn.execute(_INSERT_NODE, {"id": row_id, "t": tenant, "name": p, "path": p})
    return ids


async def all_paths(engine: AsyncEngine, tenant: UUID) -> list[str]:
    async with with_tenant(tenant, engine=engine) as conn:
        rows = await conn.execute(text("SELECT path::text FROM helper_probe ORDER BY path"))
        return [r[0] for r in rows]


async def new_row(engine: AsyncEngine, tenant: UUID, name: str = "r") -> UUID:
    client_id = uuid.uuid4()
    async with with_tenant(tenant, engine=engine) as conn:
        created = await create_idempotent(
            conn, probe, {"tenant_id": tenant, "name": name, "client_generated_id": client_id}
        )
    return created.row["id"]


async def test_move_subtree_moves_the_node_and_its_descendants(engine: AsyncEngine) -> None:
    await seed_tree(engine, TENANT_A_ID, ["a", "a.b", "a.b.x", "a.b.y", "a.b.y.z", "a.c", "a.d"])
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        assert len(await descendants(conn, probe, "a.b")) == 3
        moved = await move_subtree(conn, probe, "a.b", "a.c")
    assert moved == 4
    assert await all_paths(engine, TENANT_A_ID) == [
        "a",
        "a.c",
        "a.c.b",
        "a.c.b.x",
        "a.c.b.y",
        "a.c.b.y.z",
        "a.d",
    ]
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        assert len(await descendants(conn, probe, "a.c.b")) == 3
        assert await descendants(conn, probe, "a.b") == []
        assert [r["path"] for r in await ancestors(conn, probe, "a.c.b.y.z")] == [
            "a",
            "a.c",
            "a.c.b",
            "a.c.b.y",
        ]
        own = await descendants(conn, probe, "a.c.b", include_self=True)
        assert len(own) == 4


async def test_move_subtree_to_the_root(engine: AsyncEngine) -> None:
    await seed_tree(engine, TENANT_A_ID, ["a", "a.b", "a.b.x"])
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        assert await move_subtree(conn, probe, "a.b", None) == 2
    assert await all_paths(engine, TENANT_A_ID) == ["a", "b", "b.x"]


async def test_move_subtree_cycle_changes_no_rows(engine: AsyncEngine) -> None:
    await seed_tree(engine, TENANT_A_ID, ["a", "a.b", "a.b.c"])
    before = await all_paths(engine, TENANT_A_ID)
    with pytest.raises(CycleError):
        async with with_tenant(TENANT_A_ID, engine=engine) as conn:
            await move_subtree(conn, probe, "a.b", "a.b.c")
    assert await all_paths(engine, TENANT_A_ID) == before


async def test_descendants_skip_soft_deleted_rows_but_they_move_with_the_subtree(
    engine: AsyncEngine,
) -> None:
    ids = await seed_tree(engine, TENANT_A_ID, ["a", "a.b", "a.b.x", "a.c"])
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        await soft_delete(conn, probe, ids["a.b.x"])
        assert await descendants(conn, probe, "a.b") == []
        await move_subtree(conn, probe, "a.b", "a.c")
        restored = await restore(conn, probe, ids["a.b.x"])
    assert restored["path"] == "a.c.b.x"


async def test_two_concurrent_updates_with_the_same_version_one_wins(engine: AsyncEngine) -> None:
    row_id = await new_row(engine, TENANT_A_ID, "original")
    barrier = asyncio.Barrier(2)

    async def writer(name: str) -> dict[str, Any]:
        async with with_tenant(TENANT_A_ID, engine=engine) as conn:
            await barrier.wait()  # both transactions are open before either writes
            return await update_with_version(conn, probe, row_id, 1, {"name": name})

    results = await asyncio.gather(writer("one"), writer("two"), return_exceptions=True)
    winners = [r for r in results if isinstance(r, dict)]
    losers = [r for r in results if isinstance(r, ConflictError)]
    assert len(winners) == 1 and len(losers) == 1
    assert winners[0]["sync_version"] == 2
    assert losers[0].current["sync_version"] == 2
    assert losers[0].current["name"] == winners[0]["name"]

    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        again = await update_with_version(conn, probe, row_id, 2, {"name": "three"})
    assert (again["sync_version"], again["name"]) == (3, "three")


async def test_soft_delete_hides_a_row_from_active_and_restore_brings_it_back(
    engine: AsyncEngine,
) -> None:
    row_id = await new_row(engine, TENANT_A_ID)
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        deleted = await soft_delete(conn, probe, row_id)
        assert deleted["deleted_at"] is not None and deleted["sync_version"] == 2
        assert (await conn.execute(active(probe))).all() == []
        with pytest.raises(NotFoundError):
            await soft_delete(conn, probe, row_id)  # already deleted
        with pytest.raises(NotFoundError):
            await update_with_version(conn, probe, row_id, 2, {"name": "ghost"})
        back = await restore(conn, probe, row_id)
        assert back["deleted_at"] is None and back["sync_version"] == 3
        assert len((await conn.execute(active(probe))).all()) == 1
        with pytest.raises(NotFoundError):
            await restore(conn, probe, row_id)  # not deleted


async def test_create_idempotent_returns_the_original_row(engine: AsyncEngine) -> None:
    client_id = uuid.uuid4()
    values = {"name": "first", "client_generated_id": client_id}
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        first = await create_idempotent(conn, probe, {**values, "tenant_id": TENANT_A_ID})
        second = await create_idempotent(
            conn, probe, {**values, "name": "replay", "tenant_id": TENANT_A_ID}
        )
        count = (await conn.execute(text("SELECT count(*) FROM helper_probe"))).scalar_one()
    assert first.created and not second.created
    assert first.row["id"] == second.row["id"]
    assert second.row["name"] == "first" and second.row["sync_version"] == 1
    assert count == 1

    # The same client id in tenant B is a separate row.
    async with with_tenant(TENANT_B_ID, engine=engine) as conn:
        other = await create_idempotent(conn, probe, {**values, "tenant_id": TENANT_B_ID})
    assert other.created and other.row["id"] != first.row["id"]


async def test_create_idempotent_cannot_insert_for_another_tenant(engine: AsyncEngine) -> None:
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):  # RLS WITH CHECK
        async with with_tenant(TENANT_A_ID, engine=engine) as conn:
            await create_idempotent(
                conn, probe, {"tenant_id": TENANT_B_ID, "client_generated_id": uuid.uuid4()}
            )


async def test_attributes_are_validated_against_a_schema_stored_in_jsonb(
    engine: AsyncEngine,
) -> None:
    schema = {
        "type": "object",
        "required": ["wall_loss_mm"],
        "properties": {"wall_loss_mm": {"type": "number", "minimum": 0}},
    }
    type_id, asset_id = uuid.uuid4(), uuid.uuid4()
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        for row_id, name, attrs in (
            (type_id, "type", schema),
            (asset_id, "asset", {"wall_loss_mm": -2}),
        ):
            await conn.execute(
                probe.insert().values(id=row_id, tenant_id=TENANT_A_ID, name=name, attributes=attrs)
            )
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        rows = {r.id: r.attributes for r in (await conn.execute(active(probe))).all()}
    errors = validate_attributes(rows[type_id], rows[asset_id])
    assert [(e.path, e.term_key, e.params) for e in errors] == [
        ("$.wall_loss_mm", "validation.attribute.minimum", {"limit": 0})
    ]
    assert validate_attributes(rows[type_id], {"wall_loss_mm": 0.4}) == []


async def test_helpers_never_cross_tenants(engine: AsyncEngine) -> None:
    ids_a = await seed_tree(engine, TENANT_A_ID, ["a", "a.b", "a.b.c"])
    ids_b = await seed_tree(engine, TENANT_B_ID, ["a", "a.b", "a.x"])
    row_a = ids_a["a.b"]

    async with with_tenant(TENANT_B_ID, engine=engine) as conn:
        with pytest.raises(NotFoundError):  # A's row does not exist for B
            await update_with_version(conn, probe, row_a, 1, {"name": "hijack"})
        with pytest.raises(NotFoundError):
            await soft_delete(conn, probe, row_a)
        with pytest.raises(NotFoundError):
            await restore(conn, probe, row_a)
        assert {r["id"] for r in await descendants(conn, probe, "a", include_self=True)} == set(
            ids_b.values()
        )
        assert await move_subtree(conn, probe, "a.b", "a.x") == 1  # only B's own a.b

    assert await all_paths(engine, TENANT_A_ID) == ["a", "a.b", "a.b.c"]
    assert await all_paths(engine, TENANT_B_ID) == ["a", "a.x", "a.x.b"]
    async with with_tenant(TENANT_A_ID, engine=engine) as conn:
        assert len((await conn.execute(active(probe))).all()) == 3
        untouched = await update_with_version(conn, probe, row_a, 1, {"name": "mine"})
        assert untouched["sync_version"] == 2


# --- e2e (FastAPI fixture routes: 409 with the current record, 404 after soft delete) ----------


async def test_routes_return_409_with_the_current_record_and_404_for_deleted_rows(
    engine: AsyncEngine,
    principal_resolver: FixturePrincipalResolver,
    membership_resolver: FixtureMembershipResolver,
) -> None:
    app = create_app(
        principal_resolver=principal_resolver,
        membership_resolver=membership_resolver,
        env="test",
        tracing=False,
    )

    @app.get("/api/v1/_fixture/probe/{row_id}")
    async def read_row(row_id: UUID) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        async with with_tenant(get_context(), engine=engine) as conn:
            row = (await conn.execute(active(probe).where(probe.c.id == row_id))).first()
        if row is None:
            raise NotFoundError(str(row_id))
        return {"id": str(row.id), "name": row.name, "sync_version": row.sync_version}

    @app.patch("/api/v1/_fixture/probe/{row_id}")
    async def patch_row(row_id: UUID, version: int, name: str) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        async with with_tenant(get_context(), engine=engine) as conn:
            row = await update_with_version(conn, probe, row_id, version, {"name": name})
        return {"sync_version": row["sync_version"]}

    @app.delete("/api/v1/_fixture/probe/{row_id}")
    async def delete_row(row_id: UUID, undo: bool = False) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        async with with_tenant(get_context(), engine=engine) as conn:
            await (restore if undo else soft_delete)(conn, probe, row_id)
        return {"ok": True}

    row_id = await new_row(engine, TENANT_A_ID, "start")
    alice = {"Authorization": "Bearer token-alice"}
    bob = {"Authorization": "Bearer token-bob"}
    url = f"/api/v1/_fixture/probe/{row_id}"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.patch(url, params={"version": 1, "name": "v2"}, headers=alice)
        assert ok.status_code == 200 and ok.json() == {"sync_version": 2}

        stale = await client.patch(url, params={"version": 1, "name": "late"}, headers=alice)
        assert stale.status_code == 409
        body = stale.json()
        assert body["code"] == "VERSION_CONFLICT"
        assert body["current"]["sync_version"] == 2 and body["current"]["name"] == "v2"
        assert body["current"]["id"] == str(row_id)

        # Tenant B cannot see, change or delete tenant A's row: 404, not 409.
        assert (await client.get(url, headers=bob)).status_code == 404
        assert (
            await client.patch(url, params={"version": 2, "name": "x"}, headers=bob)
        ).status_code == 404
        assert (await client.delete(url, headers=bob)).status_code == 404

        assert (await client.get(url, headers=alice)).status_code == 200
        assert (await client.delete(url, headers=alice)).status_code == 200
        assert (await client.get(url, headers=alice)).status_code == 404
        assert (await client.delete(url, params={"undo": True}, headers=alice)).status_code == 200
        assert (await client.get(url, headers=alice)).status_code == 200
