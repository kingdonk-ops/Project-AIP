"""``get_display_names`` against real Postgres through ``aip_app`` with RLS on (IDENTITY-09)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func
from tests.fixtures.postgres import TenantDb

from aip.modules.identity import repository as repo
from aip.modules.identity.api import get_display_names

from .conftest import TENANT_A_ID, TENANT_B_ID


async def _seed(db: TenantDb, tenant: UUID, email: str, display_name: str) -> UUID:
    async with db.with_tenant(tenant) as conn:
        return await repo.insert_user(
            conn,
            tenant_id=tenant,
            email=email,
            display_name=display_name,
            user_class="staff",
            status="active",
            sso_managed=True,
        )


async def test_maps_the_bound_tenants_users_to_display_names(idb: TenantDb) -> None:
    alice = await _seed(idb, TENANT_A_ID, "alice@kaefer.test", "Alice Approver")
    carol = await _seed(idb, TENANT_A_ID, "carol@kaefer.test", "Carol Checker")
    async with idb.with_tenant(TENANT_A_ID) as conn:
        names = await get_display_names(conn, [alice, carol, alice])
    assert names == {alice: "Alice Approver", carol: "Carol Checker"}


async def test_another_tenants_and_unknown_ids_are_left_out(idb: TenantDb) -> None:
    alice = await _seed(idb, TENANT_A_ID, "alice@kaefer.test", "Alice Approver")
    bob = await _seed(idb, TENANT_B_ID, "bob@acme.test", "Bob Builder")
    async with idb.with_tenant(TENANT_A_ID) as conn:
        assert await get_display_names(conn, [alice, bob, uuid4()]) == {alice: "Alice Approver"}
    async with idb.with_tenant(TENANT_B_ID) as conn:
        assert await get_display_names(conn, [alice, bob]) == {bob: "Bob Builder"}


async def test_deactivated_and_soft_deleted_signers_keep_their_name(idb: TenantDb) -> None:
    gone = await _seed(idb, TENANT_A_ID, "gone@kaefer.test", "Gwen Gone")
    left = await _seed(idb, TENANT_A_ID, "left@kaefer.test", "Lee Left")
    async with idb.with_tenant(TENANT_A_ID) as conn:
        await repo.set_user_status(conn, left, "deactivated")
        await repo.update_user(conn, gone, deleted_at=func.now())
    async with idb.with_tenant(TENANT_A_ID) as conn:
        names = await get_display_names(conn, {gone, left})
    assert names == {gone: "Gwen Gone", left: "Lee Left"}


async def test_no_ids_is_an_empty_map(idb: TenantDb) -> None:
    async with idb.with_tenant(TENANT_A_ID) as conn:
        assert await get_display_names(conn, []) == {}
