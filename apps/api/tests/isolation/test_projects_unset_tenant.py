"""TESTING-09 step 4: the M0 isolation floor on ``projects`` (ADR 0002, ADR 0007).

One project per tenant is seeded as the owner; every assertion connects as ``aip_app``. With no
``app.tenant_id`` the table shows no rows and refuses writes (RLS WITH CHECK), and each tenant's
context shows only its own row. Weakening the ``projects`` policy (for example ``USING (true)``)
fails these tests.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import OwnerSeeder, TenantDb

PROJECT_A = UUID("00000000-0000-4000-8000-0000000009aa")
PROJECT_B = UUID("00000000-0000-4000-8000-0000000009bb")
COUNT = text("SELECT count(*) FROM projects")
IDS = text("SELECT id FROM projects")
INSUFFICIENT_PRIVILEGE = "42501"


@pytest.fixture
def seeded(tenant_db: TenantDb, owner_conn_for_seeding_only: OwnerSeeder) -> TenantDb:
    for tenant, project in ((TENANT_A_ID, PROJECT_A), (TENANT_B_ID, PROJECT_B)):
        owner_conn_for_seeding_only.insert(
            tenant,
            "INSERT INTO projects (id, tenant_id, code, name)"
            f" VALUES ('{project}', '{tenant}', 'ISO-1', 'Isolation probe');",
        )
    return tenant_db


async def test_no_tenant_context_sees_no_projects(seeded: TenantDb) -> None:
    async with seeded.no_tenant() as conn:
        assert (await conn.execute(COUNT)).scalar_one() == 0, (
            "M0: a query with no tenant context returns 0 rows"
        )


async def test_an_insert_without_a_tenant_fails_the_rls_check(seeded: TenantDb) -> None:
    with pytest.raises(DBAPIError) as caught:
        async with seeded.no_tenant() as conn:
            await conn.execute(
                text(
                    "INSERT INTO projects (id, tenant_id, code, name)"
                    " VALUES (gen_random_uuid(), :tenant, 'ISO-2', 'No tenant')"
                ),
                {"tenant": TENANT_A_ID},
            )
    assert getattr(caught.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, (
        "M0: a write with no tenant context is refused by the RLS WITH CHECK"
    )


@pytest.mark.parametrize(
    ("tenant", "project"), [(TENANT_A_ID, PROJECT_A), (TENANT_B_ID, PROJECT_B)]
)
async def test_each_tenant_sees_exactly_its_own_project(
    seeded: TenantDb, tenant: UUID, project: UUID
) -> None:
    async with seeded.with_tenant(tenant) as conn:
        assert (await conn.execute(COUNT)).scalar_one() == 1
        assert [row[0] for row in (await conn.execute(IDS)).all()] == [project], (
            "M0: a tenant sees only its own project"
        )
