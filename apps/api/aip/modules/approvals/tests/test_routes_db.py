"""APPROVALS-04: approval routes through the real app on Postgres as ``aip_app``.

Users, projects, the ``qa`` role and the ``Client`` team are real rows (seeded as the superuser),
so role and team approvers resolve through the access module at decision time. Permissions come
from the test grant table. The ``demo`` workflow's ``approve`` is critical, so a route's last
approval is made by a stepped-up (aal 2) approver.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.approvals.api import ApprovalsApi
from aip.modules.approvals.tests.conftest import (
    ALICE,
    BOB,
    CAROL,
    SUBMITTER,
    DemoRecords,
    GrantTable,
    act,
    history,
    principal_headers,
    signed,
    su_execute,
    su_fetch,
)
from aip.modules.approvals.transition import Actor
from aip.modules.identity.api import SessionFacts
from aip.platform.access import AccessPrincipal

pytestmark = pytest.mark.usefixtures("demo", "people")

U1 = UUID("00000000-0000-4000-8000-0000000a0401")  # serial approver 1
U2 = UUID("00000000-0000-4000-8000-0000000a0402")  # serial approver 2
U3 = UUID("00000000-0000-4000-8000-0000000a0403")  # the submitter
Q1 = UUID("00000000-0000-4000-8000-0000000a0411")  # holds qa on P1
Q2 = UUID("00000000-0000-4000-8000-0000000a0412")  # holds qa on P2 only
C1 = UUID("00000000-0000-4000-8000-0000000a0421")  # Client team member
C2 = UUID("00000000-0000-4000-8000-0000000a0422")  # Client team member
P1 = UUID("00000000-0000-4000-8000-0000000a04f1")
P2 = UUID("00000000-0000-4000-8000-0000000a04f2")
QA_ROLE = UUID("00000000-0000-4000-8000-0000000a04e1")
CLIENT_TEAM = UUID("00000000-0000-4000-8000-0000000a04c1")

APPROVER = {"approvals.view", "approvals.approve"}
ROUTES = "/api/v1/approvals"


def _seed_sql() -> str:
    users = {U1: "u1", U2: "u2", U3: "u3", Q1: "q1", Q2: "q2", C1: "c1", C2: "c2"}
    rows = ", ".join(
        f"('{uid}', '{TENANT_A_ID}', 'staff', '{name}@kaefer.test', '{name}', 'active')"
        for uid, name in users.items()
    )
    return (
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
        f"{rows};"
        "INSERT INTO projects (id, tenant_id, code, name, status) VALUES "
        f"('{P1}', '{TENANT_A_ID}', 'P1', 'Project 1', 'active'), "
        f"('{P2}', '{TENANT_A_ID}', 'P2', 'Project 2', 'active');"
        "INSERT INTO role (id, tenant_id, code, name) VALUES "
        f"('{QA_ROLE}', '{TENANT_A_ID}', 'qa', 'QA');"
        "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type, project_id)"
        f" VALUES (gen_random_uuid(), '{TENANT_A_ID}', '{Q1}', '{QA_ROLE}', 'project', '{P1}'),"
        f" (gen_random_uuid(), '{TENANT_A_ID}', '{Q2}', '{QA_ROLE}', 'project', '{P2}');"
        "INSERT INTO team (id, tenant_id, name, team_type) VALUES "
        f"('{CLIENT_TEAM}', '{TENANT_A_ID}', 'Client', 'client');"
        "INSERT INTO team_member (id, tenant_id, team_id, user_id) VALUES "
        f"(gen_random_uuid(), '{TENANT_A_ID}', '{CLIENT_TEAM}', '{C1}'), "
        f"(gen_random_uuid(), '{TENANT_A_ID}', '{CLIENT_TEAM}', '{C2}')"
    )


@pytest.fixture
async def people(db: TenantDb, grants: GrantTable) -> None:
    await su_execute(db, _seed_sql())
    for user in (U1, U2, Q1, Q2, C1, C2):
        grants.by_user[user] = set(APPROVER)
    grants.by_user[U3] = {*SUBMITTER, *APPROVER}
    grants.by_user[ALICE_ID] |= {"approvals.design", "access.team.manage"}
    grants.by_user[BOB_ID] |= {*APPROVER, "approvals.design"}


def as_(user: UUID) -> dict[str, str]:
    """A fresh aal 2 session in tenant A (passes the critical ``approve``)."""
    return signed(TENANT_A_ID, user)


def step(user: UUID) -> dict[str, Any]:
    return {"stepOrder": 1, "approverType": "user", "approverRef": str(user)}


async def create_template(
    client: httpx.AsyncClient,
    steps: list[dict[str, Any]],
    *,
    headers: dict[str, str] | None = None,
    expect: int = 201,
    **extra: Any,
) -> dict[str, Any]:
    body = {
        "name": f"route {uuid4().hex[:8]}",
        "recordType": "demo",
        "onApprovedAction": "approve",
        "onRejectedAction": "reject",
        "steps": steps,
        **extra,
    }
    response = await client.post(f"{ROUTES}/route-templates", json=body, headers=headers or ALICE)
    assert response.status_code == expect, response.text
    return response.json()


async def submitted(
    client: httpx.AsyncClient, records: DemoRecords, project: UUID | None = P1
) -> dict[str, Any]:
    """A ``demo`` instance on ``project``, started and submitted by U3."""
    record_id = uuid4()
    records.projects[record_id] = project
    body = {"recordType": "demo", "recordId": str(record_id)}
    response = await client.post(f"{ROUTES}/instances", json=body, headers=as_(U3))
    assert response.status_code == 201, response.text
    instance = response.json()
    assert (await act(client, instance["id"], "submit", as_(U3))).status_code == 200
    return instance


async def start_route(
    client: httpx.AsyncClient,
    instance_id: str,
    template_id: str,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.post(
        f"{ROUTES}/instances/{instance_id}/route",
        json={"routeTemplateId": template_id},
        headers=headers or as_(U3),
    )


async def decide(
    client: httpx.AsyncClient,
    instance_id: str,
    step_id: str,
    decision: str,
    headers: dict[str, str],
    comment: str | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"stepId": step_id, "decision": decision}
    if comment is not None:
        body["comment"] = comment
    return await client.post(f"{ROUTES}/instances/{instance_id}/decide", json=body, headers=headers)


async def get_steps(client: httpx.AsyncClient, instance_id: str) -> dict[str, Any]:
    response = await client.get(f"{ROUTES}/instances/{instance_id}/steps", headers=as_(U3))
    assert response.status_code == 200, response.text
    return response.json()


async def events(db: TenantDb, instance_id: str, name: str) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT payload FROM domain_events WHERE event_name = $1 AND aggregate_id = $2"
        " ORDER BY occurred_at, id",
        name,
        UUID(instance_id),
    )
    return [json.loads(p) if isinstance(p, str) else p for (p,) in rows]


async def started(
    client: httpx.AsyncClient, records: DemoRecords, steps: list[dict[str, Any]], **extra: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A submitted instance with a route from a new template; returns (instance, route)."""
    template = await create_template(client, steps, **extra)
    instance = await submitted(client, records)
    response = await start_route(client, instance["id"], template["id"])
    assert response.status_code == 201, response.text
    return instance, response.json()


