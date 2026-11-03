"""INSPECTIONS-10 integration tests: the guarded submit transitions of both inspection presets,
through ``TransitionService`` with the real facts provider (ADR 0041 §4, §5).

Submit is Request Supervisor Review when the template has supervisor review, and Submit Report
(critical, ``approvals.inspection.execute``) when it has not; either needs the report ticked
complete. The form and helpers are ``test_acknowledgements_db.py``'s; the inspector has MFA
enrolled here, so a critical action on an aal 1 session must step up.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.approvals.api import ApprovalsApi
from aip.platform.context import use_context

from .conftest import (
    INSPECTOR,
    INSPECTOR_ID,
    KF_01,
    LEAD_ID,
    VIEWER,
    GrantTable,
    ctx,
    signed,
    su_execute,
)
from .test_acknowledgements_db import (
    INSPECTIONS,
    answer,
    complete_everything,
    new_inspection,
    responders,  # noqa: F401 - the autouse grants fixture
)


@pytest.fixture(autouse=True)
async def inspector_has_mfa(db: TenantDb) -> None:
    await su_execute(db, f"UPDATE app_user SET mfa_enrolled_at = now() WHERE id = '{INSPECTOR_ID}'")


async def actions(client: httpx.AsyncClient, inspection_id: str) -> dict[str, dict[str, Any]]:
    found = await client.get(f"{INSPECTIONS}/{inspection_id}", headers=INSPECTOR)
    assert found.status_code == 200, found.text
    return {t["action"]: t for t in found.json()["availableTransitions"]}


async def submit(
    client: httpx.AsyncClient, inspection_id: str, action: str, headers: dict[str, str]
) -> httpx.Response:
    return await client.post(
        f"{INSPECTIONS}/{inspection_id}/transition", json={"action": action}, headers=headers
    )


def signed_inspector() -> dict[str, str]:
    return signed(INSPECTOR_ID)  # a fresh aal 2 session: passes the sign-off policy


async def test_request_supervisor_review_waits_for_the_report_tick(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    inspection = await new_inspection(client, db)
    offered = await actions(client, inspection)
    assert "submit_report" not in offered  # never both submits
    review = offered["request_supervisor_review"]
    assert (review["allowed"], review["reasonKey"]) == (False, "inspection.guard.submit_not_ready")

    refused = await submit(client, inspection, "request_supervisor_review", signed_inspector())
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "GUARD_FAILED"
    assert refused.json()["messageKey"] == "inspection.guard.submit_not_ready"

    await complete_everything(client, inspection)
    assert (await actions(client, inspection))["request_supervisor_review"]["allowed"] is True
    handed_in = await submit(client, inspection, "request_supervisor_review", INSPECTOR)
    assert handed_in.status_code == 200, handed_in.text
    assert handed_in.json()["inspection"]["currentState"] == "supervisor_review"


async def test_without_supervisor_review_the_doer_submits_the_report_as_a_sign_off(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    inspection = await new_inspection(client, db, has_supervisor_review=False)
    offered = await actions(client, inspection)
    assert "request_supervisor_review" not in offered
    assert offered["submit_report"]["critical"] is True
    assert offered["submit_report"]["labelKey"] == "workflow.inspection.action.submit_report"

    early = await submit(client, inspection, "submit_report", signed_inspector())
    assert early.status_code == 422 and early.json()["code"] == "GUARD_FAILED"

    await complete_everything(client, inspection)
    step_up = await submit(client, inspection, "submit_report", INSPECTOR)  # aal 1
    assert step_up.status_code == 401, step_up.text
    assert step_up.json()["detail"]["code"] == "STEP_UP_REQUIRED"

    done = await submit(client, inspection, "submit_report", signed_inspector())
    assert done.status_code == 200, done.text
    assert done.json()["inspection"]["currentState"] == "performed"
    decision = done.json()["decision"]
    assert (decision["action"], decision["actorId"]) == ("submit_report", str(INSPECTOR_ID))
    assert (decision["status"], decision["authStrength"]) == ("applied", "mfa")
    assert (
        (await actions(client, inspection))
        .keys()
        .isdisjoint({"submit_report", "request_supervisor_review"})
    )

    late = await answer(client, inspection, dft_1=400)
    assert late.status_code == 409 and late.json()["code"] == "INSPECTION_NOT_EDITABLE"
    history = await client.get(f"{INSPECTIONS}/{inspection}/history", headers=VIEWER)
    assert history.json()["chainValid"] is True


CLIENT_ID = LEAD_ID  # plays the client reviewer here


async def test_the_client_variant_submits_the_report_to_client_review_and_again_after_rework(
    client: httpx.AsyncClient, db: TenantDb, grants: GrantTable
) -> None:
    grants.by_user[CLIENT_ID] |= {"approvals.inspection.client_approve"}
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await ApprovalsApi().install_preset(conn, "inspection_standard")
            await ApprovalsApi().install_preset(conn, "inspection_client_review", project_id=KF_01)
    inspection = await new_inspection(client, db, has_supervisor_review=False)
    await complete_everything(client, inspection)
    done = await submit(client, inspection, "submit_report", signed_inspector())
    assert done.status_code == 200, done.text
    assert done.json()["inspection"]["currentState"] == "client_review"

    # The client sends it back; the inspector reworks it and submits the report again from
    # rework (owner 2026-11-03), never offered Request Supervisor Review.
    reworked = await client.post(
        f"{INSPECTIONS}/{inspection}/transition",
        json={"action": "request_rework", "comment": "redo the DFT"},
        headers=signed(CLIENT_ID),
    )
    assert reworked.status_code == 200, reworked.text
    offered = await actions(client, inspection)
    assert "request_supervisor_review" not in offered
    assert offered["submit_report"]["allowed"] is False  # rework cleared the ticks
    await complete_everything(client, inspection)
    again = await submit(client, inspection, "submit_report", signed_inspector())
    assert again.status_code == 200, again.text
    assert again.json()["inspection"]["currentState"] == "client_review"
