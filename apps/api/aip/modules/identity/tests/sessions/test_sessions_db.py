"""IDENTITY-03 integration tests on real Postgres (and Redis where marked): issuing, resolving,
expiring, rotating and revoking app sessions, CSRF, logout and the Keycloak back-channel logout.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.identity.routes import get_logout_verifier
from aip.modules.identity.session_store import RedisSessionCache, SessionStore
from aip.modules.identity.sessions import REVOKE_KEYCLOAK_JOB, revoke_all_for_user
from aip.platform.db.session import with_tenant

from .conftest import CAROL_ID, cookies, new_session, su_execute, su_fetch, unsafe

ME = "/api/v1/me"
JOBS_SQL = "SELECT args FROM procrastinate_jobs WHERE task_name = $1"


def expired(response: httpx.Response) -> None:
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "SESSION_EXPIRED"
    cleared = response.headers.get_list("set-cookie")
    assert any(c.startswith("__Host-aip_sid=") and "Max-Age=0" in c for c in cleared)
    assert any(c.startswith("__Host-aip_csrf=") and "Max-Age=0" in c for c in cleared)


async def test_only_the_hash_of_the_sid_is_stored(client: httpx.AsyncClient, db: TenantDb) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID)
    rows = await su_fetch(db, "SELECT sid_hash, row_to_json(s)::text FROM user_session s")
    assert len(rows) == 1
    assert bytes(rows[0][0]) == hashlib.sha256(issued.sid.encode()).digest()
    assert issued.sid not in rows[0][1] and issued.csrf not in rows[0][1]

    me = await client.get(ME, headers=cookies(issued))
    assert me.status_code == 200, me.text
    assert me.json()["user"]["id"] == str(ALICE_ID)
    assert "eyJ" not in me.text


async def test_no_cookie_is_401_and_an_unknown_cookie_is_session_expired(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(ME)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "NOT_AUTHENTICATED"
    expired(await client.get(ME, headers={"cookie": "__Host-aip_sid=not-a-session"}))


async def test_logging_in_with_an_old_cookie_rotates_it(db: TenantDb) -> None:
    old = await new_session(TENANT_A_ID, ALICE_ID)
    await new_session(TENANT_A_ID, ALICE_ID, presented_sid=old.sid)
    rows = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE id = $1", old.session_id
    )
    assert rows == [("rotated",)]


async def test_revocation_commits_with_its_transaction(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID, kc_sid="kc-1")

    class RollbackError(Exception):
        pass

    with pytest.raises(RollbackError):
        async with with_tenant(TENANT_A_ID) as conn:
            await revoke_all_for_user(conn, ALICE_ID, "admin")
            raise RollbackError
    assert (await client.get(ME, headers=cookies(issued))).status_code == 200
    assert await su_fetch(db, JOBS_SQL, REVOKE_KEYCLOAK_JOB) == []

    async with with_tenant(TENANT_A_ID) as conn:
        await revoke_all_for_user(conn, ALICE_ID, "admin")
    expired(await client.get(ME, headers=cookies(issued)))
    assert len(await su_fetch(db, JOBS_SQL, REVOKE_KEYCLOAK_JOB)) == 1
    payload = await su_fetch(
        db, "SELECT payload FROM jobs WHERE job_type = $1", REVOKE_KEYCLOAK_JOB
    )
    assert "kc-1" in str(payload)


async def test_idle_and_absolute_timeouts(client: httpx.AsyncClient, db: TenantDb) -> None:
    idle = await new_session(TENANT_A_ID, ALICE_ID)
    await su_execute(
        db,
        "UPDATE user_session SET last_seen_at = now() - interval '31 minutes',"
        f" idle_expires_at = now() - interval '1 minute' WHERE id = '{idle.session_id}'",
    )
    expired(await client.get(ME, headers=cookies(idle)))

    absolute = await new_session(TENANT_A_ID, ALICE_ID)
    await su_execute(
        db,
        "UPDATE user_session SET created_at = now() - interval '12 hours 1 minute',"
        " idle_expires_at = now() - interval '1 minute',"
        f" absolute_expires_at = now() - interval '1 minute' WHERE id = '{absolute.session_id}'",
    )
    expired(await client.get(ME, headers=cookies(absolute)))


async def test_activity_slides_the_idle_expiry_but_never_the_absolute(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID)
    await su_execute(
        db,
        "UPDATE user_session SET last_seen_at = now() - interval '5 minutes',"
        " idle_expires_at = now() + interval '5 minutes',"
        f" absolute_expires_at = now() + interval '10 minutes' WHERE id = '{issued.session_id}'",
    )
    before = await su_fetch(
        db, "SELECT absolute_expires_at FROM user_session WHERE id = $1", issued.session_id
    )
    assert (await client.get(ME, headers=cookies(issued))).status_code == 200
    rows = await su_fetch(
        db,
        "SELECT last_seen_at > now() - interval '5 seconds', idle_expires_at, absolute_expires_at"
        " FROM user_session WHERE id = $1",
        issued.session_id,
    )
    touched, idle_at, absolute_at = rows[0]
    assert touched
    assert absolute_at == before[0][0]
    assert idle_at == absolute_at  # capped by the absolute expiry


async def test_a_deactivated_user_is_refused(client: httpx.AsyncClient, db: TenantDb) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID)
    await su_execute(
        db,
        "UPDATE app_user SET status = 'deactivated', deactivated_at = now()"
        f" WHERE id = '{ALICE_ID}'",
    )
    expired(await client.get(ME, headers=cookies(issued)))


async def test_fifty_parallel_requests_each_see_their_own_tenant(
    client: httpx.AsyncClient,
) -> None:
    alice = await new_session(TENANT_A_ID, ALICE_ID)
    bob = await new_session(TENANT_B_ID, BOB_ID)
    plan = [(alice, "kaefer-demo"), (bob, "tenant-b")] * 25
    responses = await asyncio.gather(
        *(client.get(ME, headers=cookies(issued)) for issued, _ in plan)
    )
    assert [r.json()["tenant"]["slug"] for r in responses] == [slug for _, slug in plan]


async def test_logout_revokes_the_session_and_queues_the_keycloak_logout(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID, kc_sid="kc-logout")
    response = await client.post("/api/v1/auth/logout", headers=unsafe(issued))
    assert response.status_code == 204, response.text
    assert all("Max-Age=0" in c for c in response.headers.get_list("set-cookie"))
    rows = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE id = $1", issued.session_id
    )
    assert rows == [("logout",)]
    assert len(await su_fetch(db, JOBS_SQL, REVOKE_KEYCLOAK_JOB)) == 1
    expired(await client.get(ME, headers=cookies(issued)))
    # Without a session, logout still clears the cookies (idempotent).
    assert (await client.post("/api/v1/auth/logout")).status_code == 204


async def test_unsafe_requests_need_the_csrf_token(client: httpx.AsyncClient) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID)
    for headers in (
        cookies(issued),
        {**cookies(issued), "origin": "https://evil.test", "x-csrf-token": issued.csrf},
        {**cookies(issued), "origin": "https://app.example.test", "x-csrf-token": "wrong"},
    ):
        response = await client.post("/api/v1/auth/logout", headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "CSRF_FAILED"
    assert (await client.get(ME, headers=cookies(issued))).status_code == 200


async def test_my_sessions_list_and_revoke(client: httpx.AsyncClient, db: TenantDb) -> None:
    current = await new_session(TENANT_A_ID, ALICE_ID)
    other = await new_session(TENANT_A_ID, ALICE_ID)
    carol = await new_session(TENANT_A_ID, CAROL_ID)
    listed = (await client.get("/api/v1/me/sessions", headers=cookies(current))).json()["items"]
    assert {(s["id"], s["current"]) for s in listed} == {
        (str(current.session_id), True),
        (str(other.session_id), False),
    }
    assert listed[0]["ip"] == "203.0.113.7" and listed[0]["userAgent"] == "pytest"

    path = "/api/v1/me/sessions/"
    gone = await client.delete(f"{path}{carol.session_id}", headers=unsafe(current))
    assert gone.status_code == 404  # someone else's session
    assert (await client.get(ME, headers=cookies(carol))).status_code == 200

    assert (
        await client.delete(f"{path}{other.session_id}", headers=unsafe(current))
    ).status_code == 204
    expired(await client.get(ME, headers=cookies(other)))
    assert (await client.get(ME, headers=cookies(current))).status_code == 200


async def test_backchannel_logout_revokes_matching_sessions(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    async def verify(token: str) -> str:
        if token != "good":
            from aip.modules.identity.oidc import OidcError

            raise OidcError("INVALID_LOGOUT_TOKEN", 400, "bad")
        return "kc-bc"

    verifier: Callable[[], Callable[[str], Awaitable[str]]] = lambda: verify  # noqa: E731
    app.dependency_overrides[get_logout_verifier] = verifier
    matching = await new_session(TENANT_A_ID, ALICE_ID, kc_sid="kc-bc")
    other = await new_session(TENANT_A_ID, ALICE_ID, kc_sid="kc-other")
    form = {"content-type": "application/x-www-form-urlencoded"}

    bad = await client.post(
        "/api/v1/auth/oidc/backchannel-logout", content="logout_token=bad", headers=form
    )
    assert bad.status_code == 400
    ok = await client.post(
        "/api/v1/auth/oidc/backchannel-logout", content="logout_token=good", headers=form
    )
    assert ok.status_code == 200
    again = await client.post(
        "/api/v1/auth/oidc/backchannel-logout", content="logout_token=good", headers=form
    )
    assert again.status_code == 200  # idempotent
    expired(await client.get(ME, headers=cookies(matching)))
    assert (await client.get(ME, headers=cookies(other))).status_code == 200
    rows = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE id = $1", matching.session_id
    )
    assert rows == [("keycloak_logout",)]
    assert await su_fetch(db, JOBS_SQL, REVOKE_KEYCLOAK_JOB) == []  # Keycloak already knows


# --- with the Redis cache ---------------------------------------------------------------------


@pytest.mark.parametrize("use_redis", [True])
async def test_revocation_purges_the_cache_after_commit(
    app: FastAPI, client: httpx.AsyncClient, redis_url: str
) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID)
    assert (await client.get(ME, headers=cookies(issued))).status_code == 200
    redis: Any = Redis.from_url(redis_url)  # pyright: ignore[reportUnknownMemberType]
    key = RedisSessionCache.key(hashlib.sha256(issued.sid.encode()).digest())
    assert await redis.exists(key) == 1
    async with with_tenant(TENANT_A_ID) as conn:
        await revoke_all_for_user(conn, ALICE_ID, "admin")
    for _ in range(50):  # the purge runs right after commit
        if not await redis.exists(key):
            break
        await asyncio.sleep(0.02)
    assert await redis.exists(key) == 0
    expired(await client.get(ME, headers=cookies(issued)))
    await redis.aclose()


@pytest.mark.parametrize("use_redis", [True])
async def test_a_deactivated_user_is_refused_once_the_cache_entry_lapses(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, redis_url: str
) -> None:
    from datetime import timedelta

    store: SessionStore = app.state.identity_session_store
    store.cache_ttl = timedelta(seconds=1)
    issued = await new_session(TENANT_A_ID, ALICE_ID)
    assert (await client.get(ME, headers=cookies(issued))).status_code == 200
    await su_execute(
        db,
        "UPDATE app_user SET status = 'deactivated', deactivated_at = now()"
        f" WHERE id = '{ALICE_ID}'",
    )
    await asyncio.sleep(1.2)
    expired(await client.get(ME, headers=cookies(issued)))


async def test_deactivation_revokes_sessions_so_reactivation_cannot_revive_them(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    from aip.modules.identity.repository import set_user_status

    issued = await new_session(TENANT_A_ID, ALICE_ID, kc_sid="kc-deact")
    async with with_tenant(TENANT_A_ID) as conn:
        await set_user_status(conn, ALICE_ID, "deactivated")
    async with with_tenant(TENANT_A_ID) as conn:
        await set_user_status(conn, ALICE_ID, "active")
    expired(await client.get(ME, headers=cookies(issued)))
    rows = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE id = $1", issued.session_id
    )
    assert rows == [("user_deactivated",)]
    assert len(await su_fetch(db, JOBS_SQL, REVOKE_KEYCLOAK_JOB)) == 1


async def test_an_oversized_backchannel_request_is_refused(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    async def verify(token: str) -> str:
        raise AssertionError("the token must not be verified")

    app.dependency_overrides[get_logout_verifier] = lambda: verify
    response = await client.post(
        "/api/v1/auth/oidc/backchannel-logout",
        content="logout_token=" + "x" * 20_000,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400
