"""IDENTITY-04 Part D (ADR 0010) on real Postgres: the ``signoff_policy`` table, its admin API and
``check_signoff_assurance`` reading it."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.identity import repository as repo
from aip.modules.identity.api import SessionFacts, SignoffContext, check_signoff_assurance
from aip.modules.identity.assurance import effective_policy

from .conftest import ALICE, BOB, GrantTable, principal_headers, su_fetch

POLICY = "/api/v1/identity/signoff-policy"


def _ctx(minutes_ago: float, aal: int = 2) -> SignoffContext:
    now = datetime.now(UTC)
    return SignoffContext(
        session=SessionFacts(
            aal=aal, amr=["pwd", "otp"], authenticated_at=now - timedelta(minutes=minutes_ago)
        ),
        aal2_available=True,
        now=now,
    )


async def test_kaefer_demo_has_the_seeded_defaults(db: TenantDb) -> None:
    async with db.with_tenant(TENANT_A_ID) as conn:
        rows = await repo.list_signoff_policies(conn)
    assert [(r.action_code, r.min_aal, r.step_up_max_age_min) for r in rows] == [
        ("hold_point.release", 2, 10),
        ("itp.signoff", 2, 10),
        ("record.seal", 2, 10),
        ("witness.countersign", 2, 10),
    ]


async def test_rls_and_the_default_for_a_missing_row(db: TenantDb) -> None:
    async with db.with_tenant(TENANT_B_ID) as conn:
        assert await repo.list_signoff_policies(conn) == []  # kaefer-demo's rows are invisible
        assert await effective_policy(conn, "hold_point.release") == (2, 10)
    async with db.no_tenant() as conn:
        assert await repo.list_signoff_policies(conn) == []


async def test_check_signoff_assurance_reads_the_policy(db: TenantDb) -> None:
    async with db.with_tenant(TENANT_A_ID) as conn:
        await repo.upsert_signoff_policy(
            conn, action_code="itp.signoff", min_aal=2, step_up_max_age_min=30, updated_by=ALICE_ID
        )
        relaxed = await check_signoff_assurance(conn, _ctx(20), "itp.signoff")
        strict = await check_signoff_assurance(conn, _ctx(20), "hold_point.release")
    assert relaxed.decision == "allow" and relaxed.max_age_min == 30
    assert strict.decision == "step_up_required" and strict.max_age_min == 10
    assert relaxed.assurance.method == "totp"


async def test_get_lists_rows_and_defaults(client: httpx.AsyncClient) -> None:
    r = await client.get(POLICY, headers=BOB)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert {i["actionCode"] for i in items} == {
        "hold_point.release",
        "itp.signoff",
        "record.seal",
        "witness.countersign",
    }
    assert all(i["isDefault"] and i["minAal"] == 2 for i in items)
    mine = (await client.get(POLICY, headers=ALICE)).json()["items"]
    assert not any(i["isDefault"] for i in mine)


async def test_lowering_a_minimum_needs_a_step_up_and_is_audited(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    body = {"actionCode": "hold_point.release", "minAal": 1, "stepUpMaxAgeMin": 10}
    stale = principal_headers(TENANT_A_ID, ALICE_ID, minutes_ago=30)
    r = await client.put(POLICY, json=body, headers=stale)
    assert r.status_code == 401, r.text
    assert r.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    assert await su_fetch(db, "SELECT count(*) FROM domain_events") == [(0,)]

    r = await client.put(POLICY, json=body, headers=ALICE)
    assert r.status_code == 200, r.text
    hold = next(i for i in r.json()["items"] if i["actionCode"] == "hold_point.release")
    assert (hold["minAal"], hold["isDefault"]) == (1, False)
    events = await su_fetch(
        db, "SELECT event_name, payload, tenant_id, actor_id FROM domain_events"
    )
    assert len(events) == 1
    name, payload, tenant, actor = events[0]
    assert (name, tenant, actor) == ("identity.signoff_policy.changed", TENANT_A_ID, ALICE_ID)
    body = json.loads(payload) if isinstance(payload, str) else payload
    assert body == {
        "actionCode": "hold_point.release",
        "before": {"minAal": 2, "stepUpMaxAgeMin": 10},
        "after": {"minAal": 1, "stepUpMaxAgeMin": 10},
    }


async def test_tightening_needs_no_step_up_but_widening_the_window_does(
    client: httpx.AsyncClient,
) -> None:
    stale = principal_headers(TENANT_A_ID, ALICE_ID, minutes_ago=30)
    narrower = {"actionCode": "record.seal", "minAal": 2, "stepUpMaxAgeMin": 5}
    assert (await client.put(POLICY, json=narrower, headers=stale)).status_code == 200
    wider = {"actionCode": "record.seal", "minAal": 2, "stepUpMaxAgeMin": 60}
    r = await client.put(POLICY, json=wider, headers=stale)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    assert (await client.put(POLICY, json=wider, headers=ALICE)).status_code == 200


async def test_values_outside_the_range_are_422(client: httpx.AsyncClient) -> None:
    for bad in (
        {"actionCode": "record.seal", "minAal": 3},
        {"actionCode": "record.seal", "minAal": 0},
        {"actionCode": "record.seal", "minAal": 2, "stepUpMaxAgeMin": 61},
        {"actionCode": "record.seal", "minAal": 2, "stepUpMaxAgeMin": 0},
        {"actionCode": "Not A Code", "minAal": 2},
    ):
        assert (await client.put(POLICY, json=bad, headers=ALICE)).status_code == 422, bad


async def test_changing_the_policy_needs_its_permission(
    client: httpx.AsyncClient, grants: GrantTable
) -> None:
    grants.by_user[ALICE_ID] = {"identity.signoff_policy.read"}
    body = {"actionCode": "record.seal", "minAal": 2}
    r = await client.put(POLICY, json=body, headers=ALICE)
    assert r.status_code == 403
    assert r.json()["permission"] == "identity.signoff_policy.manage"
