"""INSPECTIONS-03 integration tests: ITP steps, hold and witness points, signed and chained
sign-offs with sign-off assurance, NCR holds and the open-steps guard.

The app connects as ``aip_app`` (RLS on); users and grants come from the INSPECTIONS-01 conftest.
Here the inspector also holds ``itp.sign``, and the supervisor ``itp.sign``, ``itp.manage`` and
``itp.waive``. Each test uses ITP ``ITP-101`` (kind ``itp``) on asset ``TK-101`` in project
``KF-01`` with steps 1 hold "Surface preparation", 2 witness "DFT check" (24 hours' notice) and
3 review "Final coat", moved to ``in_progress``. The supervisor has MFA enrolled (conftest); the
inspector has not unless a test enrols them.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.inspections import workflow
from aip.modules.inspections.api import (
    HoldMismatchError,
    InspectionsApi,
    StepAlreadyReleasedError,
)
from aip.modules.inspections.signoff_chain import genesis_hash
from aip.platform.context import use_context
from aip.platform.db.scope import run_as_system

from .conftest import (
    BOB,
    INSPECTOR,
    INSPECTOR_ID,
    KF_01,
    SUPERVISOR,
    SUPERVISOR_ID,
    VIEWER,
    VIEWER_ID,
    GrantTable,
    Setup,
    count,
    ctx,
    principal_headers,
    signed,
    su_execute,
    su_fetch,
)

INSPECTIONS = "/api/v1/inspections"
STEPS = "/api/v1/itp-steps"
STEP_DEFS: list[dict[str, Any]] = [
    {"seq": 1, "title": "Surface preparation", "pointType": "hold"},
    {"seq": 2, "title": "DFT check", "pointType": "witness", "noticeHours": 24},
    {"seq": 3, "title": "Final coat", "pointType": "review"},
]
api = InspectionsApi()


@dataclass(frozen=True, slots=True)
class Itp:
    id: str
    steps: tuple[str, str, str]


@pytest.fixture(autouse=True)
def signers(grants: GrantTable) -> GrantTable:
    grants.by_user[INSPECTOR_ID] |= {"itp.sign"}
    grants.by_user[SUPERVISOR_ID] |= {"itp.sign", "itp.manage", "itp.waive"}
    return grants


def password(user: UUID) -> dict[str, str]:
    """A fresh aal 1 password session: below the default sign-off policy (aal 2)."""
    return principal_headers(
        TENANT_A_ID, user, aal=1, amr=["pwd"], authenticated_at=datetime.now(UTC)
    )


async def create_itp(client: httpx.AsyncClient, setup: Setup, kind: str = "itp") -> str:
    created = await client.post(
        INSPECTIONS,
        json={
            "assetId": str(setup.asset_id),
            "projectId": str(KF_01),
            "templateId": str(setup.template_id),
            "kind": kind,
        },
        headers=SUPERVISOR,
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def add_steps(
    client: httpx.AsyncClient, itp_id: str, steps: list[dict[str, Any]]
) -> httpx.Response:
    return await client.post(
        f"{INSPECTIONS}/{itp_id}/itp-steps", json={"steps": steps}, headers=SUPERVISOR
    )


async def move(client: httpx.AsyncClient, itp_id: str, action: str, user: UUID) -> httpx.Response:
    return await client.post(
        f"{INSPECTIONS}/{itp_id}/transition", json={"action": action}, headers=signed(user)
    )


@pytest.fixture
async def itp(client: httpx.AsyncClient, setup: Setup) -> Itp:
    itp_id = await create_itp(client, setup)
    added = await add_steps(client, itp_id, STEP_DEFS)
    assert added.status_code == 201, added.text
    ids = [s["id"] for s in added.json()["steps"]]
    for action, user in (("ready", SUPERVISOR_ID), ("inspect", INSPECTOR_ID)):
        moved = await move(client, itp_id, action, user)
        assert moved.status_code == 200, (action, moved.text)
    return Itp(id=itp_id, steps=(ids[0], ids[1], ids[2]))


async def act(
    client: httpx.AsyncClient, step_id: str, action: str, headers: dict[str, str], **extra: Any
) -> httpx.Response:
    return await client.post(
        f"{STEPS}/{step_id}/actions", json={"action": action, **extra}, headers=headers
    )


async def act_ok(
    client: httpx.AsyncClient, step_id: str, action: str, headers: dict[str, str]
) -> dict[str, Any]:
    response = await act(client, step_id, action, headers)
    assert response.status_code == 200, (action, response.text)
    return response.json()


async def sign(
    client: httpx.AsyncClient,
    step_id: str,
    decision: str,
    headers: dict[str, str],
    role: str = "inspector",
    **extra: Any,
) -> httpx.Response:
    return await client.post(
        f"{STEPS}/{step_id}/signoffs",
        json={"decision": decision, "signatoryRole": role, **extra},
        headers=headers,
    )


async def start(client: httpx.AsyncClient, step_id: str) -> None:
    await act_ok(client, step_id, "ready", SUPERVISOR)
    await act_ok(client, step_id, "start", INSPECTOR)


async def release_hold(client: httpx.AsyncClient, itp: Itp) -> None:
    await start(client, itp.steps[0])
    released = await sign(client, itp.steps[0], "approve", signed(INSPECTOR_ID))
    assert released.status_code == 200, released.text


async def waive_witness(client: httpx.AsyncClient, db: TenantDb, itp: Itp) -> None:
    await act_ok(client, itp.steps[1], "ready", SUPERVISOR)
    await backdate_ready(db, itp.steps[1], hours=25)
    waived = await sign(
        client,
        itp.steps[1],
        "waived",
        signed(SUPERVISOR_ID),
        "supervisor",
        comment="Client did not attend",
    )
    assert waived.status_code == 200, waived.text


async def backdate_ready(db: TenantDb, step_id: str, hours: int) -> None:
    await su_execute(
        db,
        f"UPDATE itp_steps SET ready_at = now() - interval '{hours} hours' WHERE id = '{step_id}'",
    )


async def step_view(client: httpx.AsyncClient, itp: Itp, index: int) -> dict[str, Any]:
    listed = await client.get(f"{INSPECTIONS}/{itp.id}/itp-steps", headers=VIEWER)
    assert listed.status_code == 200, listed.text
    return listed.json()["steps"][index]


async def signoffs(db: TenantDb) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT seq, status, decision, action_code, assurance_level, prev_hash, countersigns_id,"
        " id, itp_step_id, signer_user_id FROM inspection_signoffs ORDER BY seq",
    )
    keys = (
        "seq",
        "status",
        "decision",
        "action_code",
        "assurance_level",
        "prev_hash",
        "countersigns_id",
        "id",
        "itp_step_id",
        "signer_user_id",
    )
    return [dict(zip(keys, r, strict=True)) for r in rows]


async def events(db: TenantDb, name: str) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT payload FROM domain_events WHERE event_name = $1 ORDER BY occurred_at, id",
        name,
    )
    return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]


# --- releasing a hold point -----------------------------------------------------------------------


async def test_an_assured_inspector_releases_a_hold_point(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await start(client, itp.steps[0])
    released = await sign(client, itp.steps[0], "approve", signed(INSPECTOR_ID))
    assert released.status_code == 200, released.text
    body = released.json()
    assert body["step"]["status"] == "released"
    assert body["step"]["releasedAt"] is not None
    assert body["signoff"]["assuranceLevel"] == 2

    [row] = await signoffs(db)
    assert row["action_code"] == "hold_point.release"
    assert (row["seq"], row["assurance_level"], row["status"]) == (1, 2, "applied")
    assert row["prev_hash"] == genesis_hash(itp.id)
    [event] = await events(db, "itp_step.released")
    assert event["stepId"] == itp.steps[0]
    assert (event["pointType"], event["decision"]) == ("hold", "approve")
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        assert await api.is_step_released(conn, UUID(itp.steps[0])) is True
        assert await api.is_step_released(conn, UUID(itp.steps[2])) is False
        assert await api.is_step_released(conn, uuid.uuid4()) is False


async def test_a_later_step_cannot_start_while_a_hold_is_open(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await act_ok(client, itp.steps[2], "ready", SUPERVISOR)
    refused = await act(client, itp.steps[2], "start", INSPECTOR)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "BLOCKED_BY_HOLD"
    assert (await step_view(client, itp, 2))["status"] == "ready"
    assert await signoffs(db) == []

    await release_hold(client, itp)
    assert (await act_ok(client, itp.steps[2], "start", INSPECTOR))["status"] == "in_progress"


async def test_a_step_is_started_only_while_the_itp_is_in_progress(
    client: httpx.AsyncClient, setup: Setup
) -> None:
    itp_id = await create_itp(client, setup)
    added = await add_steps(client, itp_id, STEP_DEFS[:1])
    step_id = added.json()["steps"][0]["id"]
    await act_ok(client, step_id, "ready", SUPERVISOR)
    refused = await act(client, step_id, "start", INSPECTOR)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "ITP_NOT_IN_PROGRESS"


async def test_the_caller_sees_the_actions_they_may_take(
    client: httpx.AsyncClient, itp: Itp
) -> None:
    await act_ok(client, itp.steps[0], "ready", SUPERVISOR)

    async def available(headers: dict[str, str]) -> list[list[str]]:
        listed = await client.get(f"{INSPECTIONS}/{itp.id}/itp-steps", headers=headers)
        assert listed.status_code == 200, listed.text
        return [s["availableActions"] for s in listed.json()["steps"]]

    assert await available(INSPECTOR) == [["start"], [], []]
    assert await available(SUPERVISOR) == [["start"], ["ready"], ["ready"]]
    assert await available(VIEWER) == [[], [], []]
    await act_ok(client, itp.steps[0], "start", INSPECTOR)
    assert (await available(INSPECTOR))[0] == ["approve", "reject"]


# --- sign-off assurance ---------------------------------------------------------------------------


async def test_an_enrolled_signer_below_the_minimum_must_step_up(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await su_execute(db, f"UPDATE app_user SET mfa_enrolled_at = now() WHERE id = '{INSPECTOR_ID}'")
    await start(client, itp.steps[0])
    refused = await sign(client, itp.steps[0], "approve", password(INSPECTOR_ID))
    assert refused.status_code == 401, refused.text
    assert refused.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    assert await signoffs(db) == []
    assert (await step_view(client, itp, 0))["status"] == "in_progress"


async def test_a_sign_off_below_the_minimum_waits_for_a_countersign(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await start(client, itp.steps[0])
    pending = await sign(client, itp.steps[0], "approve", password(INSPECTOR_ID))
    assert pending.status_code == 202, pending.text
    assert pending.json()["signoff"]["status"] == "pending_countersign"
    assert pending.json()["step"]["status"] == "in_progress"
    [first] = await signoffs(db)
    assert first["status"] == "pending_countersign"
    assert await events(db, "itp_step.released") == []
    assert (await step_view(client, itp, 0))["pendingCountersign"] == "approve"

    again = await sign(client, itp.steps[0], "approve", signed(INSPECTOR_ID))
    assert again.status_code == 409 and again.json()["code"] == "SELF_COUNTERSIGN"
    other = await sign(
        client, itp.steps[0], "reject", signed(SUPERVISOR_ID), "supervisor", comment="no"
    )
    assert other.status_code == 409 and other.json()["code"] == "COUNTERSIGN_PENDING"

    countersigned = await sign(client, itp.steps[0], "approve", signed(SUPERVISOR_ID), "supervisor")
    assert countersigned.status_code == 200, countersigned.text
    assert countersigned.json()["step"]["status"] == "released"
    second = (await signoffs(db))[1]
    assert second["status"] == "applied"
    assert second["countersigns_id"] == first["id"]
    assert len(await events(db, "itp_step.released")) == 1

    listed = await client.get(f"{INSPECTIONS}/{itp.id}/signoffs", headers=VIEWER)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["entries"]) == 2
    assert listed.json()["chainValid"] is True


async def test_a_countersigner_below_the_minimum_is_refused(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await start(client, itp.steps[0])
    assert (await sign(client, itp.steps[0], "approve", password(INSPECTOR_ID))).status_code == 202
    await su_execute(db, f"UPDATE app_user SET mfa_enrolled_at = NULL WHERE id = '{SUPERVISOR_ID}'")
    refused = await sign(client, itp.steps[0], "approve", password(SUPERVISOR_ID), "supervisor")
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "COUNTERSIGN_ASSURANCE_REQUIRED"
    assert len(await signoffs(db)) == 1


# --- witness points -------------------------------------------------------------------------------


async def test_a_witness_point_is_waived_after_its_notice(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await release_hold(client, itp)
    await act_ok(client, itp.steps[1], "ready", SUPERVISOR)
    early = await sign(
        client, itp.steps[1], "waived", signed(SUPERVISOR_ID), "supervisor", comment="No show"
    )
    assert early.status_code == 409 and early.json()["code"] == "NOTICE_NOT_ELAPSED"

    await backdate_ready(db, itp.steps[1], hours=25)
    not_allowed = await sign(
        client, itp.steps[1], "waived", signed(INSPECTOR_ID), comment="Client did not attend"
    )
    assert not_allowed.status_code == 403, not_allowed.text
    waived = await sign(
        client,
        itp.steps[1],
        "waived",
        signed(SUPERVISOR_ID),
        "supervisor",
        comment="Client did not attend",
    )
    assert waived.status_code == 200, waived.text
    assert waived.json()["step"]["status"] == "waived"
    assert (await signoffs(db))[-1]["decision"] == "waived"
    assert [e["decision"] for e in await events(db, "itp_step.released")] == ["approve", "waived"]


# --- NCR holds ------------------------------------------------------------------------------------


async def test_an_ncr_hold_blocks_the_release_until_its_issue_clears_it(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await release_hold(client, itp)
    await waive_witness(client, db, itp)
    await start(client, itp.steps[2])
    step = UUID(itp.steps[2])
    n1, n2 = uuid.uuid4(), uuid.uuid4()

    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            held = await api.place_hold(conn, step, issue_id=n1)
    assert held.held is True
    refused = await sign(client, itp.steps[2], "approve", signed(INSPECTOR_ID))
    assert refused.status_code == 409 and refused.json()["code"] == "STEP_ON_HOLD"
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        assert await api.is_step_released(conn, step) is False
        assert (await workflow.facts(conn, UUID(itp.id)))["heldStepCount"] == 1

    with use_context(ctx()), pytest.raises(HoldMismatchError):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await api.clear_hold(conn, step, issue_id=n2)
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await api.clear_hold(conn, step, issue_id=n1)
    released = await sign(client, itp.steps[2], "approve", signed(INSPECTOR_ID))
    assert released.status_code == 200, released.text
    changes = await events(db, "itp_step.hold_changed")
    assert [(e["issueId"], e["held"]) for e in changes] == [(str(n1), True), (str(n1), False)]


async def test_a_released_step_cannot_be_held(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await release_hold(client, itp)
    with use_context(ctx()), pytest.raises(StepAlreadyReleasedError):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await api.place_hold(conn, UUID(itp.steps[0]), issue_id=uuid.uuid4())


# --- the open-steps guard -------------------------------------------------------------------------


async def test_an_itp_with_open_steps_cannot_be_handed_in(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        facts = await workflow.facts(conn, UUID(itp.id))
    assert (facts["openStepCount"], facts["heldStepCount"]) == (3, 0)

    await release_hold(client, itp)
    await waive_witness(client, db, itp)
    refused = await move(client, itp.id, "request_supervisor_review", INSPECTOR_ID)
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "GUARD_FAILED"
    assert refused.json()["messageKey"] == "inspection.guard.not_ready_to_submit"

    await start(client, itp.steps[2])
    assert (await sign(client, itp.steps[2], "approve", signed(INSPECTOR_ID))).status_code == 200
    handed_in = await move(client, itp.id, "request_supervisor_review", INSPECTOR_ID)
    assert handed_in.status_code == 200, handed_in.text


# --- setting up steps -----------------------------------------------------------------------------


async def test_steps_are_set_up_only_on_an_itp_that_has_not_started(
    client: httpx.AsyncClient, setup: Setup, itp: Itp
) -> None:
    plain = await create_itp(client, setup, kind="inspection")
    refused = await add_steps(client, plain, STEP_DEFS[:1])
    assert refused.status_code == 422 and refused.json()["code"] == "NOT_AN_ITP"

    locked = await add_steps(client, itp.id, [{"seq": 4, "title": "Late", "pointType": "review"}])
    assert locked.status_code == 409 and locked.json()["code"] == "ITP_LOCKED"

    draft = await create_itp(client, setup)
    twice = await add_steps(client, draft, [STEP_DEFS[0], {**STEP_DEFS[2], "seq": 1}])
    assert twice.status_code == 409 and twice.json()["code"] == "DUPLICATE_SEQ"
    assert (await add_steps(client, draft, STEP_DEFS[:1])).status_code == 201
    again = await add_steps(client, draft, STEP_DEFS[:1])
    assert again.status_code == 409 and again.json()["code"] == "DUPLICATE_SEQ"

    wrong = await add_steps(client, draft, [{**STEP_DEFS[0], "seq": 5, "noticeHours": 4}])
    assert wrong.status_code == 422, wrong.text


async def test_a_stale_version_returns_the_current_step(
    client: httpx.AsyncClient, itp: Itp
) -> None:
    readied = await act_ok(client, itp.steps[0], "ready", SUPERVISOR)
    stale = await act(
        client, itp.steps[0], "start", INSPECTOR, expectedSyncVersion=readied["syncVersion"] - 1
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "VERSION_CONFLICT"
    assert stale.json()["current"]["status"] == "ready"


# --- append-only sign-offs, permissions, tenants --------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    ["UPDATE inspection_signoffs SET comment = 'x'", "DELETE FROM inspection_signoffs"],
)
async def test_aip_app_can_never_change_a_sign_off(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp, statement: str
) -> None:
    await release_hold(client, itp)
    with pytest.raises(DBAPIError) as caught:
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text(statement))
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"  # insufficient privilege
    assert len(await signoffs(db)) == 1


async def test_an_altered_sign_off_breaks_the_chain(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    await release_hold(client, itp)
    await su_execute(db, "UPDATE inspection_signoffs SET comment = 'edited'")
    listed = await client.get(f"{INSPECTIONS}/{itp.id}/signoffs", headers=VIEWER)
    assert listed.status_code == 200, listed.text
    assert listed.json()["chainValid"] is False
    assert listed.json()["brokenAtSeq"] == 1


async def test_a_viewer_cannot_sign(client: httpx.AsyncClient, db: TenantDb, itp: Itp) -> None:
    await start(client, itp.steps[0])
    refused = await sign(client, itp.steps[0], "approve", signed(VIEWER_ID))
    assert refused.status_code == 403, refused.text
    assert await signoffs(db) == []


async def test_another_tenant_sees_no_steps(
    client: httpx.AsyncClient, db: TenantDb, itp: Itp
) -> None:
    seen = await client.get(f"{INSPECTIONS}/{itp.id}/itp-steps", headers=BOB)
    assert seen.status_code == 404, seen.text
    signed_b = await sign(client, itp.steps[0], "approve", signed(BOB_ID, TENANT_B_ID))
    assert signed_b.status_code == 404, signed_b.text
    acted = await act(client, itp.steps[0], "ready", BOB)
    assert acted.status_code == 404, acted.text
    listed = await client.get(f"{INSPECTIONS}/{itp.id}/signoffs", headers=BOB)
    assert listed.status_code == 404, listed.text

    async with db.with_tenant(TENANT_B_ID) as conn:
        assert await api.get_itp_step(conn, UUID(itp.steps[0])) is None
        found = await conn.execute(text("SELECT count(*) FROM itp_steps"))
        assert found.scalar_one() == 0
    async with db.with_tenant(TENANT_A_ID) as conn:
        mine = await api.get_itp_step(conn, UUID(itp.steps[0]))
    assert mine is not None and mine.seq == 1
    assert await count(db, "SELECT count(*) FROM itp_steps") == 3
