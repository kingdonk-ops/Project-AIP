"""TESTING-13 (ADR 0035 §9): the dev and demo ``demo`` record type and its seed, on Postgres.

The same journeys run against the compose stack in ``e2e/web/approvals-transition.spec.ts``. Here a
``demo`` record is a project row (inserted as the superuser), and ``allPhotosClean`` follows the
project's status, exactly as on the stack.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.approvals.api import (
    register_guard_context_provider,
    register_record_resolver,
    unregister_guard_context_provider,
    unregister_record_resolver,
)
from aip.modules.approvals.demo import (
    DEMO_DEFINITION_KEY,
    DEMO_RECORD_TYPE,
    DEMO_RECORDS_ENV,
    DemoRecordsRefusedError,
    demo_spec,
    install_demo_records,
)
from aip.modules.approvals.guards.context_providers import provider_for, resolver_for
from aip.modules.approvals.seeds import seed
from aip.modules.approvals.service import DefinitionsService
from aip.modules.approvals.tests.conftest import (
    ALICE,
    BOB,
    GrantTable,
    act,
    ctx,
    history,
    su_execute,
    su_fetch,
)
from aip.platform.context import use_context

ROLE_A_ID = UUID("00000000-0000-4000-8000-00000000d1a0")
ROLE_B_ID = UUID("00000000-0000-4000-8000-00000000d1b0")

# ADR 0037: `projects` is project-scoped by RLS, so alice and bob need a tenant-scope assignment
# (as the fixture admins have on the stack) to see their tenant's projects. Permissions still come
# from the test grant table; this only establishes the RLS scope.
SEED_SCOPE_SQL = (
    "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
    f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active'), "
    f"('{BOB_ID}', '{TENANT_B_ID}', 'staff', 'bob@acme.test', 'Bob', 'active');"
    "INSERT INTO role (id, tenant_id, code, name) VALUES "
    f"('{ROLE_A_ID}', '{TENANT_A_ID}', 'member', 'Member'), "
    f"('{ROLE_B_ID}', '{TENANT_B_ID}', 'member', 'Member');"
    "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type) VALUES "
    f"(gen_random_uuid(), '{TENANT_A_ID}', '{ALICE_ID}', '{ROLE_A_ID}', 'tenant'), "
    f"(gen_random_uuid(), '{TENANT_B_ID}', '{BOB_ID}', '{ROLE_B_ID}', 'tenant')"
)

DEMO_ROLE = {
    "approvals.view",
    "approvals.start",
    "approvals.inspection.execute",
    "approvals.inspection.approve",
}


@pytest.fixture(autouse=True)
def demo_records(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Replaces the conftest's in-memory ``demo`` records with the real project-backed ones."""
    monkeypatch.setenv(DEMO_RECORDS_ENV, "1")
    unregister_record_resolver(DEMO_RECORD_TYPE)
    # The inspections module registers the real ``inspection`` hooks at import; put them back.
    resolver, provider = resolver_for("inspection"), provider_for("inspection")
    try:
        yield
    finally:
        unregister_record_resolver(DEMO_RECORD_TYPE)
        unregister_guard_context_provider(DEMO_RECORD_TYPE)
        unregister_record_resolver("inspection")
        unregister_guard_context_provider("inspection")
        if resolver is not None:
            register_record_resolver("inspection", resolver)
        if provider is not None:
            register_guard_context_provider("inspection", provider)


@pytest.fixture(autouse=True)
def roles(grants: GrantTable) -> GrantTable:
    grants.by_user[ALICE_ID] = set(DEMO_ROLE)
    grants.by_user[BOB_ID] = set(DEMO_ROLE)
    return grants


@pytest.fixture
async def demo_definition(db: TenantDb) -> UUID:
    await su_execute(db, SEED_SCOPE_SQL)
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            definition = await DefinitionsService().install_spec(
                conn, DEMO_DEFINITION_KEY, DEMO_RECORD_TYPE, demo_spec()
            )
    return definition.id


