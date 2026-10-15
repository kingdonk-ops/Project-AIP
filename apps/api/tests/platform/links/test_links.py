"""ARCH-08: the record-link service (unit + integration on real Postgres as ``aip_app``).

The fixture chain is defect -> NCR -> repair -> re-inspection (record types ``fixture_defect``,
``fixture_ncr``, ``fixture_repair``, ``fixture_inspection``). Tenants are seeded as the superuser
because ``record_links.tenant_id`` references ``tenants``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.context import RequestContext, use_context
from aip.platform.links import MAX_DEPTH, LinkService, RecordRef
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

SEED_TENANTS = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
)

links = LinkService()


def ref(record_type: str) -> RecordRef:
    return RecordRef(record_type, uuid4())


def ctx(tenant: UUID = TENANT_A_ID) -> RequestContext:
    return RequestContext(
        tenant_id=tenant, request_id=f"test-{uuid.uuid4().hex}", actor_id=ALICE_ID
    )


class FakeConn:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def execute(self, statement: Any, *args: Any) -> None:
        self.calls.append(statement)


# --- unit -------------------------------------------------------------------------------------


async def test_traverse_rejects_a_depth_above_five_before_any_sql() -> None:
    conn = FakeConn()
    with pytest.raises(ValueError, match="max_depth"):
        await links.traverse(cast("AsyncConnection", conn), ref("fixture_defect"), max_depth=6)
    assert MAX_DEPTH == 5
    assert conn.calls == []


async def test_traverse_rejects_a_depth_below_one() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        await links.traverse(
            cast("AsyncConnection", FakeConn()), ref("fixture_defect"), max_depth=0
        )


@pytest.mark.parametrize("bad", ["", "Defect", "1defect", "defect-ncr", "a" * 64])
def test_a_record_type_must_be_a_snake_case_code(bad: str) -> None:
    with pytest.raises(ValueError, match="record type"):
        RecordRef(bad, uuid4())


async def test_a_link_kind_must_be_a_snake_case_code() -> None:
    conn = FakeConn()
    with pytest.raises(ValueError, match="link kind"):
        await links.link(
            cast("AsyncConnection", conn), ref("fixture_defect"), ref("fixture_ncr"), "Follows"
        )
    assert conn.calls == []


async def test_a_record_cannot_link_to_itself() -> None:
    same = ref("fixture_defect")
    with pytest.raises(ValueError, match="itself"):
        await links.link(cast("AsyncConnection", FakeConn()), same, same, "follows")


# --- integration ------------------------------------------------------------------------------


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await _execute(tenant_db.db.superuser_url, SEED_TENANTS)
    return tenant_db


async def count_links(db: TenantDb, tenant: UUID) -> int:
    async with db.with_tenant(tenant) as conn:
        return (await conn.execute(text("SELECT count(*) FROM record_links"))).scalar_one()


async def test_linking_twice_inserts_one_row_and_returns_the_existing_id(db: TenantDb) -> None:
    a, b = ref("fixture_defect"), ref("fixture_ncr")
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            first = await links.link(conn, a, b, "follows")
        async with db.with_tenant(TENANT_A_ID) as conn:
            second = await links.link(conn, a, b, "follows")
    assert first == second
    assert await count_links(db, TENANT_A_ID) == 1
    async with db.with_tenant(TENANT_A_ID) as conn:
        row = (await conn.execute(text("SELECT tenant_id, created_by FROM record_links"))).one()
    assert (row.tenant_id, row.created_by) == (TENANT_A_ID, ALICE_ID)


async def test_a_different_kind_is_a_separate_link(db: TenantDb) -> None:
    a, b = ref("fixture_defect"), ref("fixture_ncr")
    async with db.with_tenant(TENANT_A_ID) as conn:
        first = await links.link(conn, a, b, "follows")
        second = await links.link(conn, a, b, "relates_to")
    assert first != second
    assert await count_links(db, TENANT_A_ID) == 2


async def test_the_defect_chain_is_retrievable_in_order(db: TenantDb) -> None:
    d, n, r, i = (
        ref("fixture_defect"),
        ref("fixture_ncr"),
        ref("fixture_repair"),
        ref("fixture_inspection"),
    )
    asset = uuid4()
    async with db.with_tenant(TENANT_A_ID) as conn:
        await links.link(conn, d, n, "follows", asset_id=asset)
        await links.link(conn, n, r, "follows", asset_id=asset)
        await links.link(conn, r, i, "follows", asset_id=asset)
        assert await links.traverse(conn, d) == [(n, 1), (r, 2), (i, 3)]
        assets = (await conn.execute(text("SELECT DISTINCT asset_id FROM record_links"))).all()
    assert [a.asset_id for a in assets] == [asset]


async def test_traverse_stops_at_max_depth(db: TenantDb) -> None:
    d, n, r, i = (
        ref("fixture_defect"),
        ref("fixture_ncr"),
        ref("fixture_repair"),
        ref("fixture_inspection"),
    )
    async with db.with_tenant(TENANT_A_ID) as conn:
        await links.link(conn, d, n, "follows")
        await links.link(conn, n, r, "follows")
        await links.link(conn, r, i, "follows")
        assert await links.traverse(conn, d, max_depth=2) == [(n, 1), (r, 2)]


async def test_a_cycle_terminates_without_duplicates(db: TenantDb) -> None:
    a, b, c = ref("fixture_defect"), ref("fixture_ncr"), ref("fixture_repair")
    async with db.with_tenant(TENANT_A_ID) as conn:
        await links.link(conn, a, b, "follows")
        await links.link(conn, b, c, "follows")
        await links.link(conn, c, a, "follows")
        result = await links.traverse(conn, a, max_depth=5)
    assert [found for found, _ in result] == [b, c, a]
    assert result == [(b, 1), (c, 2), (a, 3)]


async def test_a_diamond_reports_each_record_once_at_its_shortest_depth(db: TenantDb) -> None:
    a, b, c, d = (
        ref("fixture_defect"),
        ref("fixture_ncr"),
        ref("fixture_ncr"),
        ref("fixture_repair"),
    )
    async with db.with_tenant(TENANT_A_ID) as conn:
        await links.link(conn, a, b, "follows")
        await links.link(conn, a, c, "follows")
        await links.link(conn, b, d, "follows")
        await links.link(conn, c, d, "follows")
        await links.link(conn, a, d, "relates_to")
        result = await links.traverse(conn, a)
    assert sorted(result, key=lambda pair: (pair[1], pair[0].type, str(pair[0].id))) == result
    assert dict(result) == {b: 1, c: 1, d: 1}


async def test_unlink_soft_deletes_and_traverse_ignores_it(db: TenantDb) -> None:
    a, b = ref("fixture_defect"), ref("fixture_ncr")
    async with db.with_tenant(TENANT_A_ID) as conn:
        first = await links.link(conn, a, b, "follows")
        assert await links.unlink(conn, a, b, "follows") is True
        assert await links.unlink(conn, a, b, "follows") is False
        assert await links.traverse(conn, a) == []
        deleted = (
            await conn.execute(
                text("SELECT deleted_at FROM record_links WHERE id = :id"), {"id": first}
            )
        ).scalar_one()
        assert deleted is not None
        relinked = await links.link(conn, a, b, "follows")  # a new live row is allowed
    assert relinked != first


async def test_another_tenant_cannot_traverse_or_unlink_tenant_a_records(db: TenantDb) -> None:
    d, n = ref("fixture_defect"), ref("fixture_ncr")
    async with db.with_tenant(TENANT_A_ID) as conn:
        await links.link(conn, d, n, "follows")
    async with db.with_tenant(TENANT_B_ID) as conn:
        assert await links.traverse(conn, d) == []
        assert await links.unlink(conn, d, n, "follows") is False
    async with db.with_tenant(TENANT_A_ID) as conn:
        assert await links.traverse(conn, d) == [(n, 1)]


async def test_aip_app_cannot_hard_delete_a_link(db: TenantDb) -> None:
    async with db.with_tenant(TENANT_A_ID) as conn:
        await links.link(conn, ref("fixture_defect"), ref("fixture_ncr"), "follows")
    with pytest.raises(DBAPIError) as caught:
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text("DELETE FROM record_links"))
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"


async def test_concurrent_links_of_one_pair_make_one_row(db: TenantDb) -> None:
    a, b = ref("fixture_defect"), ref("fixture_ncr")

    async def link_once() -> UUID:
        async with db.with_tenant(TENANT_A_ID) as conn:
            return await links.link(conn, a, b, "follows")

    first, second = await asyncio.gather(link_once(), link_once())
    assert first == second
    assert await count_links(db, TENANT_A_ID) == 1


async def test_a_dense_two_way_graph_reports_each_record_once(db: TenantDb) -> None:
    records = [ref("fixture_ncr") for _ in range(12)]
    async with db.with_tenant(TENANT_A_ID) as conn:
        for x in records:
            for y in records:
                if x != y:
                    await links.link(conn, x, y, "relates_to")
        result = await links.traverse(conn, records[0])
    others = set(records[1:])
    assert {found for found, depth in result if depth == 1} == others
    assert result[-1] == (records[0], 2)  # back to the start once, then nothing new
    assert len(result) == len(records)