async def test_a_serial_route_takes_each_approver_in_turn(
    client: httpx.AsyncClient, db: TenantDb, demo_records: DemoRecords
) -> None:
    instance, route = await started(
        client, demo_records, [step(U1), {**step(U2), "stepOrder": 2, "dueHours": 24}]
    )
    first, second = route["steps"]
    assert (first["status"], second["status"]) == ("pending", "waiting")
    assert route["currentStepId"] == first["id"] and route["routeRound"] == 1
    requested = await events(db, instance["id"], "approval.requested")
    assert [e["approverRef"] for e in requested] == [str(U1)]

    early = await decide(client, instance["id"], second["id"], "approve", as_(U2))
    assert early.status_code == 403 and early.json()["code"] == "NOT_CURRENT_APPROVER"

    response = await decide(client, instance["id"], first["id"], "approve", as_(U1))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] is None
    assert [s["status"] for s in body["route"]["steps"]] == ["approved", "pending"]
    assert body["route"]["currentStepId"] == second["id"]
    assert body["route"]["instance"]["currentState"] == "submitted"
    assert body["decision"]["action"] == "approve_step"
    requested = await events(db, instance["id"], "approval.requested")
    assert [e["approverRef"] for e in requested] == [str(U1), str(U2)]
    assert requested[1]["dueAt"] is not None

    response = await decide(client, instance["id"], second["id"], "approve", as_(U2))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "approved"
    assert body["route"]["instance"]["currentState"] == "approved"
    assert body["route"]["currentStepId"] is None
    assert body["decision"]["action"] == "approve"
    assert body["decision"]["fromState"] == "submitted"
    assert len(await events(db, instance["id"], "approval.approved")) == 1
    [completed] = await events(db, instance["id"], "approval.completed")
    assert completed == {
        "instanceId": instance["id"],
        "recordType": "demo",
        "recordId": instance["recordId"],
        "outcome": "approved",
    }
    assert len(await events(db, instance["id"], "approval.rejected")) == 0
    assert len(await events(db, instance["id"], "workflow.transitioned")) == 2

    steps = await get_steps(client, instance["id"])
    assert [s["status"] for s in steps["steps"]] == ["approved", "approved"]
    assert [s["decidedBy"] for s in steps["steps"]] == [str(U1), str(U2)]

    log = await history(client, instance["id"], as_(U3))
    assert [e["action"] for e in log["entries"]] == ["submit", "approve_step", "approve"]
    assert log["chainValid"] is True

    again = await decide(client, instance["id"], second["id"], "approve", as_(U2))
    assert again.status_code == 409 and again.json()["code"] == "STEP_NOT_PENDING"