async def add_project(db: TenantDb, tenant: UUID = TENANT_A_ID) -> UUID:
    project_id = uuid.uuid4()
    code = f"WF-{project_id.hex[:8].upper()}"
    await su_execute(
        db,
        "INSERT INTO projects (id, tenant_id, code, name, status) VALUES "
        f"('{project_id}', '{tenant}', '{code}', 'Workflow journey', 'draft')",
    )
    return project_id


async def start(
    client: httpx.AsyncClient, record_id: UUID, headers: dict[str, str]
) -> httpx.Response:
    body = {"recordType": DEMO_RECORD_TYPE, "recordId": str(record_id)}
    return await client.post("/api/v1/approvals/instances", json=body, headers=headers)


def test_the_record_type_needs_the_switch_and_a_non_production_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DEMO_RECORDS_ENV)
    assert install_demo_records("development") == []
    monkeypatch.setenv(DEMO_RECORDS_ENV, "1")
    for env in ("production", "staging", ""):
        with pytest.raises(DemoRecordsRefusedError):
            install_demo_records(env)
    # INSPECTIONS-01 registered the real ``inspection`` resolver, so only ``demo`` is added...
    assert install_demo_records("demo") == [DEMO_RECORD_TYPE]
    assert install_demo_records("demo") == []  # a second call registers nothing twice
    # ...and without it the project-backed fallback still serves ``inspection``.
    unregister_record_resolver("inspection")
    assert install_demo_records("demo") == ["inspection"]


@pytest.mark.usefixtures("demo_definition")
async def test_submit_then_a_guarded_approve_on_a_project_backed_record(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    project_id = await add_project(db)
    started = await start(client, project_id, ALICE)
    assert started.status_code == 201, started.text
    instance = started.json()
    assert (instance["currentState"], instance["projectId"]) == ("draft", str(project_id))

    assert (await act(client, instance["id"], "submit")).status_code == 200
    refused = await act(client, instance["id"], "approve")
    assert refused.status_code == 422
    assert refused.json() == {
        "code": "GUARD_FAILED",
        "messageKey": "workflow.demo.guard.photos_not_clean",
    }

    # The fixture switch: an active project's photos count as clean.
    await su_execute(db, f"UPDATE projects SET status = 'active' WHERE id = '{project_id}'")
    approved = await act(client, instance["id"], "approve")
    assert approved.status_code == 200, approved.text
    found = await history(client, instance["id"])
    assert [e["action"] for e in found["entries"]] == ["submit", "approve"]
    assert found["entries"][1]["guardResult"]["passed"] is True
    assert found["chainValid"] is True

    # Tenant B sees neither the instance nor the record.
    as_b = await client.get(f"/api/v1/approvals/instances/{instance['id']}/history", headers=BOB)
    assert as_b.status_code == 404
    assert (await start(client, project_id, BOB)).status_code == 404


@pytest.mark.usefixtures("demo_definition")
async def test_a_record_that_is_no_project_of_the_tenant_is_404(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    assert (await start(client, uuid.uuid4(), ALICE)).status_code == 404
    other = await add_project(db, TENANT_B_ID)
    assert (await start(client, other, ALICE)).status_code == 404


async def test_the_seed_publishes_the_demo_workflow_once_in_kaefer_demo_only(
    db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", db.db.app_url)
    from aip.platform.db.engine import dispose_engine

    await dispose_engine()
    try:
        _, first = await seed(env="test")
        _, second = await seed(env="test")
    finally:
        await dispose_engine()
    assert (first.key, first.record_type, first.version) == ("demo", "demo", 1)
    assert first.status == "active" and second.id == first.id
    counts = await su_fetch(
        db,
        "SELECT tenant_id, count(*) FROM workflow_definitions WHERE key = $1 GROUP BY tenant_id",
        DEMO_DEFINITION_KEY,
    )
    assert [tuple(r) for r in counts] == [(TENANT_A_ID, 1)]
