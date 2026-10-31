"""INSPECTIONS-01 integration tests: the API, the table and the approvals lifecycle on Postgres.

The app connects as ``aip_app`` (RLS on). Users come from the AUTH_TEST_STUB principal header;
permissions from the ``grants`` fixture (see ``conftest``). The lifecycle is the APPROVALS-09 v2
``inspection_standard`` preset: ``ready`` (supervisor) → ``inspect`` (inspector) →
``request_supervisor_review`` (inspector) → ``mark_performed`` (supervisor, critical: a fresh aal 2
session).
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import Outbox, TenantDb

from aip.modules.inspections import service
from aip.modules.inspections.events import follow_workflow
from aip.platform.access import AccessPrincipal, Grant, ProjectScope
from aip.platform.context import RequestContext, use_context
from aip.platform.db.scope import run_as_system
from aip.platform.events.dispatcher import DispatchSettings, dispatch_batch
from aip.platform.events.subscribers import DomainEvent, subscribers

from .conftest import (
    ALICE,
    BOB,
    INSPECTOR,
    INSPECTOR_ID,
    KF_01,
    KF_02,
    SUPERVISOR,
    SUPERVISOR_ID,
    VIEWER,
    VIEWER_ID,
    GrantTable,
    Setup,
    count,
    create_asset,
    new_revision,
    publish,
    signed,
    su_fetch,
    upload_template,
)

INSPECTIONS = "/api/v1/inspections"
HAPPY_PATH = [
    ("ready", SUPERVISOR_ID, "draft", "assigned"),
    ("inspect", INSPECTOR_ID, "assigned", "in_progress"),
    ("request_supervisor_review", INSPECTOR_ID, "in_progress", "supervisor_review"),
    ("mark_performed", SUPERVISOR_ID, "supervisor_review", "performed"),
]
INSPECTIONS_ONLY = subscribers.for_modules(["inspections"])


def body(setup: Setup, **extra: Any) -> dict[str, Any]:
    return {
        "assetId": str(setup.asset_id),
        "projectId": str(KF_01),
        "templateId": str(setup.template_id),
        "kind": "inspection",
        **extra,
    }


async def create(
    client: httpx.AsyncClient, setup: Setup, headers: dict[str, str] = SUPERVISOR, **extra: Any
) -> dict[str, Any]:
    response = await client.post(INSPECTIONS, json=body(setup, **extra), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def act(
    client: httpx.AsyncClient,
    inspection_id: str,
    action: str,
    headers: dict[str, str],
    **extra: Any,
) -> httpx.Response:
    return await client.post(
        f"{INSPECTIONS}/{inspection_id}/transition",
        json={"action": action, **extra},
        headers=headers,
    )


async def drive(client: httpx.AsyncClient, inspection_id: str, steps: int) -> dict[str, Any]:
    """Take the first ``steps`` happy-path actions by role; return the last inspection."""
    last: dict[str, Any] = {}
    for action, user, _, _ in HAPPY_PATH[:steps]:
        response = await act(client, inspection_id, action, signed(user))
        assert response.status_code == 200, (action, response.text)
        last = response.json()["inspection"]
    return last


async def counts(db: TenantDb) -> tuple[int, int, int]:
    """(inspections, domain_events named inspection.*, workflow_instances for inspections)."""
    return (
        await count(db, "SELECT count(*) FROM inspections"),
        await count(db, "SELECT count(*) FROM domain_events WHERE event_name LIKE 'inspection.%'"),
        await count(db, "SELECT count(*) FROM workflow_instances WHERE record_type = 'inspection'"),
    )


async def state_events(db: TenantDb, inspection_id: str) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT payload FROM domain_events WHERE event_name = 'inspection.state_changed'"
        " AND aggregate_id = $1 ORDER BY occurred_at, id",
        UUID(inspection_id),
    )
    return [json.loads(r[0]) if isinstance(r[0], str) else dict(r[0]) for r in rows]


async def dispatch_all(outbox: Outbox) -> None:
    settings = DispatchSettings(batch_size=100)
    while (await dispatch_batch(outbox.jobs, outbox.app, INSPECTIONS_ONLY, settings)).claimed:
        pass


# --- create ---------------------------------------------------------------------------------------


async def test_create_writes_the_row_the_instance_and_one_event(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    created = await create(client, setup)
    assert created["state"] == "draft"
    assert created["templateRevisionId"] == str(setup.revision_id)
    assert (created["source"], created["sourceRefId"], created["kind"]) == (
        "manual",
        None,
        "inspection",
    )
    assert created["projectId"] == str(KF_01)
    assert await counts(db) == (1, 1, 1)
    rows = await su_fetch(
        db,
        "SELECT event_name, payload, asset_id FROM domain_events"
        " WHERE event_name = 'inspection.created'",
    )
    (_name, payload, asset_id) = rows[0]
    payload = json.loads(payload) if isinstance(payload, str) else dict(payload)
    assert payload == {
        "inspectionId": created["id"],
        "assetId": str(setup.asset_id),
        "projectId": str(KF_01),
        "kind": "inspection",
        "templateRevisionId": str(setup.revision_id),
        "source": "manual",
    }
    assert asset_id == setup.asset_id
    instance = await su_fetch(
        db,
        "SELECT i.id, i.current_state, i.project_id, d.status FROM workflow_instances i"
        " JOIN workflow_definitions d ON d.id = i.definition_id WHERE i.record_id = $1",
        UUID(created["id"]),
    )
    assert [tuple(r) for r in instance] == [
        (UUID(created["workflowInstanceId"]), "draft", KF_01, "active")
    ]


async def test_a_replayed_client_generated_id_returns_the_same_inspection(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    client_id = str(uuid.uuid4())
    first = await client.post(
        INSPECTIONS, json=body(setup, clientGeneratedId=client_id), headers=SUPERVISOR
    )
    again = await client.post(
        INSPECTIONS, json=body(setup, clientGeneratedId=client_id), headers=SUPERVISOR
    )
    assert (first.status_code, again.status_code) == (201, 200), again.text
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["clientGeneratedId"] == client_id
    assert await counts(db) == (1, 1, 1)


async def test_refused_creates_write_nothing(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    unknown_asset = await client.post(
        INSPECTIONS, json=body(setup, assetId=str(uuid.uuid4())), headers=SUPERVISOR
    )
    assert unknown_asset.status_code == 404, unknown_asset.text
    assert unknown_asset.json() == {
        "code": "ASSET_NOT_FOUND",
        "messageKey": "inspection.error.asset_not_found",
    }

    draft_only, draft_revision = await upload_template(client, code="coating-draft")
    unpublished = await client.post(
        INSPECTIONS, json=body(setup, templateId=str(draft_only)), headers=SUPERVISOR
    )
    assert unpublished.status_code == 422, unpublished.text
    assert unpublished.json()["code"] == "TEMPLATE_NOT_PUBLISHED"

    for revision in (draft_revision, uuid.uuid4()):
        mismatch = await client.post(
            INSPECTIONS, json=body(setup, templateRevisionId=str(revision)), headers=SUPERVISOR
        )
        assert mismatch.status_code == 422, mismatch.text
        assert mismatch.json()["code"] == "REVISION_MISMATCH"

    unknown_project = await client.post(
        INSPECTIONS, json=body(setup, projectId=str(uuid.uuid4())), headers=SUPERVISOR
    )
    assert unknown_project.status_code == 404, unknown_project.text

    # tenant-b has its own asset and published template but no inspection workflow.
    asset_b = await create_asset(db, "TK-B1", TENANT_B_ID)
    template_b, revision_b = await upload_template(client, headers=BOB)
    await publish(client, revision_b, headers=BOB)
    no_workflow = await client.post(
        INSPECTIONS,
        json={"assetId": str(asset_b), "templateId": str(template_b), "kind": "itp"},
        headers=BOB,
    )
    assert no_workflow.status_code == 422, no_workflow.text
    assert no_workflow.json() == {
        "code": "NO_INSPECTION_WORKFLOW",
        "messageKey": "inspection.error.no_inspection_workflow",
    }
    assert await counts(db) == (0, 0, 0)


async def test_a_viewer_cannot_create(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    response = await client.post(INSPECTIONS, json=body(setup), headers=VIEWER)
    assert response.status_code == 403, response.text
    assert response.json()["permission"] == "inspection.create"
    assert await counts(db) == (0, 0, 0)


async def test_a_body_with_server_owned_fields_is_422(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    for extra in ({"source": "reinspection"}, {"state": "performed"}, {"kind": "audit"}):
        response = await client.post(INSPECTIONS, json=body(setup, **extra), headers=SUPERVISOR)
        assert response.status_code == 422, (extra, response.text)
    assert await counts(db) == (0, 0, 0)


async def test_a_failed_emit_rolls_back_the_row_and_the_instance(
    lenient_client: httpx.AsyncClient,
    db: TenantDb,
    setup: Setup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_emit(*args: object, **kwargs: object) -> UUID:
        raise RuntimeError("outbox down")

    monkeypatch.setattr(service, "emit", broken_emit)
    response = await lenient_client.post(INSPECTIONS, json=body(setup), headers=SUPERVISOR)
    assert response.status_code == 500
    assert await counts(db) == (0, 0, 0)


# --- the pinned revision --------------------------------------------------------------------------


async def test_a_new_revision_affects_only_new_inspections(
    client: httpx.AsyncClient, setup: Setup
) -> None:
    first = await create(client, setup)
    revision_2 = await new_revision(client, setup.template_id)
    second = await create(client, setup)
    assert second["templateRevisionId"] == str(revision_2)
    found = await client.get(f"{INSPECTIONS}/{first['id']}", headers=VIEWER)
    assert found.json()["templateRevisionId"] == str(setup.revision_id)
    # A named, still-published revision can be pinned; the superseded one cannot.
    named = await create(client, setup, templateRevisionId=str(revision_2))
    assert named["templateRevisionId"] == str(revision_2)
    old = await client.post(
        INSPECTIONS, json=body(setup, templateRevisionId=str(setup.revision_id)), headers=SUPERVISOR
    )
    assert old.status_code == 422 and old.json()["code"] == "REVISION_MISMATCH"


async def test_the_database_refuses_to_change_a_pin(
    db: TenantDb, setup: Setup, client: httpx.AsyncClient
) -> None:
    created = await create(client, setup)
    with pytest.raises(DBAPIError) as caught:  # system: the project-scope policy shows the row
        async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
            await conn.execute(
                text("UPDATE inspections SET template_revision_id = gen_random_uuid()")
            )
    assert getattr(caught.value.orig, "sqlstate", None) == "P0001"
    found = await su_fetch(
        db, "SELECT template_revision_id FROM inspections WHERE id = $1", UUID(created["id"])
    )
    assert found[0][0] == setup.revision_id


# --- the lifecycle --------------------------------------------------------------------------------


async def test_the_happy_path_follows_every_transition_once(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    created = await create(client, setup)
    detail = await client.get(f"{INSPECTIONS}/{created['id']}", headers=SUPERVISOR)
    assert detail.status_code == 200, detail.text
    view = detail.json()
    assert (view["currentState"], view["pendingCountersign"]) == ("draft", None)
    by_action = {t["action"]: t for t in view["availableTransitions"]}
    assert by_action["ready"]["allowed"] is True
    assert by_action["ready"]["labelKey"] == "workflow.inspection.action.ready"
    assert by_action["retire"]["allowed"] is False  # the supervisor does not hold retire

    last = await drive(client, created["id"], len(HAPPY_PATH))
    assert (last["state"], last["currentState"]) == ("performed", "performed")
    assert last["availableTransitions"] == []

    events = await state_events(db, created["id"])
    assert [(e["from"], e["to"], e["action"]) for e in events] == [
        (before, after, action) for action, _, before, after in HAPPY_PATH
    ]
    assert {e["assetId"] for e in events} == {str(setup.asset_id)}

    history = await client.get(f"{INSPECTIONS}/{created['id']}/history", headers=VIEWER)
    assert history.status_code == 200, history.text
    found = history.json()
    assert found["chainValid"] is True
    assert [e["action"] for e in found["entries"]] == [a for a, _, _, _ in HAPPY_PATH]
    assert found["entries"][-1]["authStrength"] == "mfa"


async def test_mark_performed_on_an_aal1_session_needs_a_step_up(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    created = await create(client, setup)
    await drive(client, created["id"], 3)
    before = await count(db, "SELECT count(*) FROM domain_events")
    response = await act(client, created["id"], "mark_performed", SUPERVISOR)  # aal 1
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    found = await client.get(f"{INSPECTIONS}/{created['id']}", headers=VIEWER)
    assert (found.json()["state"], found.json()["currentState"]) == (
        "supervisor_review",
        "supervisor_review",
    )
    assert await count(db, "SELECT count(*) FROM domain_events") == before


async def test_refused_transitions_pass_through_from_approvals(
    client: httpx.AsyncClient, setup: Setup
) -> None:
    created = await create(client, setup)
    await drive(client, created["id"], 2)  # in_progress
    early = await act(client, created["id"], "mark_performed", signed(SUPERVISOR_ID))
    assert early.status_code == 409 and early.json()["code"] == "INVALID_TRANSITION"
    await drive_from(client, created["id"], 2)
    denied = await act(client, created["id"], "mark_performed", signed(INSPECTOR_ID))
    assert denied.status_code == 403, denied.text
    rework = await act(client, created["id"], "request_rework", signed(SUPERVISOR_ID))
    assert rework.status_code == 422 and rework.json()["code"] == "COMMENT_REQUIRED"
    stale = await act(
        client,
        created["id"],
        "request_rework",
        signed(SUPERVISOR_ID),
        comment="x",
        expectedSyncVersion=1,
    )
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    unknown = await act(client, str(uuid.uuid4()), "ready", signed(SUPERVISOR_ID))
    assert unknown.status_code == 404


async def drive_from(client: httpx.AsyncClient, inspection_id: str, done: int) -> None:
    """Take the happy path's remaining steps up to supervisor review."""
    for action, user, _, _ in HAPPY_PATH[done:3]:
        response = await act(client, inspection_id, action, signed(user))
        assert response.status_code == 200, (action, response.text)


