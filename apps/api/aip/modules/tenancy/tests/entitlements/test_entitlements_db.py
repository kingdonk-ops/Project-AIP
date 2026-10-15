"""ENT-01 integration tests: entitlements on real Postgres through ``aip_app`` and the API."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.tenancy.api import ensure_within_limit, requires_entitlement
from aip.modules.tenancy.entitlements.service import EntitlementService
from aip.modules.tenancy.entitlements.usage import UsageFigures
from aip.modules.tenancy.seed import seed
from aip.platform.access import authenticated
from aip.platform.http import DomainError

from .conftest import ALICE, BOB, CAROL, FakeClock, su_execute, su_fetch

PLATFORM = "/api/v1/platform/tenants"


def subscription_body(plan: str = "core", **extra: Any) -> dict[str, Any]:
    return {
        "planCode": plan,
        "term": "sandbox",
        "startsOn": "2026-07-01",
        "renewalDate": "2027-06-30",
        "reason": "test set-up",
        **extra,
    }


async def put_subscription(
    client: httpx.AsyncClient, tenant: UUID, headers: dict[str, str] = CAROL, **body: Any
) -> httpx.Response:
    return await client.put(
        f"{PLATFORM}/{tenant}/subscription", json=subscription_body(**body), headers=headers
    )


async def events(db: TenantDb, change: str | None = None) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT tenant_id, actor_id, payload FROM domain_events"
        " WHERE event_name = 'tenant.entitlements_changed' ORDER BY occurred_at",
    )
    found = [{"tenant": r[0], "actor": r[1], **json.loads(r[2])} for r in rows]
    return [e for e in found if change is None or e["change"] == change]


# --- isolation --------------------------------------------------------------------------------


async def test_aip_app_sees_only_its_own_subscription(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    assert (await put_subscription(client, TENANT_A_ID, plan="professional")).status_code == 200
    assert (await put_subscription(client, TENANT_B_ID)).status_code == 200
    async with db.with_tenant(TENANT_A_ID) as conn:
        rows = (
            await conn.execute(text("SELECT tenant_id, plan_code FROM tenant_subscription"))
        ).all()
    assert [tuple(r) for r in rows] == [(TENANT_A_ID, "professional")]
    async with db.no_tenant() as conn:
        for table in ("tenant_subscription", "tenant_entitlement_override", "tenant_usage"):
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0


# --- requires_entitlement, overrides and the clock ---------------------------------------------


def add_bim_route(app: FastAPI) -> None:
    @app.get(
        "/api/v1/_test/bim",
        dependencies=[Depends(authenticated()), Depends(requires_entitlement("feature.bim"))],
    )
    async def bim() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}


async def test_override_grants_until_it_expires(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, clock: FakeClock
) -> None:
    add_bim_route(app)
    assert (await put_subscription(client, TENANT_A_ID)).status_code == 200

    denied = await client.get("/api/v1/_test/bim", headers=ALICE)
    assert denied.status_code == 403
    assert denied.json() == {"code": "NOT_ENTITLED", "key": "feature.bim"}

    expires = (clock.now + timedelta(hours=1)).isoformat()
    created = await client.post(
        f"{PLATFORM}/{TENANT_A_ID}/entitlement-overrides",
        json={"key": "feature.bim", "value": True, "reason": "pilot", "expiresAt": expires},
        headers=CAROL,
    )
    assert created.status_code == 201, created.text
    assert (await client.get("/api/v1/_test/bim", headers=ALICE)).status_code == 200

    clock.advance(timedelta(hours=2))
    assert (await client.get("/api/v1/_test/bim", headers=ALICE)).status_code == 403

    added = await events(db, "override_added")
    assert len(added) == 1
    assert added[0]["tenant"] == TENANT_A_ID  # the target tenant, not the operator's
    assert (added[0]["key"], added[0]["reason"]) == ("feature.bim", "pilot")


async def test_removing_an_override_needs_a_reason_and_is_audited(
    client: httpx.AsyncClient, db: TenantDb, service: EntitlementService
) -> None:
    await put_subscription(client, TENANT_A_ID, add_ons=["bim"])
    created = await client.post(
        f"{PLATFORM}/{TENANT_A_ID}/entitlement-overrides",
        json={"key": "feature.bim", "value": False, "reason": "contract paused"},
        headers=CAROL,
    )
    override_id = created.json()["id"]
    assert (await service.check(TENANT_A_ID, "feature.bim")).source == "override"

    url = f"{PLATFORM}/{TENANT_A_ID}/entitlement-overrides/{override_id}"
    assert (await client.delete(url, headers=CAROL)).status_code == 422  # no reason
    assert (
        await client.delete(url, params={"reason": "resumed"}, headers=CAROL)
    ).status_code == 204
    assert (await client.delete(url, params={"reason": "again"}, headers=CAROL)).status_code == 404
    decision = await service.check(TENANT_A_ID, "feature.bim")
    assert (decision.allowed, decision.source) == (True, "add_on")
    assert [e["reason"] for e in await events(db, "override_removed")] == ["resumed"]


async def test_override_values_must_match_the_key(client: httpx.AsyncClient) -> None:
    await put_subscription(client, TENANT_A_ID)
    url = f"{PLATFORM}/{TENANT_A_ID}/entitlement-overrides"
    cases = [
        ({"key": "release.new_nav", "value": True}, "INVALID_ENTITLEMENT_KEY"),
        ({"key": "feature.bim", "value": 3}, "INVALID_OVERRIDE_VALUE"),
        ({"key": "limit.projects", "value": True}, "INVALID_OVERRIDE_VALUE"),
        ({"key": "feature.bimm", "value": True}, "UNKNOWN_ENTITLEMENT_KEY"),
    ]
    for body, code in cases:
        response = await client.post(url, json={**body, "reason": "x"}, headers=CAROL)
        assert (response.status_code, response.json()["code"]) == (422, code)
    blank = await client.post(
        url, json={"key": "feature.bim", "value": True, "reason": " "}, headers=CAROL
    )
    assert blank.status_code == 422


async def test_an_operator_cannot_touch_an_unknown_tenant(client: httpx.AsyncClient) -> None:
    unknown = UUID("00000000-0000-4000-8000-0000000000ff")
    assert (await put_subscription(client, unknown)).status_code == 404


# --- limits ----------------------------------------------------------------------------------


async def test_check_limit_refuses_over_a_block_limit(
    client: httpx.AsyncClient, service: EntitlementService
) -> None:
    await put_subscription(client, TENANT_A_ID)  # core: 25 GB of storage, BLOCK
    decision = await service.check_limit(TENANT_A_ID, "limit.storage_gb", 26)
    assert (decision.allowed, decision.limit) == (False, 25)
    assert (await service.check_limit(TENANT_A_ID, "limit.storage_gb", 25)).allowed is True
    await put_subscription(client, TENANT_A_ID, plan="enterprise", seat_limits={"full": 50})
    seats = await service.check_limit(TENANT_A_ID, "limit.seats.full", 51)
    assert (seats.allowed, seats.limit, seats.action) == (True, 50, "OVERAGE")


async def test_overage_allows_and_appears_in_the_usage_snapshot(
    client: httpx.AsyncClient, db: TenantDb, service: EntitlementService, clock: FakeClock
) -> None:
    await put_subscription(client, TENANT_A_ID)  # core: 1 full seat, OVERAGE
    for total in (3, 2):
        decision = await service.check_limit(TENANT_A_ID, "limit.seats.full", total)
        assert (decision.allowed, decision.recorded) == (True, True)
    await service.snapshot_usage(TENANT_A_ID, clock.now.date())
    async with db.with_tenant(TENANT_A_ID) as conn:
        raw = (await conn.execute(text("SELECT over_limit FROM tenant_usage"))).scalar_one()
    assert raw["limit.seats.full"] == {"action": "OVERAGE", "limit": 1, "peak": 3}


async def test_warn_allows_and_records(
    client: httpx.AsyncClient, db: TenantDb, service: EntitlementService
) -> None:
    await put_subscription(client, TENANT_A_ID)  # core: 5 GB database, WARN
    decision = await service.check_limit(TENANT_A_ID, "limit.db_gb", 6)
    assert (decision.allowed, decision.action, decision.recorded) == (True, "WARN", True)
    async with db.with_tenant(TENANT_A_ID) as conn:
        raw = (await conn.execute(text("SELECT over_limit FROM tenant_usage"))).scalar_one()
    assert raw["limit.db_gb"]["peak"] == 6


async def test_full_storage_refuses_an_upload_but_reads_never_check(
    client: httpx.AsyncClient, service: EntitlementService
) -> None:
    await put_subscription(client, TENANT_A_ID)  # core: 25 GB, BLOCK
    with pytest.raises(DomainError) as refused:
        await ensure_within_limit(service, TENANT_A_ID, "limit.storage_gb", current=25)
    assert refused.value.code == "LIMIT_REACHED"
    assert refused.value.extra == {"gate": "limit.storage_gb", "limit": 25, "current": 25}
    # An export or a read never calls a limit check; plan-and-usage still answers.
    assert (await client.get("/api/v1/settings/plan-and-usage", headers=ALICE)).status_code == 200


# --- caching and the entitlement version --------------------------------------------------------


async def test_a_version_bump_invalidates_cached_decisions(
    app: FastAPI, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    await put_subscription(client, TENANT_A_ID)
    reader = EntitlementService(clock=clock)  # another process: its own cache
    assert (await reader.check(TENANT_A_ID, "feature.bim")).allowed is False
    assert (await reader.check(TENANT_A_ID, "feature.sso")).allowed is False
    assert reader.loads == 1  # the second check came from the cache

    await put_subscription(client, TENANT_A_ID, add_ons=["bim"])  # written by the app's service
    assert (await reader.check(TENANT_A_ID, "feature.bim")).allowed is True
    assert reader.loads == 2


# --- usage snapshot and the database-size estimate ----------------------------------------------


class FakeUsage:
    async def collect(self, conn: AsyncConnection, tenant_id: UUID) -> UsageFigures:
        return UsageFigures(active_users={"staff": 12, "field": 40, "portal": 3})


async def test_snapshot_usage_is_idempotent(db: TenantDb, clock: FakeClock) -> None:
    service = EntitlementService(connect=db.with_tenant, clock=clock, usage_sources=(FakeUsage(),))
    for _ in range(2):
        await service.snapshot_usage(TENANT_A_ID, date(2026, 10, 1))
    async with db.with_tenant(TENANT_A_ID) as conn:
        rows = (await conn.execute(text("SELECT period, active_users FROM tenant_usage"))).all()
    assert [tuple(r) for r in rows] == [
        (date(2026, 10, 1), {"staff": 12, "field": 40, "portal": 3})
    ]


async def test_db_estimates_follow_the_row_ratio(db: TenantDb, clock: FakeClock) -> None:
    padding = "x" * 4000

    def projects(tenant: UUID, count: int) -> str:
        values = ", ".join(
            f"(gen_random_uuid(), '{tenant}', 'P{i:03d}', '{padding}', 'draft')"
            for i in range(count)
        )
        return f"INSERT INTO projects (id, tenant_id, code, name, status) VALUES {values}"

    await su_execute(db, projects(TENANT_A_ID, 10))
    await su_execute(db, projects(TENANT_B_ID, 20))
    service = EntitlementService(connect=db.with_tenant, clock=clock)
    for tenant in (TENANT_A_ID, TENANT_B_ID):
        await service.snapshot_usage(tenant, date(2026, 10, 1))
    rows = dict(await su_fetch(db, "SELECT tenant_id, db_bytes_est FROM tenant_usage"))
    assert 1.8 < rows[TENANT_B_ID] / rows[TENANT_A_ID] < 2.2
    method = await su_fetch(db, "SELECT DISTINCT db_estimate_method FROM tenant_usage")
    assert method == [("row-bytes-v1",)]


async def test_the_nightly_sweep_removes_expired_overrides_with_an_audit_event(
    client: httpx.AsyncClient, db: TenantDb, service: EntitlementService, clock: FakeClock
) -> None:
    await put_subscription(client, TENANT_A_ID)
    url = f"{PLATFORM}/{TENANT_A_ID}/entitlement-overrides"
    soon = (clock.now + timedelta(hours=1)).isoformat()
    await client.post(
        url,
        json={"key": "feature.bim", "value": True, "reason": "a", "expiresAt": soon},
        headers=CAROL,
    )
    await client.post(url, json={"key": "limit.projects", "value": 9, "reason": "b"}, headers=CAROL)
    assert await service.sweep_expired_overrides(TENANT_A_ID) == 0
    clock.advance(timedelta(days=1))
    assert await service.sweep_expired_overrides(TENANT_A_ID) == 1
    live = await su_fetch(
        db, "SELECT key FROM tenant_entitlement_override WHERE deleted_at IS NULL"
    )
    assert live == [("limit.projects",)]
    expired = await events(db, "override_expired")
    assert [(e["key"], e["actor"]) for e in expired] == [("feature.bim", None)]


# --- operator API and the tenant page -----------------------------------------------------------


async def test_only_operators_change_subscriptions(client: httpx.AsyncClient, db: TenantDb) -> None:
    assert (await put_subscription(client, TENANT_A_ID, headers=ALICE)).status_code == 403
    assert (await put_subscription(client, TENANT_A_ID, headers=CAROL)).status_code == 200


async def test_a_production_term_needs_a_contract_ref_and_is_audited(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    missing = await put_subscription(client, TENANT_A_ID, term="annual")
    assert (missing.status_code, missing.json()) == (422, {"code": "CONTRACT_REF_REQUIRED"})
    first = await put_subscription(client, TENANT_A_ID, term="annual", contract_ref="C-1001")
    assert first.status_code == 200, first.text
    second = await put_subscription(client, TENANT_A_ID, term="annual", contract_ref="C-1002")
    assert second.json()["entitlementVersion"] == first.json()["entitlementVersion"] + 1
    changes = await events(db, "subscription")
    assert [e["after"]["contractRef"] for e in changes] == ["C-1001", "C-1002"]
    assert changes[0]["before"] is None
    assert changes[1]["before"]["contractRef"] == "C-1001"
    assert changes[1]["reason"] == "test set-up"


async def test_unknown_plans_and_add_ons_are_refused(client: httpx.AsyncClient) -> None:
    plan = await put_subscription(client, TENANT_A_ID, plan="platinum")
    assert (plan.status_code, plan.json()["code"]) == (422, "UNKNOWN_PLAN")
    add_on = await put_subscription(client, TENANT_A_ID, add_ons=["teleport"])
    assert (add_on.status_code, add_on.json()["code"]) == (422, "UNKNOWN_ADD_ON")


async def test_tenant_admins_read_their_own_plan_and_usage(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    await put_subscription(client, TENANT_A_ID, plan="professional")
    await put_subscription(client, TENANT_B_ID)

    page = await client.get("/api/v1/settings/plan-and-usage", headers=ALICE)
    assert page.status_code == 200, page.text
    body = page.json()
    assert (body["plan"], body["term"], body["renewalDate"]) == (
        "professional",
        "sandbox",
        "2027-06-30",
    )
    limits = {item["key"]: item for item in body["limits"]}
    assert limits["limit.seats.full"]["limit"] == 5
    features = {item["key"]: item for item in body["features"]}
    assert features["feature.sso"] == {"key": "feature.sso", "enabled": False, "source": "plan"}
    assert not {"price", "invoice", "payment"} & {k.lower() for k in body}

    other = await client.get("/api/v1/settings/plan-and-usage", headers=BOB)
    assert other.json()["plan"] == "core"


async def test_plan_and_usage_needs_the_permission(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/settings/plan-and-usage", headers=CAROL)
    assert response.status_code == 403


async def test_there_is_no_self_registration(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/register", json={})).status_code == 404
    assert (await client.get("/api/v1/register")).status_code == 404


async def test_seed_gives_the_fixture_tenants_their_plans(db: TenantDb) -> None:
    for _ in range(2):
        assert await seed(db.db.owner_url, env="test") == 2
    rows = await su_fetch(
        db,
        "SELECT tenant_id, plan_code, term, entitlement_version FROM tenant_subscription"
        " ORDER BY plan_code",
    )
    assert rows == [
        (TENANT_B_ID, "core", "sandbox", 2),
        (TENANT_A_ID, "professional", "sandbox", 2),
    ]


async def test_unknown_plan_versions_and_seat_classes_are_refused(
    client: httpx.AsyncClient,
) -> None:
    version = await put_subscription(client, TENANT_A_ID, plan_version=9)
    assert (version.status_code, version.json()["code"]) == (422, "UNKNOWN_PLAN_VERSION")
    seats = await put_subscription(client, TENANT_A_ID, seat_limits={"staff": 10})
    assert seats.status_code == 422  # only full and portal seats are contracted


async def test_override_expiry_needs_a_time_zone(client: httpx.AsyncClient) -> None:
    await put_subscription(client, TENANT_A_ID)
    response = await client.post(
        f"{PLATFORM}/{TENANT_A_ID}/entitlement-overrides",
        json={
            "key": "feature.bim",
            "value": True,
            "reason": "x",
            "expiresAt": "2026-10-16T00:00:00",
        },
        headers=CAROL,
    )
    assert response.status_code == 422
