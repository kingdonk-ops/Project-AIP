"""INSPECTIONS-02 integration tests: append-only answers, the current view and validation.

The app connects as ``aip_app`` (RLS on); users and grants come from the INSPECTIONS-01 conftest.
Here the inspector also holds ``inspection.respond``, and the supervisor holds it plus
``approvals.inspection.review`` ("Edit Inspection during Review", ADR 0041 §6). Each test answers a
published coating form: ``coating_dft`` (number, required, fails below 250), ``surface_prep``
(dropdown ``sa2_5``/``sa3``, required) and ``remarks`` (text, visible only for ``sa3``).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import JOBS, TenantDb

from aip.modules.inspections import workflow
from aip.modules.inspections.api import InspectionsApi
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.partitions import partition_name
from aip.platform.db.scope import run_as_system

from .conftest import (
    ALICE,
    BOB,
    INSPECTOR,
    INSPECTOR_ID,
    KF_01,
    SUPERVISOR,
    SUPERVISOR_ID,
    VIEWER,
    GrantTable,
    count,
    create_asset,
    install_preset,
    publish,
    signed,
    su_fetch,
)

INSPECTIONS = "/api/v1/inspections"
REVIEW = "approvals.inspection.review"

COATING_FORM: dict[str, Any] = {
    "schemaVersion": 1,
    "sections": [
        {
            "key": "coating",
            "label": "Coating",
            "fields": [
                {
                    "key": "coating_dft",
                    "type": "number",
                    "label": "Dry film thickness",
                    "required": True,
                    "failWhen": {"<": [{"var": "answers.coating_dft"}, 250]},
                },
                {
                    "key": "surface_prep",
                    "type": "dropdown",
                    "label": "Surface preparation",
                    "required": True,
                    "options": [
                        {"value": "sa2_5", "label": "Sa 2.5"},
                        {"value": "sa3", "label": "Sa 3"},
                    ],
                },
                {
                    "key": "remarks",
                    "type": "text",
                    "label": "Remarks",
                    "visibleIf": {"==": [{"var": "answers.surface_prep"}, "sa3"]},
                },
            ],
        }
    ],
}


@pytest.fixture(autouse=True)
def responders(grants: GrantTable) -> GrantTable:
    grants.by_user[INSPECTOR_ID] |= {"inspection.respond"}
    grants.by_user[SUPERVISOR_ID] |= {"inspection.respond", REVIEW}
    return grants


@pytest.fixture
async def inspection(client: httpx.AsyncClient, db: TenantDb) -> str:
    """An inspection of the coating form, moved to ``in_progress``; returns its id."""
    await install_preset(db)
    asset_id = await create_asset(db)
    form = {"code": "coating-dft", "name": "Coating DFT", "kind": "inspection"}
    uploaded = await client.post(
        "/api/v1/forms/templates", json={**form, "schema": COATING_FORM}, headers=ALICE
    )
    assert uploaded.status_code == 201, uploaded.text
    await publish(client, UUID(uploaded.json()["revision"]["id"]))
    created = await client.post(
        INSPECTIONS,
        json={
            "assetId": str(asset_id),
            "projectId": str(KF_01),
            "templateId": uploaded.json()["template"]["id"],
            "kind": "inspection",
        },
        headers=SUPERVISOR,
    )
    assert created.status_code == 201, created.text
    inspection_id: str = created.json()["id"]
    await move(client, inspection_id, "ready", SUPERVISOR_ID)
    await move(client, inspection_id, "inspect", INSPECTOR_ID)
    return inspection_id


async def move(
    client: httpx.AsyncClient, inspection_id: str, action: str, user: UUID, **extra: Any
) -> None:
    response = await client.post(
        f"{INSPECTIONS}/{inspection_id}/transition",
        json={"action": action, **extra},
        headers=signed(user),
    )
    assert response.status_code == 200, (action, response.text)


def item(field_key: str, value: Any, client_id: UUID | None = None) -> dict[str, Any]:
    return {"fieldKey": field_key, "value": value, "clientId": str(client_id or uuid.uuid4())}


async def answer(
    client: httpx.AsyncClient,
    inspection_id: str,
    *items: dict[str, Any],
    headers: dict[str, str] = INSPECTOR,
) -> httpx.Response:
    return await client.post(
        f"{INSPECTIONS}/{inspection_id}/responses", json={"answers": list(items)}, headers=headers
    )


async def answer_ok(
    client: httpx.AsyncClient, inspection_id: str, *items: dict[str, Any]
) -> list[dict[str, Any]]:
    response = await answer(client, inspection_id, *items)
    assert response.status_code == 200, response.text
    return response.json()["results"]


async def responses(db: TenantDb) -> int:
    return await count(db, "SELECT count(*) FROM inspection_responses")


async def failed_events(db: TenantDb) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT payload FROM domain_events WHERE event_name = 'inspection.answer_failed'"
        " ORDER BY occurred_at, id",
    )
    return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]


# --- the DATABASE-05 check: append-only, current by view, full history ----------------------------


async def test_a_correction_supersedes_and_the_view_shows_the_latest(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    first = (await answer_ok(client, inspection, item("coating_dft", 300)))[0]
    second = (await answer_ok(client, inspection, item("coating_dft", 320)))[0]
    assert first["created"] and second["created"]

    current = await client.get(f"{INSPECTIONS}/{inspection}/responses", headers=VIEWER)
    assert current.status_code == 200, current.text
    dft = current.json()["answers"]["coating_dft"]
    assert dft["value"] == 320 and dft["responseId"] == second["responseId"]
    assert dft["respondedBy"] == str(INSPECTOR_ID)
    assert (
        await count(
            db,
            "SELECT count(*) FROM inspection_current_responses WHERE field_key = 'coating_dft'",
        )
        == 1
    )

    history = await client.get(
        f"{INSPECTIONS}/{inspection}/responses/coating_dft/history", headers=VIEWER
    )
    assert history.status_code == 200, history.text
    entries = history.json()["entries"]
    assert [e["value"] for e in entries] == [300, 320]
    assert entries[0]["supersedesId"] is None
    assert entries[1]["supersedesId"] == first["responseId"]


async def test_the_current_view_reports_the_evaluation(
    client: httpx.AsyncClient, inspection: str
) -> None:
    await answer_ok(client, inspection, item("coating_dft", 200))
    body = (await client.get(f"{INSPECTIONS}/{inspection}/responses", headers=VIEWER)).json()
    evaluation = body["evaluation"]
    assert evaluation["missingRequired"] == ["surface_prep"]
    assert evaluation["failed"] == ["coating_dft"]
    assert evaluation["visible"]["remarks"] is False
    assert evaluation["required"]["coating_dft"] is True


async def test_a_retried_client_id_is_returned_not_stored_again(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    client_id = uuid.uuid4()
    first = (await answer_ok(client, inspection, item("coating_dft", 300, client_id)))[0]
    before = await responses(db)
    again = (await answer_ok(client, inspection, item("coating_dft", 310, client_id)))[0]
    assert again == {**first, "created": False}
    assert await responses(db) == before


# --- failed answers -------------------------------------------------------------------------------


async def test_only_a_newly_failed_answer_is_announced(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    result = (await answer_ok(client, inspection, item("coating_dft", 200)))[0]
    assert result["failed"] is True
    events = await failed_events(db)
    assert len(events) == 1
    assert events[0]["fieldKey"] == "coating_dft"
    assert events[0]["inspectionId"] == inspection
    assert events[0]["responseId"] == result["responseId"]
    assert events[0]["projectId"] == str(KF_01)

    await answer_ok(client, inspection, item("coating_dft", 180))  # still failing
    assert len(await failed_events(db)) == 1
    passed = (await answer_ok(client, inspection, item("coating_dft", 300)))[0]
    assert passed["failed"] is False
    await answer_ok(client, inspection, item("coating_dft", 190))  # fails again
    assert len(await failed_events(db)) == 2


# --- validation: an invalid batch writes nothing --------------------------------------------------


async def test_invalid_answers_are_refused_with_their_paths(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    not_an_option = await answer(client, inspection, item("surface_prep", "sa1"))
    assert not_an_option.status_code == 422, not_an_option.text
    assert not_an_option.json()["code"] == "ANSWER_INVALID"
    assert not_an_option.json()["messageKey"] == "inspection.error.answer_invalid"
    assert not_an_option.json()["errors"] == [{"path": "answers[0].value", "code": "NOT_AN_OPTION"}]

    wrong_type = await answer(client, inspection, item("coating_dft", "thick"))
    assert wrong_type.status_code == 422
    assert wrong_type.json()["errors"] == [{"path": "answers[0].value", "code": "WRONG_TYPE"}]

    unknown = await answer(client, inspection, item("nozzle_size", 3))
    assert unknown.status_code == 422, unknown.text
    assert unknown.json()["code"] == "UNKNOWN_FIELD"
    assert unknown.json()["errors"] == [{"path": "answers[0].fieldKey", "code": "UNKNOWN_FIELD"}]

    await answer_ok(client, inspection, item("surface_prep", "sa2_5"))
    hidden = await answer(client, inspection, item("remarks", "x"))
    assert hidden.status_code == 422, hidden.text
    assert hidden.json()["code"] == "FIELD_NOT_VISIBLE"

    before = await responses(db)
    mixed = await answer(client, inspection, item("coating_dft", 300), item("surface_prep", "sa1"))
    assert mixed.status_code == 422
    assert mixed.json()["errors"] == [{"path": "answers[1].value", "code": "NOT_AN_OPTION"}]
    assert await responses(db) == before


async def test_an_answer_in_the_same_batch_can_make_a_field_visible(
    client: httpx.AsyncClient, inspection: str
) -> None:
    results = await answer_ok(
        client, inspection, item("surface_prep", "sa3"), item("remarks", "blasted twice")
    )
    assert [r["created"] for r in results] == [True, True]


async def test_a_batch_repeating_a_field_or_client_id_is_refused(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    twice = await answer(client, inspection, item("coating_dft", 300), item("coating_dft", 310))
    assert twice.status_code == 422, twice.text
    assert twice.json()["code"] == "DUPLICATE_ANSWER"
    assert twice.json()["errors"] == [{"path": "answers[1]", "code": "DUPLICATE_ANSWER"}]
    same_id = uuid.uuid4()
    reused = await answer(
        client, inspection, item("coating_dft", 300, same_id), item("surface_prep", "sa3", same_id)
    )
    assert reused.status_code == 422 and reused.json()["code"] == "DUPLICATE_ANSWER"
    assert await responses(db) == 0


async def test_an_answer_can_be_cleared(client: httpx.AsyncClient, inspection: str) -> None:
    await answer_ok(client, inspection, item("surface_prep", "sa3"))
    cleared = (await answer_ok(client, inspection, item("surface_prep", None)))[0]
    assert cleared["failed"] is False
    body = (await client.get(f"{INSPECTIONS}/{inspection}/responses", headers=VIEWER)).json()
    assert body["answers"]["surface_prep"]["value"] is None
    assert "surface_prep" in body["evaluation"]["missingRequired"]


# --- who may answer, and when (ADR 0041 §6) -------------------------------------------------------


async def test_answers_are_refused_outside_the_editable_states(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await move(client, inspection, "assign", SUPERVISOR_ID)  # in_progress -> assigned
    refused = await answer(client, inspection, item("coating_dft", 300))
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "INSPECTION_NOT_EDITABLE"
    assert refused.json()["state"] == "assigned"
    assert refused.json()["messageKey"] == "inspection.error.not_editable"
    assert await responses(db) == 0


async def test_a_viewer_cannot_answer(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    refused = await answer(client, inspection, item("coating_dft", 300), headers=VIEWER)
    assert refused.status_code == 403, refused.text
    assert await responses(db) == 0


async def test_the_lifecycle_decides_who_may_answer(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await answer_ok(client, inspection, item("coating_dft", 300))  # in_progress

    await move(client, inspection, "sitesync_checkout", INSPECTOR_ID)  # checked out to SiteSync
    sitesync = await answer(client, inspection, item("coating_dft", 301))
    assert sitesync.status_code == 409, sitesync.text
    assert sitesync.json()["state"] == "in_progress_sitesync"

    await move(client, inspection, "sitesync_check_in", INSPECTOR_ID)
    await answer_ok(client, inspection, item("coating_dft", 302))  # inspector_review

    await move(client, inspection, "request_supervisor_review", INSPECTOR_ID)
    inspector = await answer(client, inspection, item("coating_dft", 303))
    assert inspector.status_code == 403, inspector.text
    assert inspector.json()["code"] == "REVIEW_PERMISSION_REQUIRED"
    supervisor = await answer(client, inspection, item("surface_prep", "sa3"), headers=SUPERVISOR)
    assert supervisor.status_code == 200, supervisor.text
    body = (await client.get(f"{INSPECTIONS}/{inspection}/responses", headers=VIEWER)).json()
    assert body["answers"]["surface_prep"]["respondedBy"] == str(SUPERVISOR_ID)

    await move(client, inspection, "request_rework", SUPERVISOR_ID, comment="redo the DFT")
    await answer_ok(client, inspection, item("coating_dft", 304))  # rework_required

    await move(client, inspection, "request_supervisor_review", INSPECTOR_ID)
    await move(client, inspection, "mark_performed", SUPERVISOR_ID)
    before = await responses(db)
    for headers in (INSPECTOR, SUPERVISOR):
        done = await answer(client, inspection, item("coating_dft", 305), headers=headers)
        assert done.status_code == 409, done.text
        assert done.json()["code"] == "INSPECTION_NOT_EDITABLE"
    assert await responses(db) == before


# --- guard facts and the published interface ------------------------------------------------------


async def test_the_facts_provider_counts_the_answers(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    async def facts() -> dict[str, Any]:  # system: the project-scope policy shows the row
        async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
            return await workflow.facts(conn, UUID(inspection))

    await answer_ok(client, inspection, item("coating_dft", 200))
    found = await facts()
    assert found["missingRequiredCount"] == 1
    assert found["answeredCount"] == 1
    assert found["failedCount"] == 1
    assert found["invalidCount"] == 0
    assert found["kind"] == "inspection"

    await answer_ok(client, inspection, item("surface_prep", "sa2_5"))
    found = await facts()
    assert found["missingRequiredCount"] == 0
    assert found["answeredCount"] == 2


async def test_the_published_interface_matches_the_route(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await answer_ok(client, inspection, item("coating_dft", 260), item("surface_prep", "sa3"))
    route = (await client.get(f"{INSPECTIONS}/{inspection}/responses", headers=VIEWER)).json()
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        current = await InspectionsApi().get_current_responses(conn, UUID(inspection))
    assert current is not None
    assert current.model_dump(mode="json", by_alias=True) == route


# --- the database: append-only, partitions, RLS ---------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE inspection_responses SET value = '1'",
        "DELETE FROM inspection_responses",
        "TRUNCATE inspection_responses",
    ],
)
async def test_aip_app_can_never_change_an_answer(
    client: httpx.AsyncClient, db: TenantDb, inspection: str, statement: str
) -> None:
    await answer_ok(client, inspection, item("coating_dft", 300))
    with pytest.raises(DBAPIError) as caught:
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text(statement))
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"  # insufficient privilege
    assert await responses(db) == 1


async def test_partitions_are_kept_ahead_and_rows_stay_readable(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    settings = await su_fetch(db, "SELECT table_name FROM partition_settings")
    assert ("inspection_responses",) in [tuple(r) for r in settings]
    result = (await answer_ok(client, inspection, item("coating_dft", 300)))[0]

    # The job's per-table step, as aip_jobs, for this table only.
    engine = create_app_engine(
        EngineSettings(url=db.db.role_url(JOBS), pool_size=2, max_overflow=0)
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT aip_ensure_partitions('inspection_responses', 3)")
            )
    finally:
        await engine.dispose()

    this_month = datetime.now(UTC).date().replace(day=1)
    expected = partition_name("inspection_responses", this_month)
    partitions = await su_fetch(
        db,
        "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid"
        " WHERE i.inhparent = 'inspection_responses'::regclass",
    )
    assert expected in {r[0] for r in partitions}
    async with db.with_tenant(TENANT_A_ID) as conn:
        found = await conn.execute(
            text("SELECT id FROM inspection_responses WHERE id = :id"),
            {"id": UUID(result["responseId"])},
        )
        assert found.scalar_one() == UUID(result["responseId"])


async def test_another_tenant_sees_no_answers(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await answer_ok(client, inspection, item("coating_dft", 300))
    async with db.with_tenant(TENANT_A_ID) as conn:
        mine = await conn.execute(text("SELECT count(*) FROM inspection_current_responses"))
        assert mine.scalar_one() == 1
    async with db.with_tenant(TENANT_B_ID) as conn:
        theirs = await conn.execute(text("SELECT count(*) FROM inspection_current_responses"))
        assert theirs.scalar_one() == 0

    for path in ("/responses", "/responses/coating_dft/history"):
        seen = await client.get(f"{INSPECTIONS}/{inspection}{path}", headers=BOB)
        assert seen.status_code == 404, (path, seen.text)
    posted = await client.post(
        f"{INSPECTIONS}/{inspection}/responses",
        json={"answers": [item("coating_dft", 1)]},
        headers=signed(BOB_ID, TENANT_B_ID),
    )
    assert posted.status_code == 404, posted.text
    assert await responses(db) == 1