async def test_a_transition_through_approvals_is_followed_once_by_the_subscriber(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup, outbox: Outbox
) -> None:
    created = await create(client, setup)
    instance_id = created["workflowInstanceId"]
    response = await client.post(
        f"/api/v1/approvals/instances/{instance_id}/transition",
        json={"action": "ready_unassigned"},
        headers=signed(SUPERVISOR_ID),
    )
    assert response.status_code == 200, response.text
    assert await state_events(db, created["id"]) == []

    await dispatch_all(outbox)
    found = await client.get(f"{INSPECTIONS}/{created['id']}", headers=VIEWER)
    assert found.json()["state"] == "assignable"
    events = await state_events(db, created["id"])
    assert [(e["from"], e["to"], e["action"]) for e in events] == [
        ("draft", "assignable", "ready_unassigned")
    ]

    # Delivering the same workflow event again changes nothing.
    rows = await su_fetch(
        db,
        "SELECT id, tenant_id, project_id, asset_id, event_name, event_version, aggregate_type,"
        " aggregate_id, payload, actor_id, occurred_at, attempts FROM domain_events"
        " WHERE event_name = 'workflow.transitioned'",
    )
    (row,) = rows
    values = dict(zip(DomainEvent.__dataclass_fields__, row, strict=True))
    if isinstance(values["payload"], str):
        values["payload"] = json.loads(values["payload"])
    replay = DomainEvent(**values)
    context = RequestContext(tenant_id=TENANT_A_ID, request_id="replay", actor_id=replay.actor_id)
    with use_context(context):
        async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
            await follow_workflow(conn, replay)
    assert len(await state_events(db, created["id"])) == 1

    # A transition through this module's route emitted its own event; the subscriber adds none.
    assigned = await act(client, created["id"], "assign_to_me", signed(INSPECTOR_ID))
    assert assigned.status_code == 200, assigned.text
    await dispatch_all(outbox)
    assert [e["to"] for e in await state_events(db, created["id"])] == ["assignable", "assigned"]


