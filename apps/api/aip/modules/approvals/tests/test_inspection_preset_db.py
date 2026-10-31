"""APPROVALS-05/09: the inspection presets through the real app and ``TransitionService`` on Postgres.

Every golden case runs here as it does through the evaluator in ``test_inspection_golden.py``.
The inspections module (INSPECTIONS-01) does not exist yet, so a test resolver stands in for the
``inspection`` record type, and the fixture grant table plays the roles: supervisor (assign,
approve), inspector (execute), quality manager (retire) and client reviewer (client_approve).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.approvals.api import (
    ApprovalsApi,
    RecordRef,
    register_record_resolver,
    unregister_record_resolver,
)
from aip.modules.approvals.seeds import SeedRefusedError, seed
from aip.modules.approvals.tests.conftest import (
    BOB,
    CAROL,
    GrantTable,
    act,
    ctx,
    history,
    principal_headers,
    signed,
    su_fetch,
)
from aip.modules.approvals.tests.test_inspection_golden import (
    INSPECTION_PERMISSIONS,
    PRESET_FOR,
    golden_cases,
    path_to,
)
from aip.platform.context import use_context

api = ApprovalsApi()

SUPERVISOR_ID = UUID("00000000-0000-4000-8000-0000000005e1")
INSPECTOR_ID = UUID("00000000-0000-4000-8000-0000000005e2")
QUALITY_ID = UUID("00000000-0000-4000-8000-0000000005e3")
CLIENT_ID = UUID("00000000-0000-4000-8000-0000000005e4")
RT_01 = UUID("00000000-0000-4000-8000-00000000a701")  # a project with client review
KF_01 = UUID("00000000-0000-4000-8000-00000000af01")  # a project without

BASE = {"approvals.view", "approvals.start"}


def fresh(user: UUID) -> dict[str, str]:
    """A fresh aal2 session: passes the default sign-off policy for the critical transitions."""
    return signed(TENANT_A_ID, user)


class Inspections:
    """The test stand-in for the inspections module: which project each inspection is in."""

    def __init__(self) -> None:
        self.projects: dict[UUID, UUID | None] = {}

    async def __call__(self, conn: object, record_id: UUID) -> RecordRef | None:
        return RecordRef(project_id=self.projects.get(record_id))


@pytest.fixture(autouse=True)
def inspections() -> Iterator[Inspections]:
    records = Inspections()
    register_record_resolver("inspection", records)  # pyright: ignore[reportArgumentType]
    try:
        yield records
    finally:
        unregister_record_resolver("inspection")


@pytest.fixture(autouse=True)
def roles(grants: GrantTable) -> GrantTable:
    grants.by_user[ALICE_ID] = {*BASE, *INSPECTION_PERMISSIONS, "approvals.design"}
    grants.by_user[SUPERVISOR_ID] = {
        *BASE,
        "approvals.inspection.assign",
        "approvals.inspection.approve",
    }
    grants.by_user[INSPECTOR_ID] = {*BASE, "approvals.inspection.execute"}
    grants.by_user[QUALITY_ID] = {*BASE, "approvals.inspection.retire"}
    grants.by_user[CLIENT_ID] = {*BASE, "approvals.inspection.client_approve"}
    return grants


async def install(db: TenantDb, preset_key: str, project_id: UUID | None = None) -> Any:
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            return await api.install_preset(conn, preset_key, project_id=project_id)


async def new_inspection(
    client: httpx.AsyncClient, inspections: Inspections, project_id: UUID | None = None
) -> dict[str, Any]:
    record_id = uuid.uuid4()
    inspections.projects[record_id] = project_id
    body = {"recordType": "inspection", "recordId": str(record_id)}
    response = await client.post("/api/v1/approvals/instances", json=body, headers=fresh(ALICE_ID))
    assert response.status_code == 201, response.text
    return response.json()


async def drive(
    client: httpx.AsyncClient, instance_id: str, actions: list[str], headers: dict[str, str]
) -> dict[str, Any]:
    """Take each action (with a comment, which some need); return the last instance."""
    body: dict[str, Any] = {}
    for action in actions:
        response = await act(client, instance_id, action, headers, comment="golden")
        assert response.status_code == 200, (action, response.text)
        body = response.json()["instance"]
    return body


# --- the golden cases through TransitionService ----------------------------------------------


@pytest.mark.parametrize("case", golden_cases())
async def test_golden_case_through_the_transition_service(
    case: dict[str, Any], client: httpx.AsyncClient, db: TenantDb, inspections: Inspections
) -> None:
    await install(db, "inspection_standard")
    project = None
    if case["variant"] == "client_review":
        project = RT_01
        await install(db, "inspection_client_review", RT_01)
    instance = await new_inspection(client, inspections, project)
    assert instance["definitionKey"] == PRESET_FOR[case["variant"]]
    headers = fresh(ALICE_ID)
    current = await drive(client, instance["id"], path_to(case["variant"], case["start"]), headers)
    state = current.get("currentState", instance["currentState"])
    assert state == case["start"]

    expect = case["expect"]
    comment = {"comment": "golden"} if case.get("comment", True) else {}
    outcome: dict[str, Any]
    for action in case["actions"]:
        response = await act(client, instance["id"], action, headers, **comment)
        if response.status_code != 200:
            assert response.status_code in (409, 422), response.text
            outcome = {"error": response.json()["code"]}
            break
        state = response.json()["instance"]["currentState"]
    else:
        if "available" in expect:
            url = f"/api/v1/approvals/instances/{instance['id']}"
            view = await client.get(url, headers=headers)
            outcome = {"available": [t["action"] for t in view.json()["availableTransitions"]]}
        else:
            outcome = {"state": state}
    assert outcome == expect


# --- roles, sign-off and comments -------------------------------------------------------------


async def test_standard_happy_path_by_role_writes_a_valid_four_entry_chain(
    client: httpx.AsyncClient, db: TenantDb, inspections: Inspections
) -> None:
    await install(db, "inspection_standard")
    instance = await new_inspection(client, inspections)
    assert instance["currentState"] == "draft"
    steps = [
        ("ready", SUPERVISOR_ID),
        ("inspect", INSPECTOR_ID),
        ("request_supervisor_review", INSPECTOR_ID),
        ("mark_performed", SUPERVISOR_ID),
    ]
    last: dict[str, Any] = {}
    for action, user in steps:
        response = await act(client, instance["id"], action, fresh(user))
        assert response.status_code == 200, (action, response.text)
        last = response.json()["instance"]
    assert last["currentState"] == "performed"
    assert last["availableTransitions"] == []

    found = await history(client, instance["id"], fresh(ALICE_ID))
    assert found["chainValid"] is True
    assert [e["action"] for e in found["entries"]] == [action for action, _ in steps]
    assert found["entries"][-1]["authStrength"] == "mfa"


async def test_the_inspector_cannot_mark_performed(
    client: httpx.AsyncClient, db: TenantDb, inspections: Inspections
) -> None:
    await install(db, "inspection_standard")
    instance = await new_inspection(client, inspections)
    await drive(client, instance["id"], path_to("standard", "supervisor_review"), fresh(ALICE_ID))
    response = await act(client, instance["id"], "mark_performed", fresh(INSPECTOR_ID))
    assert response.status_code == 403


async def test_only_the_retire_permission_retires(
    client: httpx.AsyncClient, db: TenantDb, inspections: Inspections
) -> None:
    await install(db, "inspection_standard")
    instance = await new_inspection(client, inspections)
    await drive(client, instance["id"], path_to("standard", "supervisor_review"), fresh(ALICE_ID))
    for user in (SUPERVISOR_ID, INSPECTOR_ID):
        refused = await act(client, instance["id"], "retire", fresh(user), comment="duplicate")
        assert refused.status_code == 403, refused.text
    retired = await act(client, instance["id"], "retire", fresh(QUALITY_ID), comment="duplicate")
    assert retired.status_code == 200, retired.text
    assert retired.json()["instance"]["currentState"] == "retired"


async def test_mark_performed_with_a_stale_session_needs_a_step_up(
    client: httpx.AsyncClient, db: TenantDb, inspections: Inspections
) -> None:
    await install(db, "inspection_standard")
    instance = await new_inspection(client, inspections)
    path = path_to("standard", "supervisor_review")
    await drive(client, instance["id"], path, fresh(ALICE_ID))
    stale = principal_headers(
        TENANT_A_ID,
        SUPERVISOR_ID,
        aal=2,
        amr=["pwd", "otp"],
        authenticated_at=datetime.now(UTC) - timedelta(hours=1),
    )
    response = await act(client, instance["id"], "mark_performed", stale)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    found = await history(client, instance["id"], fresh(ALICE_ID))
    assert len(found["entries"]) == len(path)  # mark_performed wrote nothing


async def test_request_rework_needs_a_comment(
    client: httpx.AsyncClient, db: TenantDb, inspections: Inspections
) -> None:
    await install(db, "inspection_standard")
    instance = await new_inspection(client, inspections)
    path = path_to("standard", "supervisor_review")
    await drive(client, instance["id"], path, fresh(ALICE_ID))
    view = await client.get(f"/api/v1/approvals/instances/{instance['id']}", headers=CAROL)
    by_action = {t["action"]: t for t in view.json()["availableTransitions"]}
    assert by_action["request_rework"]["requiresComment"] is True
    assert by_action["mark_performed"]["requiresComment"] is False

    for body in ({}, {"comment": "   "}):
        response = await act(client, instance["id"], "request_rework", fresh(SUPERVISOR_ID), **body)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "COMMENT_REQUIRED"
    assert len((await history(client, instance["id"], fresh(ALICE_ID)))["entries"]) == len(path)

    response = await act(
        client, instance["id"], "request_rework", fresh(SUPERVISOR_ID), comment="DFT low"
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"]["comment"] == "DFT low"
    assert response.json()["instance"]["currentState"] == "rework_required"


async def test_client_review_applies_only_to_its_project(
    client: httpx.AsyncClient, db: TenantDb, inspections: Inspections
) -> None:
    await install(db, "inspection_standard")
    await install(db, "inspection_client_review", RT_01)
    with_client = await new_inspection(client, inspections, RT_01)
    without = await new_inspection(client, inspections, KF_01)
    path = path_to("standard", "supervisor_review")

    await drive(client, with_client["id"], path, fresh(ALICE_ID))
    after = await act(client, with_client["id"], "mark_performed", fresh(SUPERVISOR_ID))
    assert after.status_code == 200, after.text
    assert after.json()["instance"]["currentState"] == "client_review"
    done = await act(client, with_client["id"], "client_approve", fresh(CLIENT_ID))
    assert done.status_code == 200, done.text
    assert done.json()["instance"]["currentState"] == "performed"

    await drive(client, without["id"], path, fresh(ALICE_ID))
    after = await act(client, without["id"], "mark_performed", fresh(SUPERVISOR_ID))
    assert after.status_code == 200, after.text
    assert after.json()["instance"]["currentState"] == "performed"


async def test_v2_publishes_over_an_installed_v1_and_retires_it(
    client: httpx.AsyncClient,
    db: TenantDb,
    inspections: Inspections,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A v1-shaped inspection_standard (APPROVALS-05 codes) is already installed in the tenant.
    v1_dir = tmp_path / "workflows"
    v1_dir.mkdir()
    v1 = {
        "key": "inspection_standard",
        "recordType": "inspection",
        "spec": {
            "states": [
                {"code": "draft", "labelKey": "workflow.inspection.state.draft"},
                {"code": "completed", "labelKey": "workflow.inspection.state.performed"},
            ],
            "initial": "draft",
            "transitions": [
                {
                    "action": "approve",
                    "from": "draft",
                    "to": "completed",
                    "requiredPermission": "approvals.inspection.approve",
                    "labelKey": "workflow.inspection.action.mark_performed",
                }
            ],
        },
    }
    (v1_dir / "inspection_standard.json").write_text(json.dumps(v1), encoding="utf-8")
    monkeypatch.setenv("AIP_WORKFLOWS_DIR", str(v1_dir))
    first = await install(db, "inspection_standard")
    monkeypatch.delenv("AIP_WORKFLOWS_DIR")

    second = await install(db, "inspection_standard")
    assert (first.version, second.version, second.status) == (1, 2, "active")
    rows = await su_fetch(
        db,
        "SELECT version, status FROM workflow_definitions"
        " WHERE tenant_id = $1 AND key = $2 ORDER BY version",
        TENANT_A_ID,
        "inspection_standard",
    )
    assert [tuple(r) for r in rows] == [(1, "retired"), (2, "active")]
    instance = await new_inspection(client, inspections)
    assert (instance["definitionId"], instance["version"]) == (str(second.id), 2)
    assert "ready_unassigned" in [t["action"] for t in instance["availableTransitions"]]


async def test_installing_twice_leaves_one_active_version(db: TenantDb) -> None:
    first = await install(db, "inspection_standard")
    second = await install(db, "inspection_standard")
    assert (second.id, second.version) == (first.id, 1)
    rows = await su_fetch(
        db,
        "SELECT version, status FROM workflow_definitions WHERE tenant_id = $1 AND key = $2",
        TENANT_A_ID,
        "inspection_standard",
    )
    assert [tuple(r) for r in rows] == [(1, "active")]


# --- the preset routes --------------------------------------------------------------------------


async def test_the_presets_route_lists_both_presets(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/approvals/presets", headers=CAROL)
    assert response.status_code == 200, response.text
    by_key = {p["key"]: p for p in response.json()}
    assert set(PRESET_FOR.values()) <= set(by_key)
    standard = by_key["inspection_standard"]
    assert standard["recordType"] == "inspection"
    assert standard["initial"] == "draft"
    assert "client_review" not in standard["states"]
    assert "client_approve" in by_key["inspection_client_review"]["actions"]


async def test_install_from_preset_route(
    client: httpx.AsyncClient, inspections: Inspections
) -> None:
    body = {"presetKey": "inspection_standard"}
    response = await client.post(
        "/api/v1/approvals/definitions/from-preset", json=body, headers=fresh(ALICE_ID)
    )
    assert response.status_code == 200, response.text
    installed = response.json()
    assert installed["key"] == "inspection_standard"
    assert (installed["version"], installed["status"]) == (1, "active")
    assert installed["projectId"] is None

    again = await client.post(
        "/api/v1/approvals/definitions/from-preset", json=body, headers=fresh(ALICE_ID)
    )
    assert again.json()["id"] == installed["id"]

    instance = await new_inspection(client, inspections)
    assert instance["currentState"] == "draft"
    assert instance["availableTransitions"][0]["labelKey"] == "workflow.inspection.action.ready"

    scoped = await client.post(
        "/api/v1/approvals/definitions/from-preset",
        json={"presetKey": "inspection_client_review", "projectId": str(RT_01)},
        headers=fresh(ALICE_ID),
    )
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["projectId"] == str(RT_01)


async def test_install_from_preset_needs_design_and_a_known_preset(
    client: httpx.AsyncClient,
) -> None:
    path = "/api/v1/approvals/definitions/from-preset"
    denied = await client.post(path, json={"presetKey": "inspection_standard"}, headers=CAROL)
    assert denied.status_code == 403
    missing = await client.post(path, json={"presetKey": "no_such_preset"}, headers=fresh(ALICE_ID))
    assert missing.status_code == 404
    assert missing.json()["code"] == "PRESET_NOT_FOUND"
    # Another tenant's install is its own: tenant B still has no inspection definition.
    response = await client.post(
        "/api/v1/approvals/instances",
        json={"recordType": "inspection", "recordId": str(uuid.uuid4())},
        headers=BOB,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "NO_ACTIVE_DEFINITION"


# --- the seed ------------------------------------------------------------------------------------


async def test_the_seed_installs_the_standard_preset_in_kaefer_demo_only(
    db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", db.db.app_url)
    from aip.platform.db.engine import dispose_engine

    await dispose_engine()
    try:
        first, _demo = await seed(env="test")
        second, _ = await seed(env="test")
    finally:
        await dispose_engine()
    assert (first.key, first.version, first.status) == ("inspection_standard", 1, "active")
    assert second.id == first.id
    counts = await su_fetch(
        db,
        "SELECT tenant_id, count(*) FROM workflow_definitions WHERE key = $1 GROUP BY tenant_id",
        "inspection_standard",
    )
    assert [tuple(r) for r in counts] == [(TENANT_A_ID, 1)]
    assert TENANT_B_ID not in {r[0] for r in counts}


async def test_the_seed_refuses_in_production() -> None:
    with pytest.raises(SeedRefusedError):
        await seed(env="production")
