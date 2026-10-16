"""APPROVALS-01: versioned definitions and pinned instances on real Postgres as ``aip_app``.

Tenants are seeded as the superuser (``workflow_definitions.tenant_id`` references ``tenants``);
everything else goes through ``aip_app`` with RLS on.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
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

from aip.modules.approvals.api import ApprovalsApi
from aip.modules.approvals.errors import DefinitionImmutableError, NoActiveDefinitionError
from aip.modules.approvals.service import DefinitionsService
from aip.modules.approvals.tests.fixtures import demo_spec, transition
from aip.platform.context import RequestContext, use_context

SEED_TENANTS = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
)

definitions = DefinitionsService()
approvals = ApprovalsApi()
P1 = UUID("00000000-0000-4000-8000-0000000000a1")
P2 = UUID("00000000-0000-4000-8000-0000000000b2")


def v2_spec() -> dict[str, Any]:
    """``demo`` plus an ``on_hold`` state reachable from ``submitted``."""
    spec = demo_spec()
    spec["states"].append({"code": "on_hold", "labelKey": "approvals.demo.state.on_hold"})
    spec["transitions"].append(transition("hold", "submitted", "on_hold"))
    spec["transitions"].append(transition("release", "on_hold", "submitted"))
    return spec


def ctx(tenant: UUID = TENANT_A_ID) -> RequestContext:
    return RequestContext(
        tenant_id=tenant, request_id=f"test-{uuid.uuid4().hex}", actor_id=ALICE_ID
    )


@pytest.fixture
async def db(tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    await _execute(tenant_db.db.superuser_url, SEED_TENANTS)
    return tenant_db


async def publish_new(
    db: TenantDb, spec: dict[str, Any], *, key: str = "demo", project_id: UUID | None = None
) -> UUID:
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            draft = await definitions.create_draft(conn, key, "inspection", spec, project_id)
            await definitions.publish(conn, draft.id)
    return draft.id


async def test_publishing_v2_never_moves_instances_started_under_v1(db: TenantDb) -> None:
    v1 = await publish_new(db, demo_spec())
    r1, r2 = uuid4(), uuid4()
    async with db.with_tenant(TENANT_A_ID) as conn:
        i1 = await approvals.start_instance(conn, "inspection", r1, None)
    v2 = await publish_new(db, v2_spec())
    async with db.with_tenant(TENANT_A_ID) as conn:
        i2 = await approvals.start_instance(conn, "inspection", r2, None)
        rows = dict(
            (await conn.execute(text("SELECT id, status FROM workflow_definitions"))).tuples().all()
        )
        pinned = dict(
            (await conn.execute(text("SELECT record_id, definition_id FROM workflow_instances")))
            .tuples()
            .all()
        )
    assert (i1.definition_id, i2.definition_id) == (v1, v2)
    assert pinned == {r1: v1, r2: v2}
    assert rows == {v1: "retired", v2: "active"}
    assert (i1.current_state, i1.version) == ("draft", 1)
    assert i2.version == 2


async def test_versions_count_up_per_key_and_publish_writes_an_audit_diff(db: TenantDb) -> None:
    v1 = await publish_new(db, demo_spec())
    v2 = await publish_new(db, v2_spec())
    async with db.with_tenant(TENANT_A_ID) as conn:
        versions = (
            (await conn.execute(text("SELECT version FROM workflow_definitions ORDER BY version")))
            .scalars()
            .all()
        )
        audit = (
            await conn.execute(
                text(
                    "SELECT definition_id, actor_id, change FROM workflow_definition_audit "
                    "ORDER BY created_at, (change->'after'->>'version')::int"
                )
            )
        ).all()
    assert versions == [1, 2]
    assert [(a.definition_id, a.actor_id) for a in audit] == [(v1, ALICE_ID), (v2, ALICE_ID)]
    first, second = (a.change for a in audit)
    assert first["before"] is None
    assert first["after"]["status"] == "active"
    assert second["before"]["id"] == str(v1)
    assert second["before"]["version"] == 1
    assert second["after"]["version"] == 2
    assert [s["code"] for s in second["after"]["spec"]["states"]][-1] == "on_hold"


async def test_active_and_retired_definitions_are_immutable(db: TenantDb) -> None:
    v1 = await publish_new(db, demo_spec())
    v2 = await publish_new(db, v2_spec())
    for definition_id in (v1, v2):
        async with db.with_tenant(TENANT_A_ID) as conn:
            with pytest.raises(DefinitionImmutableError):
                await definitions.update_draft(conn, definition_id, demo_spec())
        async with db.with_tenant(TENANT_A_ID) as conn:
            with pytest.raises(DefinitionImmutableError):
                await definitions.publish(conn, definition_id)


async def test_a_draft_can_be_edited_and_an_invalid_spec_is_rejected(db: TenantDb) -> None:
    async with db.with_tenant(TENANT_A_ID) as conn:
        draft = await definitions.create_draft(conn, "demo", "inspection", demo_spec())
        await definitions.update_draft(conn, draft.id, v2_spec())
        states = (
            await conn.execute(
                text("SELECT states FROM workflow_definitions WHERE id = :id"), {"id": draft.id}
            )
        ).scalar_one()
        bad = demo_spec()
        bad["transitions"][0]["to"] = "archived"
        with pytest.raises(ValidationError) as caught:
            await definitions.update_draft(conn, draft.id, bad)
    assert [s["code"] for s in states][-1] == "on_hold"
    assert caught.value.errors()[0]["loc"] == ("transitions", 0, "to")


async def test_aip_app_cannot_change_the_definition_audit(db: TenantDb) -> None:
    await publish_new(db, demo_spec())
    for sql in (
        "UPDATE workflow_definition_audit SET actor_id = NULL",
        "DELETE FROM workflow_definition_audit",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with db.with_tenant(TENANT_A_ID) as conn:
                await conn.execute(text(sql))


async def test_start_instance_is_idempotent(db: TenantDb) -> None:
    await publish_new(db, demo_spec())
    record = uuid4()
    async with db.with_tenant(TENANT_A_ID) as conn:
        first = await approvals.start_instance(conn, "inspection", record, None)
    async with db.with_tenant(TENANT_A_ID) as conn:
        second = await approvals.start_instance(conn, "inspection", record, None)
        count = (
            await conn.execute(
                text("SELECT count(*) FROM workflow_instances WHERE record_id = :r"), {"r": record}
            )
        ).scalar_one()
    assert first.id == second.id
    assert count == 1


async def test_a_project_override_wins_over_the_tenant_wide_definition(db: TenantDb) -> None:
    tenant_wide = await publish_new(db, demo_spec())
    p1 = await publish_new(db, v2_spec(), project_id=P1)
    async with db.with_tenant(TENANT_A_ID) as conn:
        for_p1 = await approvals.get_active_definition(conn, "inspection", P1)
        for_p2 = await approvals.get_active_definition(conn, "inspection", P2)
        tenant = await approvals.get_active_definition(conn, "inspection")
        with pytest.raises(NoActiveDefinitionError):
            await approvals.get_active_definition(conn, "issue", P1)
    assert (for_p1.id, for_p2.id, tenant.id) == (p1, tenant_wide, tenant_wide)
    assert for_p1.spec.states[-1].code == "on_hold"
    # Publishing the P1 override did not retire the tenant-wide version (different scope).
    assert for_p2.status == "active"


async def test_at_most_one_active_version_per_key_and_scope(db: TenantDb) -> None:
    await publish_new(db, demo_spec())
    with pytest.raises(DBAPIError, match="ux_workflow_definitions_active"):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(
                text(
                    "INSERT INTO workflow_definitions (id, tenant_id, record_type, key, version, "
                    "status, states, transitions, initial_state) VALUES (:id, :t, 'inspection', "
                    "'demo', 9, 'active', '[]', '[]', 'draft')"
                ),
                {"id": uuid4(), "t": TENANT_A_ID},
            )


async def test_other_tenants_and_unset_context_see_nothing(db: TenantDb) -> None:
    await publish_new(db, demo_spec())
    async with db.with_tenant(TENANT_A_ID) as conn:
        await approvals.start_instance(conn, "inspection", uuid4(), None)
    tables = ("workflow_definitions", "workflow_instances", "workflow_definition_audit")
    async with db.with_tenant(TENANT_B_ID) as conn:
        for table in tables:
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
        with pytest.raises(NoActiveDefinitionError):
            await approvals.get_active_definition(conn, "inspection")
    async with db.no_tenant() as conn:
        for table in tables:
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
    with pytest.raises(DBAPIError):
        async with db.no_tenant() as conn:
            await conn.execute(
                text(
                    "INSERT INTO workflow_definitions (id, tenant_id, record_type, key, version, "
                    "status, states, transitions, initial_state) VALUES (:id, :t, 'inspection', "
                    "'demo', 5, 'draft', :s, '[]', 'draft')"
                ),
                {"id": uuid4(), "t": TENANT_A_ID, "s": json.dumps([])},
            )