async def test_one_rejection_in_a_parallel_group_ends_the_route(
    client: httpx.AsyncClient, db: TenantDb, demo_records: DemoRecords
) -> None:
    group = [
        {"stepOrder": 1, "mode": "parallel", "approverType": "role", "approverRef": str(QA_ROLE)},
        {
            "stepOrder": 1,
            "mode": "parallel",
            "approverType": "team",
            "approverRef": str(CLIENT_TEAM),
        },
    ]
    instance, route = await started(client, demo_records, group)
    qa, client_step = route["steps"]
    assert {qa["status"], client_step["status"]} == {"pending"}
    assert len(await events(db, instance["id"], "approval.requested")) == 2

    blank = await decide(client, instance["id"], client_step["id"], "reject", as_(C1), "  ")
    assert blank.status_code == 422 and blank.json()["code"] == "COMMENT_REQUIRED"
    missing = await decide(client, instance["id"], client_step["id"], "reject", as_(C1))
    assert missing.status_code == 422

    response = await decide(
        client, instance["id"], client_step["id"], "reject", as_(C1), "paint DFT out of spec"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "rejected"
    assert body["route"]["instance"]["currentState"] == "rejected"
    statuses = {s["id"]: s["status"] for s in body["route"]["steps"]}
    assert statuses == {qa["id"]: "skipped", client_step["id"]: "rejected"}
    assert body["decision"]["comment"] == "paint DFT out of spec"
    [rejected] = await events(db, instance["id"], "approval.rejected")
    assert rejected["stepId"] == client_step["id"] and rejected["actorId"] == str(C1)
    assert rejected["action"] == "reject"
    [completed] = await events(db, instance["id"], "approval.completed")
    assert completed["outcome"] == "rejected"
    assert len(await events(db, instance["id"], "approval.approved")) == 0


async def test_a_parallel_group_needs_every_step(
    client: httpx.AsyncClient, demo_records: DemoRecords
) -> None:
    group = [
        {"stepOrder": 1, "mode": "parallel", "approverType": "role", "approverRef": str(QA_ROLE)},
        {
            "stepOrder": 1,
            "mode": "parallel",
            "approverType": "team",
            "approverRef": str(CLIENT_TEAM),
        },
    ]
    instance, route = await started(client, demo_records, group)
    qa, client_step = route["steps"]
    response = await decide(client, instance["id"], qa["id"], "approve", as_(Q1))
    assert response.status_code == 200, response.text
    assert response.json()["route"]["instance"]["currentState"] == "submitted"
    assert response.json()["route"]["currentStepId"] == client_step["id"]
    response = await decide(client, instance["id"], client_step["id"], "approve", as_(C2))
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "approved"


async def test_roles_resolve_in_the_instance_project_at_decision_time(
    client: httpx.AsyncClient, demo_records: DemoRecords
) -> None:
    role_step = {"stepOrder": 1, "approverType": "role", "approverRef": str(QA_ROLE)}
    instance, route = await started(client, demo_records, [role_step])
    [qa] = route["steps"]
    elsewhere = await decide(client, instance["id"], qa["id"], "approve", as_(Q2))
    assert elsewhere.status_code == 403 and elsewhere.json()["code"] == "NOT_CURRENT_APPROVER"
    outsider = await decide(client, instance["id"], qa["id"], "approve", as_(U1))
    assert outsider.status_code == 403
    response = await decide(client, instance["id"], qa["id"], "approve", as_(Q1))
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "approved"


async def test_a_member_removed_from_the_team_can_no_longer_decide(
    client: httpx.AsyncClient, demo_records: DemoRecords
) -> None:
    team_step = {"stepOrder": 1, "approverType": "team", "approverRef": str(CLIENT_TEAM)}
    instance, route = await started(client, demo_records, [team_step])
    removed = await client.delete(
        f"/api/v1/access/teams/{CLIENT_TEAM}/members/{C1}", headers=signed(TENANT_A_ID, ALICE_ID)
    )
    assert removed.status_code == 204, removed.text
    response = await decide(client, instance["id"], route["steps"][0]["id"], "approve", as_(C1))
    assert response.status_code == 403 and response.json()["code"] == "NOT_CURRENT_APPROVER"


async def test_the_submitter_cannot_approve_their_own_route_by_default(
    client: httpx.AsyncClient, demo_records: DemoRecords
) -> None:
    instance, route = await started(client, demo_records, [step(U3)])
    response = await decide(client, instance["id"], route["steps"][0]["id"], "approve", as_(U3))
    assert response.status_code == 403 and response.json()["code"] == "SELF_APPROVAL_FORBIDDEN"

    instance, route = await started(client, demo_records, [step(U3)], allowSelfApproval=True)
    response = await decide(client, instance["id"], route["steps"][0]["id"], "approve", as_(U3))
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "approved"


async def test_the_last_critical_approval_needs_strong_sign_off_and_writes_nothing_without(
    client: httpx.AsyncClient, db: TenantDb, demo_records: DemoRecords
) -> None:
    instance, route = await started(client, demo_records, [step(U1)])
    aal1 = principal_headers(TENANT_A_ID, U1)
    # Without MFA the sign-off policy falls back to a countersign, which a route never takes.
    response = await decide(client, instance["id"], route["steps"][0]["id"], "approve", aal1)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "COUNTERSIGN_ASSURANCE_REQUIRED"
    # With MFA enrolled the approver is sent to step up instead.
    await su_execute(db, f"UPDATE app_user SET mfa_enrolled_at = now() WHERE id = '{U1}'")
    response = await decide(client, instance["id"], route["steps"][0]["id"], "approve", aal1)
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    steps = await get_steps(client, instance["id"])
    assert steps["steps"][0]["status"] == "pending"
    assert steps["instance"]["currentState"] == "submitted"
    assert await events(db, instance["id"], "approval.completed") == []


async def test_another_tenant_cannot_see_or_decide_a_step(
    client: httpx.AsyncClient, demo_records: DemoRecords
) -> None:
    instance, route = await started(client, demo_records, [step(U1)])
    step_id = route["steps"][0]["id"]
    response = await decide(client, instance["id"], step_id, "approve", BOB)
    assert response.status_code == 404
    response = await client.get(f"{ROUTES}/instances/{instance['id']}/steps", headers=BOB)
    assert response.status_code == 404
    template = route["routeTemplateId"]
    other = await submitted_in_tenant_b(client, demo_records)
    response = await start_route(client, other["id"], template, headers=BOB)
    assert response.status_code == 404


async def submitted_in_tenant_b(client: httpx.AsyncClient, records: DemoRecords) -> dict[str, Any]:
    record_id = uuid4()
    body = {"recordType": "demo", "recordId": str(record_id)}
    response = await client.post(f"{ROUTES}/instances", json=body, headers=BOB)
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_running_route_owns_its_actions_and_other_transitions_cancel_it(
    client: httpx.AsyncClient, demo_records: DemoRecords
) -> None:
    instance, route = await started(client, demo_records, [step(U1)])
    blocked = await act(client, instance["id"], "approve", as_(U3))
    assert blocked.status_code == 409 and blocked.json()["code"] == "ROUTE_PENDING"
    described = await client.get(f"{ROUTES}/instances/{instance['id']}", headers=as_(U3))
    reasons = {t["action"]: t["reasonKey"] for t in described.json()["availableTransitions"]}
    assert reasons == {"approve": "approvals.route.pending", "reject": "approvals.route.pending"}

    # A route that only owns ``approve`` leaves ``reject`` free, and taking it cancels the route.
    instance, route = await started(client, demo_records, [step(U1)], onRejectedAction="approve")
    response = await act(client, instance["id"], "reject", as_(U3))
    assert response.status_code == 200, response.text
    steps = await get_steps(client, instance["id"])
    assert steps["currentStepId"] is None
    assert [s["status"] for s in steps["steps"]] == ["skipped"]
    late = await decide(client, instance["id"], route["steps"][0]["id"], "approve", as_(U1))
    assert late.status_code == 409


async def test_starting_a_route_checks_the_instance_and_template(
    client: httpx.AsyncClient, demo_records: DemoRecords
) -> None:
    template = await create_template(client, [step(U1)])
    record_id = uuid4()
    demo_records.projects[record_id] = P1
    body = {"recordType": "demo", "recordId": str(record_id)}
    draft = (await client.post(f"{ROUTES}/instances", json=body, headers=as_(U3))).json()
    response = await start_route(client, draft["id"], template["id"])
    assert response.status_code == 422 and response.json()["code"] == "ROUTE_ACTION_INVALID"

    instance = await submitted(client, demo_records)
    assert (await start_route(client, instance["id"], str(uuid4()))).status_code == 404
    denied = await start_route(client, instance["id"], template["id"], headers=CAROL)
    assert denied.status_code == 403
    assert (await start_route(client, instance["id"], template["id"])).status_code == 201
    again = await start_route(client, instance["id"], template["id"])
    assert again.status_code == 409 and again.json()["code"] == "ROUTE_ACTIVE"

    other = await create_template(client, [step(U1)], recordType="inspection")
    response = await start_route(client, (await submitted(client, demo_records))["id"], other["id"])
    assert response.status_code == 422 and response.json()["code"] == "ROUTE_TEMPLATE_MISMATCH"


async def test_route_templates_are_validated_and_listed(client: httpx.AsyncClient) -> None:
    serial_pair = [step(U1), step(U2)]
    refused = await create_template(client, serial_pair, expect=422)
    assert refused["code"] == "ROUTE_SHAPE_INVALID"
    unknown_role = [{"stepOrder": 1, "approverType": "role", "approverRef": str(uuid4())}]
    refused = await create_template(client, unknown_role, expect=422)
    assert refused["code"] == "UNKNOWN_APPROVER"
    unknown_team = [{"stepOrder": 1, "approverType": "team", "approverRef": str(uuid4())}]
    assert (await create_template(client, unknown_team, expect=422))["code"] == "UNKNOWN_APPROVER"
    await create_template(client, [], expect=422)
    await create_template(client, [step(U1)], headers=CAROL, expect=403)
    await create_template(client, [{**step(U1), "unknown": 1}], expect=422)

    created = await create_template(
        client, [{**step(U2), "stepOrder": 3}, step(U1)], name="Two step"
    )
    assert [s["approverRef"] for s in created["steps"]] == [str(U1), str(U2)]
    assert all(s["status"] is None for s in created["steps"])
    listed = await client.get(f"{ROUTES}/route-templates", headers=ALICE)
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json() if t["name"] == "Two step"] == [created["id"]]
    other_tenant = await client.get(f"{ROUTES}/route-templates", headers=BOB)
    assert other_tenant.json() == []


