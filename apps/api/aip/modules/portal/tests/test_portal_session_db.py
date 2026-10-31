"""PORTAL-02 integration tests on real Postgres: portal sessions (identity's ``issue_session(...,
audience="portal")`` for a PORTAL-01 portal user, presented as real session cookies, no test stub)
against the real app.

- ``GET /portal/me`` activates an invited client, lists its granted projects and records
  ``portal.signed_in`` once per session; expired access lists nothing;
- portal and staff cookies and sessions are not interchangeable; a portal session gets 404 on every
  staff route and a staff session 404 on the portal routes;
- tenant isolation, the portal idle timeout (default and per tenant), logout, rate limits, and a
  suspended client losing its session.

Time is moved by shifting the session row back (what ``AIP_TEST_CLOCK_OFFSET`` would do for the
step-up clock): identity's session store reads the database clock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.identity import api as identity
from aip.modules.portal.rate_limit import FixedWindowLimiter, MemoryWindowStore, PortalLimits
from aip.platform.access import AccessPrincipal, PolicyService, Resource
from aip.platform.db.session import with_tenant

from .conftest import ALICE, BOB, P1, PB, USERS, invite_body, su_count, su_execute, su_fetch

PORTAL_ORIGIN = "http://portal.localhost:8081"  # identity's default PORTAL_ORIGIN
APP_ORIGIN = "http://localhost:8080"
ME = "/api/v1/portal/me"
LOGOUT = "/api/v1/portal/logout"
PORTAL_SID, PORTAL_CSRF = "__Host-aip_portal_sid", "__Host-aip_portal_csrf"
STAFF_SID, STAFF_CSRF = "__Host-aip_sid", "__Host-aip_csrf"
SIGNED_IN = (
    "SELECT count(*) FROM domain_events WHERE event_name = 'audit.security_event'"
    " AND payload->>'eventType' = $1"
)


async def _invited(
    client: httpx.AsyncClient, *, who: Any = ALICE, email: str = "client.a@rio.example", **body: Any
) -> UUID:
    """An invited portal user whose identity account is active (what identity's JIT does at the
    first sign-in); the ``portal_users`` row stays ``invited`` until ``GET /portal/me``."""
    res = await client.post(USERS, json=invite_body(email, **body), headers=dict(who))
    assert res.status_code == 201, res.text
    user_id = UUID(res.json()["userId"])
    tenant = TENANT_A_ID if who is ALICE else TENANT_B_ID
    async with with_tenant(tenant) as conn:
        await identity.set_user_status(conn, user_id, "active")
    return user_id


async def _session(
    user_id: UUID, *, tenant: UUID = TENANT_A_ID, portal: bool = True
) -> Any:
    async with with_tenant(tenant) as conn:
        return await identity.issue_session(
            conn,
            user_id=user_id,
            user_class="portal" if portal else "staff",
            aal=2,
            amr=["pwd", "otp"],
            authenticated_at=datetime.now(UTC),
            kc_sid=None,
            audience="portal" if portal else "app",
        )


def _portal(issued: Any, *, unsafe: bool = False) -> dict[str, str]:
    if not unsafe:
        return {"cookie": f"{PORTAL_SID}={issued.sid}"}
    return {
        "cookie": f"{PORTAL_SID}={issued.sid}; {PORTAL_CSRF}={issued.csrf}",
        "origin": PORTAL_ORIGIN,
        "x-csrf-token": issued.csrf,
    }


def _staff(issued: Any, *, unsafe: bool = False) -> dict[str, str]:
    if not unsafe:
        return {"cookie": f"{STAFF_SID}={issued.sid}"}
    return {
        "cookie": f"{STAFF_SID}={issued.sid}; {STAFF_CSRF}={issued.csrf}",
        "origin": APP_ORIGIN,
        "x-csrf-token": issued.csrf,
    }


async def _shift(db: TenantDb, session_id: UUID, minutes: int) -> None:
    """Move a session ``minutes`` into the past, as if that much idle time had gone by."""
    shift = f"interval '{minutes} minutes'"
    await su_execute(
        db,
        f"UPDATE user_session SET authenticated_at = authenticated_at - {shift},"
        f" last_seen_at = last_seen_at - {shift}, idle_expires_at = idle_expires_at - {shift},"
        f" absolute_expires_at = absolute_expires_at - {shift},"
        f" created_at = created_at - {shift} WHERE id = '{session_id}'",
    )


def _cleared_names(res: httpx.Response) -> set[str]:
    cleared = res.headers.get_list("set-cookie")
    assert all("Max-Age=0" in c for c in cleared), cleared
    return {c.split("=", 1)[0] for c in cleared}


async def test_the_first_me_activates_the_client_and_records_one_sign_in(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    user_id = await _invited(client)
    issued = await _session(user_id)

    res = await client.get(ME, headers=_portal(issued))
    assert res.status_code == 200, res.text
    assert res.headers["cache-control"] == "no-store"
    body = res.json()
    assert body["userId"] == str(user_id)
    assert body["companyName"] == "Rio Example Pty Ltd"
    assert body["effectiveStatus"] == "active"
    assert body["projects"] == [
        {"id": str(P1), "code": "P1", "name": "Project one", "actions": ["view", "sign_off"]}
    ]
    status = await su_fetch(db, "SELECT status FROM portal_users WHERE user_id = $1", user_id)
    assert status == [("active",)]
    assert await su_count(db, SIGNED_IN, "portal.signed_in") == 1

    again = await client.get(ME, headers=_portal(issued))
    assert again.status_code == 200
    assert await su_count(db, SIGNED_IN, "portal.signed_in") == 1  # once per session

    other = await _session(user_id)  # a new sign-in is a new session
    assert (await client.get(ME, headers=_portal(other))).status_code == 200
    assert await su_count(db, SIGNED_IN, "portal.signed_in") == 2


async def test_expired_access_lists_no_project(client: httpx.AsyncClient, db: TenantDb) -> None:
    user_id = await _invited(client)
    issued = await _session(user_id)
    assert (await client.get(ME, headers=_portal(issued))).json()["projects"] != []
    await su_execute(
        db,
        "UPDATE portal_grants SET expires_at = now() - interval '1 second'"
        f" WHERE project_id = '{P1}'",
    )
    body = (await client.get(ME, headers=_portal(issued))).json()
    assert (body["effectiveStatus"], body["projects"]) == ("expired", [])


async def test_a_portal_session_reaches_no_staff_route(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    user_id = await _invited(client)
    issued = await _session(user_id)
    for path in (
        "/api/v1/projects",
        f"/api/v1/projects/{P1}",
        USERS,
        f"/api/v1/approvals/instances/{uuid4()}",
        "/api/v1/me",
        "/api/v1/me/sessions",
    ):
        res = await client.get(path, headers=_portal(issued))
        assert (res.status_code, res.json()) == (404, {"code": "NOT_FOUND"}), path
    before = await su_count(db, "SELECT count(*) FROM portal_users")
    create = await client.post(
        USERS, json=invite_body("other@rio.example"), headers=_portal(issued, unsafe=True)
    )
    assert (create.status_code, create.json()) == (404, {"code": "NOT_FOUND"})
    assert await su_count(db, "SELECT count(*) FROM portal_users") == before
    assert (await client.get(ME, headers=_portal(issued))).status_code == 200  # still live


async def test_staff_and_portal_sessions_and_cookies_are_not_interchangeable(
    client: httpx.AsyncClient,
) -> None:
    portal = await _session(await _invited(client))
    staff = await _session(ALICE_ID, portal=False)

    # A staff session on the portal routes: hidden.
    assert (await client.get(ME, headers=_staff(staff))).json() == {"code": "NOT_FOUND"}
    logout = await client.post(LOGOUT, headers=_staff(staff, unsafe=True))
    assert logout.status_code == 404
    assert (await client.get("/api/v1/me", headers=_staff(staff))).status_code == 200

    # Each sid under the other audience's cookie: refused and that cookie pair cleared.
    swapped = await client.get(ME, headers={"cookie": f"{STAFF_SID}={portal.sid}"})
    assert swapped.status_code == 401
    assert _cleared_names(swapped) == {STAFF_SID, STAFF_CSRF}
    swapped = await client.get(ME, headers={"cookie": f"{PORTAL_SID}={staff.sid}"})
    assert (swapped.status_code, swapped.json()["detail"]["code"]) == (401, "SESSION_EXPIRED")
    assert _cleared_names(swapped) == {PORTAL_SID, PORTAL_CSRF}


async def test_no_session_is_401(client: httpx.AsyncClient) -> None:
    res = await client.get(ME)
    assert res.status_code == 401
    assert "NOT_AUTHENTICATED" in res.text


async def test_a_tenant_b_client_sees_only_tenant_b(app: FastAPI, client: httpx.AsyncClient) -> None:
    user_id = await _invited(
        client,
        who=BOB,
        email="client.b@acme-client.example",
        grants=[{"projectId": str(PB), "actions": ["view"]}],
    )
    issued = await _session(user_id, tenant=TENANT_B_ID)
    body = (await client.get(ME, headers=_portal(issued))).json()
    assert [p["id"] for p in body["projects"]] == [str(PB)]

    policy: PolicyService = app.state.access_policy
    principal = AccessPrincipal(tenant_id=TENANT_B_ID, actor_id=user_id, external=True)
    decision = await policy.can(
        principal, "portal.record.view", Resource(project_id=P1, tenant_id=TENANT_A_ID)
    )
    assert not decision.allowed


async def test_an_idle_portal_session_ends_after_15_minutes_and_a_staff_one_does_not(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    portal = await _session(await _invited(client))
    staff = await _session(ALICE_ID, portal=False)
    await _shift(db, portal.session_id, 16)
    await _shift(db, staff.session_id, 16)

    ended = await client.get(ME, headers=_portal(portal))
    assert (ended.status_code, ended.json()["detail"]["code"]) == (401, "SESSION_EXPIRED")
    assert _cleared_names(ended) == {PORTAL_SID, PORTAL_CSRF}
    assert (await client.get("/api/v1/me", headers=_staff(staff))).status_code == 200


async def test_the_tenant_portal_idle_timeout_applies(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await su_execute(
        db,
        "INSERT INTO tenant_auth_policy (tenant_id, session_policy) VALUES"
        f" ('{TENANT_A_ID}', '{{\"portal\": {{\"idleMin\": 5}}}}')"
        " ON CONFLICT (tenant_id) DO UPDATE SET session_policy = EXCLUDED.session_policy",
    )
    portal = await _session(await _invited(client))
    await _shift(db, portal.session_id, 4)
    assert (await client.get(ME, headers=_portal(portal))).status_code == 200
    # The call above touched the session (idle slides); six idle minutes from here end it.
    await _shift(db, portal.session_id, 6)
    assert (await client.get(ME, headers=_portal(portal))).status_code == 401


async def test_logout_ends_the_portal_session_and_clears_only_portal_cookies(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    portal = await _session(await _invited(client))
    no_csrf = await client.post(LOGOUT, headers=_portal(portal))
    assert no_csrf.status_code == 403  # identity's CSRF check

    res = await client.post(LOGOUT, headers=_portal(portal, unsafe=True))
    assert res.status_code == 204, res.text
    assert res.headers["cache-control"] == "no-store"
    assert _cleared_names(res) == {PORTAL_SID, PORTAL_CSRF}
    assert (await client.get(ME, headers=_portal(portal))).status_code == 401
    reason = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE id = $1", portal.session_id
    )
    assert reason == [("logout",)]


async def test_the_121st_request_in_a_minute_is_rate_limited(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    def clock() -> float:
        return 6_000_000.0 + 20  # 20 s into a fixed minute

    store = MemoryWindowStore()
    app.state.portal_limits = PortalLimits(
        store=store,
        session=FixedWindowLimiter(store, 120, "session", clock=clock),
        ip=FixedWindowLimiter(store, 300, "ip", clock=clock),
    )
    portal = await _session(await _invited(client))
    for n in range(120):
        res = await client.get(ME, headers=_portal(portal))
        assert res.status_code == 200, (n, res.text)
    limited = await client.get(ME, headers=_portal(portal))
    assert (limited.status_code, limited.json()) == (429, {"code": "RATE_LIMITED"})
    assert limited.headers["retry-after"] == "40"
    assert (await client.get(ME, headers=_portal(portal))).status_code == 429
    assert await su_count(db, SIGNED_IN, "portal.rate_limited") == 1


async def test_a_suspended_client_loses_its_session(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    user_id = await _invited(client)
    portal = await _session(user_id)
    assert (await client.get(ME, headers=_portal(portal))).status_code == 200
    pid = (await su_fetch(db, "SELECT id FROM portal_users WHERE user_id = $1", user_id))[0][0]
    res = await client.post(
        f"{USERS}/{pid}/suspend", json={"reason": "contract ended"}, headers=dict(ALICE)
    )
    assert res.status_code == 200, res.text
    assert (await client.get(ME, headers=_portal(portal))).status_code == 401
