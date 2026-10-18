"""APPROVALS-02 Part A: the transition service through the real app on Postgres as ``aip_app``."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.approvals import transition as transition_module
from aip.modules.approvals.api import (
    RecordRef,
    register_record_resolver,
    unregister_record_resolver,
)
from aip.modules.approvals.decision_chain import genesis_hash
from aip.modules.approvals.tests.conftest import (
    ALICE,
    BOB,
    CAROL,
    DAVE,
    DAVE_ID,
    DemoRecords,
    act,
    history,
    publish,
    signed,
    start,
    su_execute,
    su_fetch,
)
from aip.modules.approvals.tests.fixtures import demo_spec
from aip.modules.identity.api import SignoffContext, SignoffDecision, derive_assurance

HEX64 = re.compile(r"^[0-9a-f]{64}$")

pytestmark = pytest.mark.usefixtures("demo")


async def counts(db: TenantDb, instance_id: str) -> tuple[int, int]:
    """(decision rows, workflow.transitioned events) for the instance, read as the superuser."""
    decisions = await su_fetch(
        db,
        "SELECT count(*) FROM workflow_decision_history WHERE instance_id = $1",
        UUID(instance_id),
    )
    events = await su_fetch(
        db,
        "SELECT count(*) FROM domain_events WHERE event_name = 'workflow.transitioned'"
        " AND aggregate_id = $1",
        UUID(instance_id),
    )
    return int(decisions[0][0]), int(events[0][0])


async def test_a_submit_writes_one_chained_decision_and_one_event(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    assert instance["currentState"] == "draft"
    assert instance["version"] == 1

    response = await act(client, instance["id"], "submit", comment="ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["instance"]["currentState"] == "submitted"
    assert body["instance"]["syncVersion"] == instance["syncVersion"] + 1
    assert body["decision"]["status"] == "applied"

    found = await history(client, instance["id"])
    assert found["chainValid"] is True
    [entry] = found["entries"]
    assert entry["seq"] == 1
    assert entry["prevHash"] == genesis_hash(instance["id"])
    assert HEX64.match(entry["entryHash"])
    assert entry["comment"] == "ready"
    assert entry["actorId"] == str(ALICE_ID)
    assert "ipAddress" not in entry  # stored as evidence, never served
    assert await counts(db, instance["id"]) == (1, 1)

    [(payload,)] = await su_fetch(
        db, "SELECT payload FROM domain_events WHERE aggregate_id = $1", UUID(instance["id"])
    )
    assert '"from": "draft"' in payload and '"definitionKey": "demo"' in payload


async def test_a_caller_without_the_transition_permission_writes_nothing(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    response = await act(client, instance["id"], "submit", headers=CAROL)
    assert response.status_code == 403
    assert response.json()["permission"] == "approvals.demo.submit"
    assert await counts(db, instance["id"]) == (0, 0)


async def test_an_illegal_action_is_409_and_writes_nothing(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    response = await act(client, instance["id"], "approve")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_TRANSITION"
    assert await counts(db, instance["id"]) == (0, 0)


async def test_an_instance_keeps_its_pinned_version_after_a_newer_publish(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    assert (await act(client, instance["id"], "submit")).status_code == 200

    v2 = demo_spec()
    v2["transitions"] = [t for t in v2["transitions"] if t["action"] not in ("reject", "resubmit")]
    v2["states"] = [s for s in v2["states"] if s["code"] != "rejected"]
    await publish(db, v2)

    newer = await start(client)
    assert newer["version"] == 2
    response = await act(client, instance["id"], "reject")
    assert response.status_code == 200, response.text
    assert response.json()["instance"]["currentState"] == "rejected"
    assert response.json()["instance"]["version"] == 1


async def test_a_failure_after_the_decision_insert_rolls_everything_back(
    lenient_client: httpx.AsyncClient,
    client: httpx.AsyncClient,
    db: TenantDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = await start(client)

    async def broken_emit(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("outbox down")

    real_emit = transition_module.emit
    monkeypatch.setattr(transition_module, "emit", broken_emit)
    response = await act(lenient_client, instance["id"], "submit")
    assert response.status_code == 500
    monkeypatch.setattr(transition_module, "emit", real_emit)  # not undo(): it resets the app env

    current = await client.get(f"/api/v1/approvals/instances/{instance['id']}", headers=ALICE)
    assert current.json()["currentState"] == "draft"
    assert await counts(db, instance["id"]) == (0, 0)


async def test_two_transitions_at_once_serialise_on_the_instance(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    responses = await asyncio.gather(
        act(client, instance["id"], "submit"), act(client, instance["id"], "submit")
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert await counts(db, instance["id"]) == (1, 1)


async def test_a_stale_expected_sync_version_is_409(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    stale = instance["syncVersion"] + 5
    response = await act(client, instance["id"], "submit", expectedSyncVersion=stale)
    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_CONFLICT"
    assert await counts(db, instance["id"]) == (0, 0)
    ok = await act(client, instance["id"], "submit", expectedSyncVersion=instance["syncVersion"])
    assert ok.status_code == 200


async def test_aip_app_cannot_change_or_remove_a_decision(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    assert (await act(client, instance["id"], "submit")).status_code == 200
    for statement in (
        "UPDATE workflow_decision_history SET comment = 'x'",
        "DELETE FROM workflow_decision_history",
        "TRUNCATE workflow_decision_history",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with db.with_tenant(TENANT_A_ID) as conn:
                await conn.execute(text(statement))


async def test_altering_a_stored_decision_makes_the_chain_invalid(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    assert (await act(client, instance["id"], "submit")).status_code == 200
    assert (await act(client, instance["id"], "reject")).status_code == 200
    assert (await history(client, instance["id"]))["chainValid"] is True

    await su_execute(
        db,
        "UPDATE workflow_decision_history SET ip_address = '198.51.100.1'"
        f" WHERE instance_id = '{instance['id']}' AND seq = 2",
    )
    found = await history(client, instance["id"])
    assert found["chainValid"] is False
    assert found["brokenAtSeq"] == 2


async def test_another_tenant_sees_404(client: httpx.AsyncClient) -> None:
    instance = await start(client)
    path = f"/api/v1/approvals/instances/{instance['id']}"
    assert (await client.get(path, headers=BOB)).status_code == 404
    assert (await client.get(f"{path}/history", headers=BOB)).status_code == 404
    assert (await act(client, instance["id"], "submit", headers=BOB)).status_code == 404


async def test_a_body_with_an_unknown_key_is_refused(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await start(client)
    response = await act(client, instance["id"], "submit", guardResult=True)
    assert response.status_code == 422  # every validation error in this API is 422 (ADR 0035)
    assert await counts(db, instance["id"]) == (0, 0)


async def test_starting_needs_the_permission_a_resolver_and_an_active_definition(
    client: httpx.AsyncClient,
) -> None:
    path = "/api/v1/approvals/instances"
    body = {"recordType": "demo", "recordId": str(uuid4())}
    refused = await client.post(path, json=body, headers=CAROL)
    assert refused.status_code == 403
    unknown = {"recordType": "no_such_type", "recordId": str(uuid4())}
    response = await client.post(path, json=unknown, headers=ALICE)
    assert response.status_code == 422
    assert response.json()["code"] == "UNKNOWN_RECORD_TYPE"

    async def other(conn: Any, record_id: UUID) -> RecordRef:
        return RecordRef(project_id=None)

    register_record_resolver("other", other)
    try:
        body = {"recordType": "other", "recordId": str(uuid4())}
        response = await client.post(path, json=body, headers=ALICE)
    finally:
        unregister_record_resolver("other")
    assert response.status_code == 422
    assert response.json()["code"] == "NO_ACTIVE_DEFINITION"


async def test_the_record_project_comes_from_its_host_module(
    client: httpx.AsyncClient, demo_records: DemoRecords
) -> None:
    path = "/api/v1/approvals/instances"
    record, project_a, project_b = uuid4(), uuid4(), uuid4()
    demo_records.projects[record] = project_a
    # Claiming another project for a project-A record (to pick B's workflow) must not work.
    body = {"recordType": "demo", "recordId": str(record), "projectId": str(project_b)}
    mismatch = await client.post(path, json=body, headers=ALICE)
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "PROJECT_MISMATCH"

    started = await client.post(path, json={**body, "projectId": None}, headers=ALICE)
    assert started.status_code == 201, started.text
    assert started.json()["projectId"] == str(project_a)

    gone = uuid4()
    demo_records.missing.add(gone)
    response = await client.post(
        path, json={"recordType": "demo", "recordId": str(gone)}, headers=ALICE
    )
    assert response.status_code == 404


async def test_available_transitions_reflect_the_callers_permissions(
    client: httpx.AsyncClient,
) -> None:
    instance = await start(client)
    [submit] = instance["availableTransitions"]
    assert submit == {
        "action": "submit",
        "toState": "submitted",
        "labelKey": "approvals.demo.action.submit",
        "critical": False,
        "allowed": True,
        "reasonKey": None,
    }
    viewer = await client.get(f"/api/v1/approvals/instances/{instance['id']}", headers=CAROL)
    assert viewer.json()["availableTransitions"][0]["allowed"] is False
    assert viewer.json()["availableTransitions"][0]["reasonKey"] == "approvals.permission.denied"


# --- critical transitions: sign-off assurance (ADR 0010), with check_signoff_assurance stubbed ---


def stub_signoff(monkeypatch: pytest.MonkeyPatch, decide: Callable[[SignoffContext], str]) -> None:
    async def fake(conn: Any, ctx: SignoffContext, action_code: str) -> SignoffDecision:
        return SignoffDecision(
            decision=decide(ctx),  # pyright: ignore[reportArgumentType]
            assurance=derive_assurance(ctx.session),
            action_code=action_code,
            min_aal=2,
            max_age_min=10,
        )

    monkeypatch.setattr(transition_module, "check_signoff_assurance", fake)


async def submitted(client: httpx.AsyncClient) -> dict[str, Any]:
    instance = await start(client)
    assert (await act(client, instance["id"], "submit")).status_code == 200
    return instance


async def test_step_up_required_is_401_with_the_step_up_url(
    client: httpx.AsyncClient, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_signoff(monkeypatch, lambda ctx: "step_up_required")
    instance = await submitted(client)
    response = await act(client, instance["id"], "approve")
    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["code"] == "STEP_UP_REQUIRED"
    assert detail["stepUpUrl"].startswith("/api/v1/auth/step-up/start")
    assert await counts(db, instance["id"]) == (1, 1)


async def test_countersign_required_records_a_pending_decision_only(
    client: httpx.AsyncClient, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_signoff(monkeypatch, lambda ctx: "countersign_required")
    instance = await submitted(client)
    response = await act(client, instance["id"], "approve")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["decision"]["status"] == "pending_countersign"
    assert body["instance"]["currentState"] == "submitted"
    assert body["instance"]["pendingCountersign"] == "approve"
    assert await counts(db, instance["id"]) == (2, 1)  # the decision, but no transition event

    other = await act(client, instance["id"], "reject")
    assert other.status_code == 409
    assert other.json()["code"] == "COUNTERSIGN_PENDING"


async def test_the_signer_cannot_countersign_their_own_decision(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_signoff(monkeypatch, lambda ctx: "countersign_required")
    instance = await submitted(client)
    assert (await act(client, instance["id"], "approve")).status_code == 202
    stub_signoff(monkeypatch, lambda ctx: "allow")
    response = await act(client, instance["id"], "approve")
    assert response.status_code == 409
    assert response.json()["code"] == "SELF_COUNTERSIGN"


async def test_a_supervisors_countersign_applies_the_transition(
    client: httpx.AsyncClient, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_signoff(monkeypatch, lambda ctx: "countersign_required")
    instance = await submitted(client)
    pending = (await act(client, instance["id"], "approve")).json()["decision"]

    stub_signoff(monkeypatch, lambda ctx: "countersign_required")
    weak = await act(client, instance["id"], "approve", headers=DAVE)
    assert weak.status_code == 403
    assert weak.json()["code"] == "COUNTERSIGN_ASSURANCE_REQUIRED"

    stub_signoff(monkeypatch, lambda ctx: "allow")
    response = await act(client, instance["id"], "approve", headers=signed(TENANT_A_ID, DAVE_ID))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["instance"]["currentState"] == "approved"
    assert body["decision"]["countersignsId"] == pending["id"]
    assert body["decision"]["actorId"] == str(DAVE_ID)
    assert body["decision"]["assurance"]["method"] == "totp"
    assert body["decision"]["assurance"]["level"] == 2

    found = await history(client, instance["id"])
    assert found["chainValid"] is True
    assert [e["status"] for e in found["entries"]] == ["applied", "pending_countersign", "applied"]
    assert found["entries"][1]["assurance"]["method"] == "password"  # Alice's weaker sign-in
    assert await counts(db, instance["id"]) == (3, 2)


async def test_an_allowed_critical_transition_records_the_method(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[SignoffContext] = []

    def allow(ctx: SignoffContext) -> str:
        seen.append(ctx)
        return "allow"

    stub_signoff(monkeypatch, allow)
    instance = await submitted(client)
    response = await act(client, instance["id"], "approve", headers=signed(TENANT_A_ID, ALICE_ID))
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["assurance"]["method"] == "totp"
    assert decision["authStrength"] == "mfa"
    assert decision["assurance"]["authenticatedAt"] is not None
    assert seen[0].aal2_available is True


async def test_the_real_signoff_policy_refuses_a_stale_aal1_session(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    instance = await submitted(client)
    # Alice signs in with aal1 and no MFA enrolled: no way to step up, so a countersign is needed.
    response = await act(client, instance["id"], "approve")
    assert response.status_code == 202
    assert response.json()["decision"]["status"] == "pending_countersign"
    # A fresh aal2 session for Dave passes the default policy (aal 2 within 10 minutes).
    applied = await act(client, instance["id"], "approve", headers=signed(TENANT_A_ID, DAVE_ID))
    assert applied.status_code == 200, applied.text
    assert applied.json()["instance"]["currentState"] == "approved"