async def test_the_inbox_lists_the_steps_an_actor_may_decide_now(
    client: httpx.AsyncClient, db: TenantDb, demo_records: DemoRecords, app: Any
) -> None:
    team_step = {"stepOrder": 1, "approverType": "team", "approverRef": str(CLIENT_TEAM)}
    role_step = {"stepOrder": 2, "approverType": "role", "approverRef": str(QA_ROLE)}
    instance, route = await started(client, demo_records, [team_step, role_step])
    policy = app.state.access_policy

    async def inbox(user: UUID) -> list[str]:
        actor = Actor(
            principal=AccessPrincipal(tenant_id=TENANT_A_ID, actor_id=user),
            session=SessionFacts(aal=1, amr=("fed",), authenticated_at=None),
        )
        async with db.with_tenant(TENANT_A_ID) as conn:
            found = await ApprovalsApi().pending_steps(conn, policy, actor)
        return [str(p.step["id"]) for p in found if str(p.record_id) == instance["recordId"]]

    client_id, qa_id = (s["id"] for s in route["steps"])
    assert await inbox(C1) == [client_id]
    assert await inbox(Q1) == []
    assert await inbox(U3) == []
    response = await decide(client, instance["id"], client_id, "approve", as_(C1))
    assert response.status_code == 200, response.text
    assert await inbox(C1) == []
    assert await inbox(Q1) == [qa_id]
    assert await inbox(Q2) == []
