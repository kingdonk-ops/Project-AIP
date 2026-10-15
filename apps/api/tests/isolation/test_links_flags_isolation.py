"""ARCH-08 step 5: tenant isolation of ``record_links`` and ``tenant_feature_flags``.

Two fixture tenants, connecting as ``aip_app``: each tenant sees and changes only its own rows, a
row cannot be written for another tenant, and with no tenant set nothing is visible or writable.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import TENANT_A_ID, TENANT_B_ID
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

INSERTS = {
    "record_links": (
        "INSERT INTO record_links (id, tenant_id, from_type, from_id, to_type, to_id, link_kind)"
        " VALUES (:id, :tenant, 'fixture_defect', gen_random_uuid(), 'fixture_ncr',"
        " gen_random_uuid(), 'follows')"
    ),
    "tenant_feature_flags": (
        "INSERT INTO tenant_feature_flags (id, tenant_id, flag, enabled)"
        " VALUES (:id, :tenant, 'bim', true)"
    ),
}
TABLES = sorted(INSERTS)


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await _execute(tenant_db.db.superuser_url, SEED_TENANTS)
    return tenant_db


async def insert_row(db: TenantDb, table: str, tenant: UUID) -> UUID:
    row_id = uuid4()
    async with db.with_tenant(tenant) as conn:
        await conn.execute(text(INSERTS[table]), {"id": row_id, "tenant": tenant})
    return row_id


@pytest.mark.parametrize("table", TABLES)
async def test_each_tenant_sees_only_its_own_rows(db: TenantDb, table: str) -> None:
    a_row = await insert_row(db, table, TENANT_A_ID)
    b_row = await insert_row(db, table, TENANT_B_ID)
    for tenant, own in ((TENANT_A_ID, a_row), (TENANT_B_ID, b_row)):
        async with db.with_tenant(tenant) as conn:
            ids = (await conn.execute(text(f"SELECT id FROM {table}"))).scalars().all()
        assert ids == [own]


@pytest.mark.parametrize("table", TABLES)
async def test_a_tenant_cannot_write_a_row_for_another_tenant(db: TenantDb, table: str) -> None:
    with pytest.raises(DBAPIError) as caught:
        async with db.with_tenant(TENANT_B_ID) as conn:
            await conn.execute(text(INSERTS[table]), {"id": uuid4(), "tenant": TENANT_A_ID})
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"


@pytest.mark.parametrize("table", TABLES)
async def test_a_tenant_cannot_update_another_tenants_row(db: TenantDb, table: str) -> None:
    a_row = await insert_row(db, table, TENANT_A_ID)
    async with db.with_tenant(TENANT_B_ID) as conn:
        result = await conn.execute(
            text(f"UPDATE {table} SET deleted_at = now() WHERE id = :id"),
            {"id": a_row},
        )
    assert result.rowcount == 0
    async with db.with_tenant(TENANT_A_ID) as conn:
        deleted = (
            await conn.execute(
                text(f"SELECT deleted_at FROM {table} WHERE id = :id"), {"id": a_row}
            )
        ).scalar_one()
    assert deleted is None


@pytest.mark.parametrize("table", TABLES)
async def test_with_no_tenant_nothing_is_visible_or_writable(db: TenantDb, table: str) -> None:
    await insert_row(db, table, TENANT_A_ID)
    async with db.no_tenant() as conn:
        assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
    with pytest.raises(DBAPIError) as caught:
        async with db.no_tenant() as conn:
            await conn.execute(text(INSERTS[table]), {"id": uuid4(), "tenant": TENANT_A_ID})
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"
