"""PORTAL-07 integration tests: the register's list filters on real Postgres (``aip_app``, RLS on).

``expiringWithinDays`` keeps users with a live grant ending within that many days;
``projectId`` keeps users with an unrevoked grant on that project. Expiry dates are set as the test
owner, as PORTAL-01's tests do.
"""

from __future__ import annotations

from typing import Any

import httpx
from tests.fixtures.postgres import TenantDb

from .conftest import ALICE, BOB, P1, P2, PB, USERS, invite_body, su_execute


async def invite(client: httpx.AsyncClient, email: str, *projects: Any) -> dict[str, Any]:
    grants = [{"projectId": str(p), "actions": ["view"]} for p in projects or (P1,)]
    res = await client.post(USERS, json=invite_body(email, grants=grants), headers=dict(ALICE))
    assert res.status_code == 201, res.text
    return res.json()


async def expire_in(db: TenantDb, grant_id: str, days: float) -> None:
    await su_execute(
        db,
        f"UPDATE portal_grants SET expires_at = now() + interval '{days} days'"
        f" WHERE id = '{grant_id}'",
    )


async def emails(client: httpx.AsyncClient, who: dict[str, str], **params: Any) -> set[str]:
    res = await client.get(USERS, params=params, headers=who)
    assert res.status_code == 200, res.text
    return {item["email"] for item in res.json()["items"]}


async def test_expiring_within_days_keeps_users_with_a_live_grant_ending_in_the_window(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    soon = await invite(client, "soon@rio.example")
    later = await invite(client, "later@rio.example")
    expired = await invite(client, "expired@rio.example")
    revoked = await invite(client, "revoked@rio.example")
    await expire_in(db, soon["grants"][0]["id"], 5)
    await expire_in(db, later["grants"][0]["id"], 100)
    await expire_in(db, expired["grants"][0]["id"], -1)
    await expire_in(db, revoked["grants"][0]["id"], 5)
    gone = revoked["grants"][0]["id"]
    res = await client.delete(f"{USERS}/{revoked['id']}/grants/{gone}", headers=dict(ALICE))
    assert res.status_code == 204

    assert await emails(client, dict(ALICE), expiringWithinDays=30) == {"soon@rio.example"}
    assert await emails(client, dict(ALICE), expiringWithinDays=400) == {
        "soon@rio.example",
        "later@rio.example",
    }
    both = await emails(client, dict(ALICE), expiringWithinDays=30, status="invited")
    assert both == {"soon@rio.example"}
    assert await emails(client, dict(ALICE), expiringWithinDays=30, status="active") == set()


async def test_project_id_keeps_users_with_an_unrevoked_grant_on_that_project(
    client: httpx.AsyncClient,
) -> None:
    await invite(client, "one@rio.example", P1)
    await invite(client, "two@rio.example", P2)
    await invite(client, "both@rio.example", P1, P2)

    assert await emails(client, dict(ALICE), projectId=str(P1)) == {
        "one@rio.example",
        "both@rio.example",
    }
    assert await emails(client, dict(ALICE), projectId=str(P2), q="both") == {"both@rio.example"}


async def test_out_of_range_filters_are_422(client: httpx.AsyncClient) -> None:
    for days in (0, 401):
        res = await client.get(USERS, params={"expiringWithinDays": days}, headers=dict(ALICE))
        assert res.status_code == 422, days
    res = await client.get(USERS, params={"projectId": "not-a-uuid"}, headers=dict(ALICE))
    assert res.status_code == 422


async def test_another_tenant_filtering_by_a_kaefer_project_sees_nothing(
    client: httpx.AsyncClient,
) -> None:
    await invite(client, "client@rio.example", P1)

    assert await emails(client, dict(BOB), projectId=str(P1)) == set()
    assert await emails(client, dict(BOB), expiringWithinDays=400) == set()
    assert await emails(client, dict(BOB), projectId=str(PB)) == set()