async def test_approvals_binds_an_inspection_only_to_its_own_project(
    client: httpx.AsyncClient, setup: Setup
) -> None:
    created = await create(client, setup)
    url = "/api/v1/approvals/instances"
    mismatch = await client.post(
        url,
        json={"recordType": "inspection", "recordId": created["id"], "projectId": str(KF_02)},
        headers=ALICE,
    )
    assert mismatch.status_code == 422 and mismatch.json()["code"] == "PROJECT_MISMATCH"
    same = await client.post(
        url, json={"recordType": "inspection", "recordId": created["id"]}, headers=ALICE
    )
    assert same.status_code == 201, same.text
    assert same.json()["id"] == created["workflowInstanceId"]
    missing = await client.post(
        url, json={"recordType": "inspection", "recordId": str(uuid.uuid4())}, headers=ALICE
    )
    assert missing.status_code == 404


# --- re-inspection --------------------------------------------------------------------------------


async def test_reinspect_creates_a_new_draft_on_the_current_revision(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    created = await create(client, setup)
    early = await client.post(f"{INSPECTIONS}/{created['id']}/reinspect", headers=SUPERVISOR)
    assert early.status_code == 409, early.text
    assert early.json() == {"code": "NOT_COMPLETED", "messageKey": "inspection.error.not_completed"}

    await drive(client, created["id"], len(HAPPY_PATH))
    revision_2 = await new_revision(client, setup.template_id)
    denied = await client.post(f"{INSPECTIONS}/{created['id']}/reinspect", headers=INSPECTOR)
    assert denied.status_code == 403
    response = await client.post(f"{INSPECTIONS}/{created['id']}/reinspect", headers=SUPERVISOR)
    assert response.status_code == 201, response.text
    again = response.json()
    assert again["id"] != created["id"]
    assert (again["source"], again["sourceRefId"], again["state"]) == (
        "reinspection",
        created["id"],
        "draft",
    )
    assert again["templateRevisionId"] == str(revision_2)
    assert (again["assetId"], again["projectId"], again["kind"]) == (
        created["assetId"],
        created["projectId"],
        created["kind"],
    )
    original = await client.get(f"{INSPECTIONS}/{created['id']}", headers=VIEWER)
    assert original.json()["state"] == "performed"  # superseding it is INSPECTIONS-09


# --- reads ----------------------------------------------------------------------------------------


async def test_the_list_filters_and_pages(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    other_asset = await create_asset(db, "TK-102")
    ids = [(await create(client, setup))["id"] for _ in range(3)]
    other = await create(client, setup, assetId=str(other_asset), projectId=str(KF_02), kind="itp")
    await drive(client, ids[0], 1)

    async def items(**params: Any) -> list[str]:
        response = await client.get(INSPECTIONS, params=params, headers=VIEWER)
        assert response.status_code == 200, response.text
        return [i["id"] for i in response.json()["items"]]

    assert await items() == [other["id"], *reversed(ids)]
    assert await items(assetId=str(other_asset)) == [other["id"]]
    assert await items(projectId=str(KF_01)) == list(reversed(ids))
    assert await items(state="assigned") == [ids[0]]
    assert await items(kind="itp") == [other["id"]]

    page = (await client.get(INSPECTIONS, params={"limit": 3}, headers=VIEWER)).json()
    assert len(page["items"]) == 3 and page["nextCursor"]
    rest = await client.get(
        INSPECTIONS, params={"limit": 3, "cursor": page["nextCursor"]}, headers=VIEWER
    )
    assert [i["id"] for i in rest.json()["items"]] == [ids[0]]
    assert rest.json()["nextCursor"] is None
    bad = await client.get(INSPECTIONS, params={"cursor": "not-a-cursor"}, headers=VIEWER)
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_CURSOR"


async def test_a_project_scoped_viewer_sees_only_their_projects(
    client: httpx.AsyncClient, setup: Setup, app: FastAPI, grants: GrantTable
) -> None:
    in_one = await create(client, setup)
    in_two = await create(client, setup, projectId=str(KF_02))
    tenant_wide = {k: v for k, v in body(setup).items() if k != "projectId"}
    no_project = await client.post(INSPECTIONS, json=tenant_wide, headers=SUPERVISOR)
    assert no_project.status_code == 201, no_project.text

    class ProjectGrants:
        async def grants(self, principal: AccessPrincipal) -> list[Grant]:
            if principal.actor_id != VIEWER_ID:
                return []
            return [Grant("inspection.view", ProjectScope(KF_02))]

    app.state.access_policy.register(ProjectGrants())
    grants.by_user[VIEWER_ID] = {"approvals.view"}  # no tenant-wide inspection.view any more

    listed = await client.get(INSPECTIONS, headers=VIEWER)
    assert [i["id"] for i in listed.json()["items"]] == [in_two["id"]]
    assert (await client.get(f"{INSPECTIONS}/{in_two['id']}", headers=VIEWER)).status_code == 200
    hidden = await client.get(f"{INSPECTIONS}/{in_one['id']}", headers=VIEWER)
    assert hidden.status_code == 403


# --- isolation ------------------------------------------------------------------------------------


async def test_another_tenant_sees_nothing(client: httpx.AsyncClient, setup: Setup) -> None:
    created = await create(client, setup)
    for path in ("", "/history"):
        response = await client.get(f"{INSPECTIONS}/{created['id']}{path}", headers=BOB)
        assert response.status_code == 404, (path, response.text)
    listed = await client.get(INSPECTIONS, headers=BOB)
    assert listed.status_code == 200 and listed.json()["items"] == []
    moved = await act(client, created["id"], "ready", signed(BOB_ID, TENANT_B_ID))
    assert moved.status_code == 404
    again = await client.post(f"{INSPECTIONS}/{created['id']}/reinspect", headers=BOB)
    assert again.status_code == 404


async def test_rls_fails_closed_without_a_tenant(
    client: httpx.AsyncClient, db: TenantDb, setup: Setup
) -> None:
    await create(client, setup)
    async with db.no_tenant() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM inspections"))).scalar_one() == 0
    with pytest.raises(DBAPIError) as caught:
        async with db.no_tenant() as conn:
            await conn.execute(
                text(
                    "INSERT INTO inspections (id, tenant_id, asset_id, template_id,"
                    " template_revision_id, kind, source, workflow_instance_id, state, created_by)"
                    " VALUES (gen_random_uuid(), :t, gen_random_uuid(), gen_random_uuid(),"
                    " gen_random_uuid(), 'inspection', 'manual', gen_random_uuid(), 'draft',"
                    " gen_random_uuid())"
                ),
                {"t": TENANT_A_ID},
            )
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"
    with pytest.raises(DBAPIError) as denied:
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text("DELETE FROM inspections"))
    assert getattr(denied.value.orig, "sqlstate", None) == "42501"
