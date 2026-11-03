"""INSPECTIONS-10 integration tests: section and report acknowledgements lock answers, only the
person who ticked can untick, Request Rework clears every tick, and the tables are append-only.

The app connects as ``aip_app`` (RLS on); users and grants come from the INSPECTIONS-01 conftest.
The inspector (``INSPECTOR``) and a second inspector (``LEAD``, taking over in the handover case)
answer and acknowledge; the supervisor also edits during review (``approvals.inspection.review``).
The form has two sections: ``prep`` (required ``surface_prep``) and ``coating`` (required ``dft_1``
and ``dft_2``, and the section rule ``avg_dft_ok``: both readings at least 250). The guarded submit
transitions themselves are in ``test_submit_preset_db.py``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import Outbox, TenantDb

from aip.modules.inspections.api import InspectionsApi
from aip.platform.db.scope import run_as_system
from aip.platform.events.dispatcher import DispatchSettings, dispatch_batch
from aip.platform.events.subscribers import subscribers

from .conftest import (
    ALICE,
    BOB,
    INSPECTOR,
    INSPECTOR_ID,
    KF_01,
    LEAD,
    LEAD_ID,
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
INSPECTIONS_ONLY = subscribers.for_modules(["inspections"])

SECTIONS_FORM: dict[str, Any] = {
    "schemaVersion": 2,
    "sections": [
        {
            "key": "prep",
            "label": "Surface preparation",
            "fields": [
                {
                    "key": "surface_prep",
                    "type": "dropdown",
                    "label": "Surface preparation",
                    "required": True,
                    "options": [
                        {"value": "sa2_5", "label": "Sa 2.5"},
                        {"value": "sa3", "label": "Sa 3"},
                    ],
                }
            ],
        },
        {
            "key": "coating",
            "label": "Coating",
            "fields": [
                {"key": "dft_1", "type": "number", "label": "DFT 1", "required": True},
                {"key": "dft_2", "type": "number", "label": "DFT 2", "required": True},
            ],
            "rules": [
                {
                    "key": "avg_dft_ok",
                    "expr": {
                        "and": [
                            {">=": [{"var": "answers.dft_1"}, 250]},
                            {">=": [{"var": "answers.dft_2"}, 250]},
                        ]
                    },
                    "label": "Every DFT reading must be at least 250",
                }
            ],
        },
    ],
}


@pytest.fixture(autouse=True)
def responders(grants: GrantTable) -> GrantTable:
    grants.by_user[LEAD_ID] |= {"inspection.respond", "approvals.inspection.execute"}
    grants.by_user[SUPERVISOR_ID] |= {"inspection.respond", REVIEW}
    return grants


async def new_inspection(
    client: httpx.AsyncClient, db: TenantDb, *, has_supervisor_review: bool = True
) -> str:
    """An inspection of the two-section form, moved to ``in_progress``; returns its id."""
    await install_preset(db)
    asset_id = await create_asset(db)
    uploaded = await client.post(
        "/api/v1/forms/templates",
        json={
            "code": f"sections-{uuid.uuid4().hex[:8]}",
            "name": "Coating sections",
            "kind": "inspection",
            "schema": SECTIONS_FORM,
            "hasSupervisorReview": has_supervisor_review,
        },
        headers=ALICE,
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
    assert created.json()["hasSupervisorReview"] is has_supervisor_review
    inspection_id: str = created.json()["id"]
    await move(client, inspection_id, "ready", SUPERVISOR_ID)
    await move(client, inspection_id, "inspect", INSPECTOR_ID)
    return inspection_id


@pytest.fixture
async def inspection(client: httpx.AsyncClient, db: TenantDb) -> str:
    return await new_inspection(client, db)


async def move(
    client: httpx.AsyncClient, inspection_id: str, action: str, user: UUID, **extra: Any
) -> httpx.Response:
    response = await client.post(
        f"{INSPECTIONS}/{inspection_id}/transition",
        json={"action": action, **extra},
        headers=signed(user),
    )
    assert response.status_code == 200, (action, response.text)
    return response


async def answer(
    client: httpx.AsyncClient,
    inspection_id: str,
    headers: dict[str, str] = INSPECTOR,
    **values: Any,
) -> httpx.Response:
    items = [
        {"fieldKey": key, "value": value, "clientId": str(uuid.uuid4())}
        for key, value in values.items()
    ]
    return await client.post(
        f"{INSPECTIONS}/{inspection_id}/responses", json={"answers": items}, headers=headers
    )


async def answer_ok(
    client: httpx.AsyncClient, inspection_id: str, headers: dict[str, str] = INSPECTOR, **v: Any
) -> None:
    response = await answer(client, inspection_id, headers, **v)
    assert response.status_code == 200, response.text


def section_url(inspection_id: str, key: str) -> str:
    return f"{INSPECTIONS}/{inspection_id}/sections/{key}/acknowledgement"


def report_url(inspection_id: str) -> str:
    return f"{INSPECTIONS}/{inspection_id}/report/acknowledgement"


async def tick(
    client: httpx.AsyncClient, inspection_id: str, key: str, headers: dict[str, str] = INSPECTOR
) -> httpx.Response:
    return await client.post(section_url(inspection_id, key), headers=headers)


async def untick(
    client: httpx.AsyncClient, inspection_id: str, key: str, headers: dict[str, str] = INSPECTOR
) -> httpx.Response:
    return await client.delete(section_url(inspection_id, key), headers=headers)


async def state(client: httpx.AsyncClient, inspection_id: str) -> dict[str, Any]:
    response = await client.get(f"{INSPECTIONS}/{inspection_id}/acknowledgements", headers=VIEWER)
    assert response.status_code == 200, response.text
    return response.json()


async def history(db: TenantDb, inspection_id: str) -> list[tuple[str, str | None, str, UUID]]:
    rows = await su_fetch(
        db,
        "SELECT scope, section_key, action, actor FROM inspection_acknowledgements"
        " WHERE inspection_id = $1 ORDER BY created_at, id",
        UUID(inspection_id),
    )
    return [(r[0], r[1], r[2], r[3]) for r in rows]


async def acknowledgements(db: TenantDb) -> int:
    return await count(db, "SELECT count(*) FROM inspection_acknowledgements")


async def complete_everything(client: httpx.AsyncClient, inspection_id: str) -> None:
    await answer_ok(client, inspection_id, surface_prep="sa2_5", dft_1=300, dft_2=310)
    for key in ("prep", "coating"):
        assert (await tick(client, inspection_id, key)).status_code == 200
    assert (await client.post(report_url(inspection_id), headers=INSPECTOR)).status_code == 200


# --- a section tick validates and locks ----------------------------------------------------------


async def test_a_section_is_ticked_only_when_complete_and_then_locks_its_answers(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await answer_ok(client, inspection, dft_1=300)
    missing = await tick(client, inspection, "coating")
    assert missing.status_code == 422, missing.text
    assert missing.json()["code"] == "SECTION_INCOMPLETE"
    assert missing.json()["messageKey"] == "inspection.error.section_incomplete"
    assert missing.json()["missingRequired"] == ["dft_2"]

    await answer_ok(client, inspection, dft_2=200)
    low = await tick(client, inspection, "coating")
    assert low.status_code == 422, low.text
    assert (low.json()["missingRequired"], low.json()["ruleFailures"]) == ([], ["avg_dft_ok"])
    assert await acknowledgements(db) == 0

    await answer_ok(client, inspection, dft_2=260)
    ticked = await tick(client, inspection, "coating")
    assert ticked.status_code == 200, ticked.text
    coating = ticked.json()["sections"]["coating"]
    assert (coating["locked"], coating["by"]) == (True, str(INSPECTOR_ID))
    assert ticked.json()["sections"]["prep"] == {"locked": False, "by": None, "at": None}

    before = await count(db, "SELECT count(*) FROM inspection_responses")
    locked = await answer(client, inspection, dft_1=310)
    assert locked.status_code == 409, locked.text
    assert (locked.json()["code"], locked.json()["sectionKey"]) == ("SECTION_LOCKED", "coating")
    # One locked field refuses the whole batch, the open section's answer included.
    batch = await answer(client, inspection, surface_prep="sa3", dft_2=300)
    assert batch.status_code == 409 and batch.json()["code"] == "SECTION_LOCKED"
    assert await count(db, "SELECT count(*) FROM inspection_responses") == before
    await answer_ok(client, inspection, surface_prep="sa3")  # another section stays open

    again = await tick(client, inspection, "coating")
    assert again.status_code == 409 and again.json()["code"] == "SECTION_ALREADY_ACKNOWLEDGED"


async def test_unknown_and_malformed_sections_are_refused(
    client: httpx.AsyncClient, inspection: str
) -> None:
    unknown = await tick(client, inspection, "nope")
    assert unknown.status_code == 422 and unknown.json()["code"] == "UNKNOWN_SECTION"
    malformed = await tick(client, inspection, "Not-A-Key")
    assert malformed.status_code == 422, malformed.text
    extra = await client.post(section_url(inspection, "prep"), json={"x": 1}, headers=INSPECTOR)
    assert extra.status_code == 422, extra.text


async def test_a_viewer_cannot_tick(client: httpx.AsyncClient, inspection: str) -> None:
    await answer_ok(client, inspection, surface_prep="sa2_5")
    refused = await tick(client, inspection, "prep", headers=VIEWER)
    assert refused.status_code == 403, refused.text


async def test_the_report_tick_needs_every_section_and_locks_all_answers(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await answer_ok(client, inspection, surface_prep="sa2_5", dft_1=300, dft_2=300)
    assert (await tick(client, inspection, "prep")).status_code == 200
    early = await client.post(report_url(inspection), headers=INSPECTOR)
    assert early.status_code == 422, early.text
    assert early.json()["code"] == "SECTIONS_NOT_ACKNOWLEDGED"
    assert early.json()["sectionKeys"] == ["coating"]

    assert (await tick(client, inspection, "coating")).status_code == 200
    report = await client.post(report_url(inspection), headers=INSPECTOR)
    assert report.status_code == 200, report.text
    assert report.json()["report"]["locked"] is True

    locked = await answer(client, inspection, surface_prep="sa3")
    assert locked.status_code == 409 and locked.json()["code"] == "REPORT_LOCKED"
    held = await untick(client, inspection, "prep")
    assert held.status_code == 409 and held.json()["code"] == "REPORT_ACKNOWLEDGED"

    # Unticking the report lets the sections be unticked again.
    unticked = await client.delete(report_url(inspection), headers=INSPECTOR)
    assert unticked.status_code == 200 and unticked.json()["report"]["locked"] is False
    assert (await untick(client, inspection, "prep")).status_code == 200
    await answer_ok(client, inspection, surface_prep="sa3")

    events = await su_fetch(
        db,
        "SELECT event_name, payload FROM domain_events"
        " WHERE event_name LIKE 'inspection.%acknowledged' ORDER BY occurred_at, id",
    )
    payloads = [(r[0], r[1] if isinstance(r[1], dict) else json.loads(r[1])) for r in events]
    assert payloads == [
        (
            "inspection.section_acknowledged",
            {
                "inspectionId": inspection,
                "scope": "section",
                "sectionKey": key,
                "actor": str(INSPECTOR_ID),
            },
        )
        for key in ("prep", "coating")
    ] + [
        (
            "inspection.report_acknowledged",
            {
                "inspectionId": inspection,
                "scope": "report",
                "sectionKey": None,
                "actor": str(INSPECTOR_ID),
            },
        )
    ]


# --- handover: only the person who ticked can untick ---------------------------------------------


async def test_only_the_ticker_unticks_even_after_a_handover(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await answer_ok(client, inspection, surface_prep="sa2_5")
    assert (await tick(client, inspection, "prep")).status_code == 200
    await move(client, inspection, "assign", SUPERVISOR_ID)  # hand over
    await move(client, inspection, "inspect", LEAD_ID)

    refused = await untick(client, inspection, "prep", headers=LEAD)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "NOT_ACKNOWLEDGER"
    not_ticked = await untick(client, inspection, "coating", headers=LEAD)
    assert not_ticked.status_code == 403 and not_ticked.json()["code"] == "NOT_ACKNOWLEDGER"

    await answer_ok(client, inspection, LEAD, dft_1=300, dft_2=300)
    assert (await tick(client, inspection, "coating", headers=LEAD)).status_code == 200
    assert (await client.post(report_url(inspection), headers=LEAD)).status_code == 200
    await move(client, inspection, "request_supervisor_review", LEAD_ID)

    for headers in (INSPECTOR, LEAD):  # from supervisor review on, nobody unticks anything
        late = await untick(client, inspection, "coating", headers=headers)
        assert late.status_code == 409, late.text
        assert late.json()["code"] == "INSPECTION_NOT_EDITABLE"
        report = await client.delete(report_url(inspection), headers=headers)
        assert report.status_code == 409 and report.json()["code"] == "INSPECTION_NOT_EDITABLE"

    found = await state(client, inspection)
    assert found["sections"]["prep"]["by"] == str(INSPECTOR_ID)
    assert found["sections"]["coating"]["by"] == str(LEAD_ID)
    assert found["report"]["by"] == str(LEAD_ID)
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        published = await InspectionsApi().get_acknowledgements(conn, UUID(inspection))
    assert published is not None
    assert published.model_dump(mode="json", by_alias=True) == found


# --- supervisor review, rework --------------------------------------------------------------------


async def test_a_supervisor_with_review_edits_through_the_ticks(
    client: httpx.AsyncClient, grants: GrantTable, inspection: str
) -> None:
    await complete_everything(client, inspection)
    await move(client, inspection, "request_supervisor_review", INSPECTOR_ID)

    edited = await answer(client, inspection, SUPERVISOR, dft_1=320)
    assert edited.status_code == 200, edited.text
    current = (await client.get(f"{INSPECTIONS}/{inspection}/responses", headers=VIEWER)).json()
    assert current["answers"]["dft_1"]["respondedBy"] == str(SUPERVISOR_ID)

    grants.by_user[SUPERVISOR_ID] -= {REVIEW}
    refused = await answer(client, inspection, SUPERVISOR, dft_1=330)
    assert refused.status_code == 403, refused.text


async def test_request_rework_clears_every_tick_and_reopens_the_answers(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await complete_everything(client, inspection)
    await move(client, inspection, "request_supervisor_review", INSPECTOR_ID)
    await move(client, inspection, "request_rework", SUPERVISOR_ID, comment="redo the DFT")

    found = await state(client, inspection)
    assert [s["locked"] for s in found["sections"].values()] == [False, False]
    assert found["report"]["locked"] is False
    cleared = [h for h in await history(db, inspection) if h[2] == "cleared_by_rework"]
    assert sorted((h[0], h[1]) for h in cleared) == [
        ("report", None),
        ("section", "coating"),
        ("section", "prep"),
    ]
    assert {h[3] for h in cleared} == {SUPERVISOR_ID}
    await answer_ok(client, inspection, dft_1=280)

    # The rework is ticked and handed in again; nothing was ever deleted.
    for key in ("prep", "coating"):
        assert (await tick(client, inspection, key)).status_code == 200
    assert (await client.post(report_url(inspection), headers=INSPECTOR)).status_code == 200
    await move(client, inspection, "request_supervisor_review", INSPECTOR_ID)
    assert len(await history(db, inspection)) == 3 + 3 + 3


async def dispatch_all(outbox: Outbox) -> None:
    settings = DispatchSettings(batch_size=100)
    while (await dispatch_batch(outbox.jobs, outbox.app, INSPECTIONS_ONLY, settings)).claimed:
        pass


async def test_rework_through_approvals_is_unlocked_before_and_after_the_subscriber(
    client: httpx.AsyncClient, db: TenantDb, inspection: str, outbox: Outbox
) -> None:
    await complete_everything(client, inspection)
    await move(client, inspection, "request_supervisor_review", INSPECTOR_ID)
    instance_id = (await client.get(f"{INSPECTIONS}/{inspection}", headers=VIEWER)).json()[
        "workflowInstanceId"
    ]
    reworked = await client.post(
        f"/api/v1/approvals/instances/{instance_id}/transition",
        json={"action": "request_rework", "comment": "redo"},
        headers=signed(SUPERVISOR_ID),
    )
    assert reworked.status_code == 200, reworked.text

    # Before the subscriber: the ticks predate the rework, so nothing is locked.
    assert (await state(client, inspection))["report"]["locked"] is False
    assert [h for h in await history(db, inspection) if h[2] == "cleared_by_rework"] == []
    await answer_ok(client, inspection, dft_1=290)
    assert (await tick(client, inspection, "prep")).status_code == 200  # a tick during rework

    # The subscriber clears the ticks from before the rework; the tick made since stands.
    await dispatch_all(outbox)
    cleared = [h for h in await history(db, inspection) if h[2] == "cleared_by_rework"]
    assert sorted((h[0], h[1]) for h in cleared) == [("report", None), ("section", "coating")]
    found = await state(client, inspection)
    assert found["sections"]["prep"]["locked"] is True
    assert found["sections"]["coating"]["locked"] is False
    await dispatch_all(outbox)  # a replay changes nothing
    assert len([h for h in await history(db, inspection) if h[2] == "cleared_by_rework"]) == 2


# --- the database: append-only, partitions, RLS ---------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE inspection_acknowledgements SET action = 'untick'",
        "DELETE FROM inspection_acknowledgements",
        "TRUNCATE inspection_acknowledgements",
    ],
)
async def test_aip_app_can_never_change_an_acknowledgement(
    client: httpx.AsyncClient, db: TenantDb, inspection: str, statement: str
) -> None:
    await answer_ok(client, inspection, surface_prep="sa2_5")
    assert (await tick(client, inspection, "prep")).status_code == 200
    with pytest.raises(DBAPIError) as caught:
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(text(statement))
    assert getattr(caught.value.orig, "sqlstate", None) == "42501"  # insufficient privilege
    assert await acknowledgements(db) == 1
    settings = await su_fetch(db, "SELECT table_name FROM partition_settings")
    assert ("inspection_acknowledgements",) in [tuple(r) for r in settings]


async def test_another_tenant_sees_no_acknowledgements(
    client: httpx.AsyncClient, db: TenantDb, inspection: str
) -> None:
    await answer_ok(client, inspection, surface_prep="sa2_5")
    assert (await tick(client, inspection, "prep")).status_code == 200
    async with db.with_tenant(TENANT_A_ID) as conn:
        mine = await conn.execute(text("SELECT count(*) FROM inspection_current_acknowledgements"))
        assert mine.scalar_one() == 1
    async with db.with_tenant(TENANT_B_ID) as conn:
        theirs = await conn.execute(
            text("SELECT count(*) FROM inspection_current_acknowledgements")
        )
        assert theirs.scalar_one() == 0

    bob = signed(BOB_ID, TENANT_B_ID)
    seen = await client.get(f"{INSPECTIONS}/{inspection}/acknowledgements", headers=BOB)
    assert seen.status_code == 404, seen.text
    for method in ("POST", "DELETE"):
        for url in (section_url(inspection, "prep"), report_url(inspection)):
            response = await client.request(method, url, headers=bob)
            assert response.status_code == 404, (method, url, response.text)
    assert await acknowledgements(db) == 1
