"""PORTAL-01 integration tests: the admin routes on real Postgres (``aip_app``, RLS on).

Users come from the AUTH_TEST_STUB principal header; permissions from real roles through the real
``RoleGrantProvider`` (see ``conftest``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.access.api import get_access_version
from aip.modules.identity import api as identity
from aip.modules.portal import policies
from aip.modules.portal import service as service_module
from aip.modules.portal.api import PortalApi

from .conftest import (
    ALICE,
    ALICE_AAL1,
    BOB,
    NODE,
    P1,
    P2,
    P_ARCHIVED,
    PADMIN1,
    PADMIN2,
    PB,
    USERS,
    invite_body,
    su_count,
    su_execute,
    su_fetch,
    tenant_tx,
)

DAY = timedelta(days=1)


async def invite(client: httpx.AsyncClient, who: Mapping[str, str], **body: Any) -> httpx.Response:
    return await client.post(USERS, json=invite_body(**body), headers=dict(who))


async def event_count(db: TenantDb, name: str) -> int:
    return await su_count(db, "SELECT count(*) FROM domain_events WHERE event_name = $1", name)


async def version(tenant: UUID = TENANT_A_ID) -> int:
    async with tenant_tx(tenant) as conn:
        return await get_access_version(conn)


async def counts(db: TenantDb) -> tuple[int, int, int]:
    return (
        await su_count(db, "SELECT count(*) FROM portal_users"),
        await su_count(db, "SELECT count(*) FROM portal_grants"),
        await su_count(db, "SELECT count(*) FROM app_user WHERE user_class = 'portal'"),
    )


def near(value: str, expected: datetime) -> bool:
    return abs(datetime.fromisoformat(value) - expected) < timedelta(minutes=1)


# --- invite -------------------------------------------------------------------------------------


async def test_a_tenant_admin_invites_a_client_with_one_grant(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    before = await version()
    res = await invite(client, ALICE)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "invited"
    assert body["effectiveStatus"] == "invited"
    assert body["email"] == "client.a@rio.example"
    [grant] = body["grants"]
    assert grant["projectId"] == str(P1)
    assert grant["actions"] == ["view", "sign_off"]
    assert grant["accessDays"] == 180
    assert grant["state"] == "live"
    assert near(grant["expiresAt"], datetime.now(UTC) + 180 * DAY)
    assert body["expiresAt"] == grant["expiresAt"]

    assert await counts(db) == (1, 1, 1)
    [(user_class, status)] = await su_fetch(
        db, "SELECT user_class, status FROM app_user WHERE id = $1", UUID(body["userId"])
    )
    assert (user_class, status) == ("portal", "invited")
    assert await event_count(db, "portal_user.invited") == 1
    assert await event_count(db, "portal_grant.created") == 1
    assert await version() == before + 1


async def test_a_project_admin_invites_on_their_project(client: httpx.AsyncClient) -> None:
    res = await invite(client, PADMIN1)
    assert res.status_code == 201, res.text


async def test_the_grant_period_comes_from_the_project_setting(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def setting(conn: AsyncConnection, project_id: UUID) -> int:
        return policies.access_days(365 if project_id == P2 else None)

    # PROJECTS-04 ships ProjectsApi.get_setting; until then the reader is the seam.
    monkeypatch.setattr(service_module, "read_access_days", setting)
    res = await invite(
        client,
        ALICE,
        grants=[
            {"projectId": str(P1), "actions": ["view"]},
            {"projectId": str(P2), "actions": ["view", "download"]},
        ],
    )
    assert res.status_code == 201, res.text
    days = {g["projectId"]: g["accessDays"] for g in res.json()["grants"]}
    assert days == {str(P1): 180, str(P2): 365}


async def test_without_get_setting_the_period_is_the_default(db: TenantDb) -> None:
    async with tenant_tx() as conn:
        assert await service_module.read_access_days(conn, P1) == 180


async def test_refused_invites_write_nothing(client: httpx.AsyncClient, db: TenantDb) -> None:
    before = (await counts(db), await version(), await event_count(db, "portal_user.invited"))

    expires = await invite(client, ALICE, expiresAt="2030-01-01T00:00:00Z")
    assert expires.status_code == 422
    role = await invite(client, ALICE, role="admin")
    assert role.status_code == 422
    no_view = await invite(client, ALICE, grants=[{"projectId": str(P1), "actions": ["sign_off"]}])
    assert no_view.status_code == 422
    bad_action = await invite(
        client, ALICE, grants=[{"projectId": str(P1), "actions": ["view", "delete"]}]
    )
    assert bad_action.status_code == 422

    other_project_admin = await invite(client, PADMIN2)
    assert other_project_admin.status_code == 403
    second_grant_elsewhere = await invite(
        client,
        PADMIN1,
        grants=[
            {"projectId": str(P1), "actions": ["view"]},
            {"projectId": str(P2), "actions": ["view"]},
        ],
    )
    assert second_grant_elsewhere.status_code == 403

    other_tenant = await invite(client, ALICE, grants=[{"projectId": str(PB), "actions": ["view"]}])
    assert other_tenant.status_code == 404

    archived = await invite(
        client, ALICE, grants=[{"projectId": str(P_ARCHIVED), "actions": ["view"]}]
    )
    assert archived.status_code == 422
    assert archived.json()["code"] == "PROJECT_CLOSED"

    missing_asset = await invite(
        client,
        ALICE,
        grants=[{"projectId": str(P1), "assetId": str(PB), "actions": ["view"]}],
    )
    assert missing_asset.status_code == 422
    assert missing_asset.json()["code"] == "ASSET_NOT_FOUND"

    after = (await counts(db), await version(), await event_count(db, "portal_user.invited"))
    assert after == before


async def test_an_invite_without_step_up_is_401(client: httpx.AsyncClient, db: TenantDb) -> None:
    res = await invite(client, ALICE_AAL1)
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    assert await counts(db) == (0, 0, 0)


async def test_an_identity_refusal_keeps_its_code_and_rolls_back(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    res = await invite(client, ALICE, email="alice@kaefer.test")  # an existing staff account
    assert res.status_code == 409
    assert res.json()["code"] == "USER_EXISTS"
    assert await counts(db) == (0, 0, 0)


async def test_two_identical_grants_conflict(client: httpx.AsyncClient, db: TenantDb) -> None:
    same = {"projectId": str(P1), "actions": ["view"]}
    res = await invite(client, ALICE, grants=[same, same])
    assert res.status_code == 409
    assert res.json()["code"] == "GRANT_EXISTS"
    assert await counts(db) == (0, 0, 0)


# --- sign-in, suspend, reinstate ----------------------------------------------------------------


async def test_mark_signed_in_activates_once(client: httpx.AsyncClient, db: TenantDb) -> None:
    user_id = UUID((await invite(client, ALICE)).json()["userId"])
    async with tenant_tx() as conn:
        row = await PortalApi().mark_signed_in(conn, user_id)
    assert row is not None and row["status"] == "active"
    first = row["first_signed_in_at"]
    async with tenant_tx() as conn:
        again = await PortalApi().mark_signed_in(conn, user_id)
    assert again is not None and again["first_signed_in_at"] == first
    assert await event_count(db, "portal_user.status_changed") == 1


async def test_suspend_and_reinstate(client: httpx.AsyncClient, db: TenantDb) -> None:
    created = (await invite(client, ALICE)).json()
    pid, user_id = created["id"], UUID(created["userId"])

    no_reason = await client.post(f"{USERS}/{pid}/suspend", json={}, headers=dict(ALICE))
    assert no_reason.status_code == 422
    v0 = await version()
    res = await client.post(f"{USERS}/{pid}/suspend", json={"reason": "left"}, headers=dict(ALICE))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "suspended"
    assert res.json()["suspendedReason"] == "left"
    assert await version() == v0 + 1
    again = await client.post(f"{USERS}/{pid}/suspend", json={"reason": "x"}, headers=dict(ALICE))
    assert again.status_code == 409

    unstepped = await client.post(f"{USERS}/{pid}/reinstate", headers=dict(ALICE_AAL1))
    assert unstepped.status_code == 401
    back = await client.post(f"{USERS}/{pid}/reinstate", headers=dict(ALICE))
    assert back.status_code == 200, back.text
    assert back.json()["status"] == "invited"  # never signed in
    assert await event_count(db, "portal_user.status_changed") == 2

    async with tenant_tx() as conn:
        await PortalApi().mark_signed_in(conn, user_id)
    await client.post(f"{USERS}/{pid}/suspend", json={"reason": "again"}, headers=dict(ALICE))
    back = await client.post(f"{USERS}/{pid}/reinstate", headers=dict(ALICE))
    assert back.json()["status"] == "active"  # has signed in before


async def test_a_project_admin_cannot_suspend(client: httpx.AsyncClient) -> None:
    pid = (await invite(client, ALICE)).json()["id"]
    res = await client.post(f"{USERS}/{pid}/suspend", json={"reason": "x"}, headers=dict(PADMIN1))
    assert res.status_code == 403


# --- grants -------------------------------------------------------------------------------------


async def test_add_and_revoke_grants(client: httpx.AsyncClient, db: TenantDb) -> None:
    pid = (await invite(client, ALICE)).json()["id"]
    url = f"{USERS}/{pid}/grants"
    p2_by_p1_admin = await client.post(
        url, json={"projectId": str(P2), "actions": ["view"]}, headers=dict(PADMIN1)
    )
    assert p2_by_p1_admin.status_code == 403
    duplicate = await client.post(
        url, json={"projectId": str(P1), "actions": ["view"]}, headers=dict(ALICE)
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "GRANT_EXISTS"

    subtree = await client.post(
        url,
        json={"projectId": str(P1), "assetId": str(NODE), "actions": ["view"]},
        headers=dict(PADMIN1),
    )
    assert subtree.status_code == 201, subtree.text
    grant_id = subtree.json()["id"]
    assert await event_count(db, "portal_grant.created") == 2

    elsewhere = await client.delete(f"{url}/{grant_id}", headers=dict(PADMIN2))
    assert elsewhere.status_code == 403
    v0 = await version()
    gone = await client.delete(f"{url}/{grant_id}", headers=dict(PADMIN1))
    assert gone.status_code == 204
    [(reason,)] = await su_fetch(
        db, "SELECT revoked_reason FROM portal_grants WHERE id = $1", UUID(grant_id)
    )
    assert reason == "manual"
    assert await event_count(db, "portal_grant.revoked") == 1
    assert await version() == v0 + 1
    again = await client.delete(f"{url}/{grant_id}", headers=dict(PADMIN1))
    assert again.status_code == 404


async def test_renew_restores_an_expired_grant(client: httpx.AsyncClient, db: TenantDb) -> None:
    created = (await invite(client, ALICE)).json()
    pid, grant_id = created["id"], created["grants"][0]["id"]
    await su_execute(
        db,
        f"UPDATE portal_grants SET expires_at = now() - interval '1 second' WHERE id = '{grant_id}'",
    )
    shown = (await client.get(f"{USERS}/{pid}", headers=dict(ALICE))).json()
    assert shown["grants"][0]["state"] == "expired"
    assert shown["expiresAt"] is None

    url = f"{USERS}/{pid}/grants/{grant_id}/renew"
    elsewhere = await client.post(url, headers=dict(PADMIN2))
    assert elsewhere.status_code == 403
    unstepped = await client.post(url, headers=dict(headers_aal1_padmin1()))
    assert unstepped.status_code == 401
    v0 = await version()
    res = await client.post(url, headers=dict(PADMIN1))
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "live"
    assert near(res.json()["expiresAt"], datetime.now(UTC) + 180 * DAY)
    assert res.json()["renewedAt"] is not None
    assert await event_count(db, "portal_grant.renewed") == 1
    assert await version() == v0 + 1

    await client.delete(f"{USERS}/{pid}/grants/{grant_id}", headers=dict(PADMIN1))
    revoked = await client.post(url, headers=dict(PADMIN1))
    assert revoked.status_code == 409
    assert revoked.json()["code"] == "REVOKED"


def headers_aal1_padmin1() -> Mapping[str, str]:
    from .conftest import PADMIN1_ID, headers

    return headers(TENANT_A_ID, PADMIN1_ID, aal=1)


# --- reads and isolation ------------------------------------------------------------------------


async def test_list_filters_and_pages(client: httpx.AsyncClient) -> None:
    for i in range(3):
        res = await invite(client, ALICE, email=f"c{i}@rio.example", companyName=f"Rio {i}")
        assert res.status_code == 201, res.text
    first = (await client.get(USERS, params={"limit": 2}, headers=dict(ALICE))).json()
    assert len(first["items"]) == 2 and first["nextCursor"]
    second = await client.get(
        USERS, params={"limit": 2, "cursor": first["nextCursor"]}, headers=dict(ALICE)
    )
    assert [i["companyName"] for i in second.json()["items"]] == ["Rio 2"]
    assert second.json()["nextCursor"] is None

    by_company = await client.get(USERS, params={"q": "rio 1"}, headers=dict(ALICE))
    assert [i["companyName"] for i in by_company.json()["items"]] == ["Rio 1"]
    by_email = await client.get(USERS, params={"q": "c2@rio"}, headers=dict(ALICE))
    assert [i["email"] for i in by_email.json()["items"]] == ["c2@rio.example"]
    suspended = await client.get(USERS, params={"status": "suspended"}, headers=dict(ALICE))
    assert suspended.json()["items"] == []
    bad = await client.get(USERS, params={"cursor": "!!"}, headers=dict(ALICE))
    assert bad.status_code == 422


async def test_tenant_b_sees_nothing_of_kaefer_demo(client: httpx.AsyncClient) -> None:
    pid = (await invite(client, ALICE)).json()["id"]
    one = await client.get(f"{USERS}/{pid}", headers=dict(BOB))
    assert one.status_code == 404
    listed = await client.get(USERS, headers=dict(BOB))
    assert listed.status_code == 200 and listed.json()["items"] == []
    suspend = await client.post(f"{USERS}/{pid}/suspend", json={"reason": "x"}, headers=dict(BOB))
    assert suspend.status_code == 404
    assert await version(TENANT_B_ID) >= 0


async def test_identity_status_is_left_to_identity(client: httpx.AsyncClient) -> None:
    user_id = UUID((await invite(client, ALICE)).json()["userId"])
    async with tenant_tx() as conn:
        user = await identity.get_user(conn, user_id)
    assert user is not None and user.status == "invited"
