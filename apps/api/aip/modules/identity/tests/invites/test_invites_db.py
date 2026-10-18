"""IDENTITY-04 integration tests on real Postgres: invites, the invite job (as ``aip_jobs``, against
a fake Keycloak), acceptance at sign-in, revocation, step-up on the admin routes and MFA reset."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.identity import repository as repo
from aip.modules.identity.invites import create_invite
from aip.modules.identity.jit import Denied, JitProvisioner, Provisioned
from aip.modules.identity.keycloak_admin import KeycloakUnavailable
from aip.modules.identity.schemas import VerifiedExternalIdentity
from aip.modules.identity.sessions import issue_session

from ..test_invites_unit import FakeKeycloak
from .conftest import ALICE, BOB, GrantTable, JobRunner, principal_headers, su_execute, su_fetch

INVITES = "/api/v1/identity/invites"
SEND = "identity.send_invite"
CAROL = "carol@client.test"


async def _invite(
    client: httpx.AsyncClient, email: str = CAROL, headers: Mapping[str, str] = ALICE
):
    return await client.post(
        INVITES, json={"email": email, "firstName": "Carol", "lastName": "Client"}, headers=headers
    )


async def _count(db: TenantDb, sql: str, *args: object) -> int:
    return int((await su_fetch(db, sql, *args))[0][0])


async def _invite_row(db: TenantDb, tenant: UUID, invite_id: str) -> repo.InviteRow:
    async with db.with_tenant(tenant) as conn:
        row = await repo.get_invite(conn, UUID(invite_id))
    assert row is not None
    return row


async def _user(db: TenantDb, tenant: UUID, user_id: str) -> repo.UserRow:
    async with db.with_tenant(tenant) as conn:
        row = await repo.get_user(conn, UUID(user_id))
    assert row is not None
    return row


def _local_identity(kc_id: UUID, email: str = CAROL) -> VerifiedExternalIdentity:
    return VerifiedExternalIdentity(
        tenant_id=None,
        idp_alias=None,
        subject=str(kc_id),
        email=email,
        email_verified=True,
        acr="aal2",
        amr=["pwd", "otp"],
        auth_time=datetime.now(UTC),
        kc_sid=None,
    )


def _jit(db: TenantDb) -> JitProvisioner:
    return JitProvisioner(connect=db.with_tenant, connect_pre=db.no_tenant)


async def _sent_invite(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner
) -> tuple[dict[str, str], UUID]:
    r = await _invite(client)
    assert r.status_code == 201, r.text
    assert await runner.run_all(TENANT_A_ID, SEND) == 1
    user = await _user(db, TENANT_A_ID, r.json()["userId"])
    assert user.keycloak_user_id is not None
    return r.json(), user.keycloak_user_id


async def test_a_local_invite_creates_the_user_the_invite_and_one_job(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    r = await _invite(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["method"] == "local"
    user = await _user(db, TENANT_A_ID, body["userId"])
    assert (user.status, user.sso_managed, user.display_name) == ("invited", False, "Carol Client")
    invite = await _invite_row(db, TENANT_A_ID, body["inviteId"])
    assert (invite.status, invite.method, invite.invited_by) == ("pending", "local", ALICE_ID)
    assert (invite.expires_at - invite.created_at).days == 7
    assert await _count(db, "SELECT count(*) FROM jobs WHERE job_type = $1", SEND) == 1
    events = await su_fetch(db, "SELECT event_type FROM auth_event WHERE user_id = $1", user.id)
    assert ("invite.created",) in events
    # The local account's email now resolves to kaefer-demo before sign-in.
    async with db.no_tenant() as conn:
        target = await repo.resolve_login(conn, "email", CAROL)
    assert target is not None and target.tenant_id == TENANT_A_ID


async def test_the_send_invite_job_creates_one_keycloak_user_and_sends_once(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner, kc: FakeKeycloak
) -> None:
    r = await _invite(client)
    body = r.json()
    [job] = await runner.queued(TENANT_A_ID, SEND)
    await runner.run(TENANT_A_ID, job)
    [kc_user] = kc.users.values()
    assert kc_user["requiredActions"] == ["VERIFY_EMAIL", "UPDATE_PASSWORD", "CONFIGURE_TOTP"]
    assert kc_user["attributes"] == {"aip_user_id": [body["userId"]]}
    assert kc_user["firstName"] == "Carol" and kc_user["lastName"] == "Client"
    assert len(kc.emails) == 1 and kc.emails[0]["lifespan"] == "604800"
    invite = await _invite_row(db, TENANT_A_ID, body["inviteId"])
    assert invite.status == "sent" and invite.sent_at is not None
    assert invite.keycloak_user_id == UUID(str(kc_user["id"]))
    user = await _user(db, TENANT_A_ID, body["userId"])
    assert user.keycloak_user_id == invite.keycloak_user_id

    await runner.run(TENANT_A_ID, job)  # a redelivered job
    assert len(kc.users) == 1


async def test_invite_and_job_roll_back_together(db: TenantDb) -> None:
    class BoomError(Exception):
        pass

    with pytest.raises(BoomError):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await create_invite(conn, tenant_id=TENANT_A_ID, email=CAROL)
            raise BoomError
    assert await _count(db, "SELECT count(*) FROM app_user WHERE email = $1", CAROL) == 0
    assert await _count(db, "SELECT count(*) FROM user_invite") == 0
    assert await _count(db, "SELECT count(*) FROM jobs WHERE job_type = $1", SEND) == 0
    assert (
        await _count(db, "SELECT count(*) FROM procrastinate_jobs WHERE task_name = $1", SEND) == 0
    )


async def test_an_sso_invite_sends_nothing(
    client: httpx.AsyncClient, db: TenantDb, kc: FakeKeycloak
) -> None:
    r = await _invite(client, "dan@kaefer.test")
    assert r.status_code == 201, r.text
    assert r.json()["method"] == "sso"
    user = await _user(db, TENANT_A_ID, r.json()["userId"])
    assert (user.sso_managed, user.idp_alias, user.status) == (True, "kaefer-oidc", "invited")
    assert await _count(db, "SELECT count(*) FROM jobs WHERE job_type = $1", SEND) == 0
    assert kc.users == {}


async def test_an_invite_needs_a_fresh_second_factor(client: httpx.AsyncClient) -> None:
    stale = principal_headers(TENANT_A_ID, ALICE_ID, minutes_ago=11)
    r = await _invite(client, headers=stale)
    assert r.status_code == 401, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "STEP_UP_REQUIRED"
    assert detail["stepUpUrl"].startswith("/api/v1/auth/step-up/start?returnTo=")
    weak = principal_headers(TENANT_A_ID, ALICE_ID, aal=1, minutes_ago=1)
    assert (await _invite(client, headers=weak)).json()["detail"]["code"] == "STEP_UP_REQUIRED"


async def test_the_tenant_step_up_window_applies(client: httpx.AsyncClient, db: TenantDb) -> None:
    await su_execute(
        db,
        "INSERT INTO tenant_auth_policy (tenant_id, step_up_max_age_min) VALUES "
        f"('{TENANT_A_ID}', 30)",
    )
    r = await _invite(client, headers=principal_headers(TENANT_A_ID, ALICE_ID, minutes_ago=20))
    assert r.status_code == 201, r.text


async def test_without_the_permission_it_is_403_before_any_step_up(
    client: httpx.AsyncClient, grants: GrantTable
) -> None:
    grants.by_user[ALICE_ID] = {"identity.user.read"}
    stale = principal_headers(TENANT_A_ID, ALICE_ID, minutes_ago=30)
    r = await _invite(client, headers=stale)
    assert r.status_code == 403
    assert r.json()["permission"] == "identity.user.manage"


async def test_an_email_local_in_another_tenant_is_refused(client: httpx.AsyncClient) -> None:
    assert (await _invite(client)).status_code == 201
    r = await _invite(client, headers=BOB)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "EMAIL_IN_OTHER_TENANT"


async def test_another_tenants_sso_domain_cannot_be_invited(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    r = await _invite(client, "dan@kaefer.test", headers=BOB)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "EMAIL_DOMAIN_SSO"
    assert (
        await _count(db, "SELECT count(*) FROM app_user WHERE email = $1", "dan@kaefer.test") == 0
    )


async def test_an_existing_member_cannot_be_invited(client: httpx.AsyncClient) -> None:
    r = await _invite(client, "alice@kaefer.test")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "USER_EXISTS"


async def test_reinviting_revokes_the_previous_invite(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    first = (await _invite(client)).json()
    second = (await _invite(client)).json()
    assert first["userId"] == second["userId"]
    assert (await _invite_row(db, TENANT_A_ID, first["inviteId"])).status == "revoked"
    assert (await _invite_row(db, TENANT_A_ID, second["inviteId"])).status == "pending"


async def test_a_keycloak_rejection_marks_the_invite_failed(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner, kc: FakeKeycloak
) -> None:
    body = (await _invite(client)).json()
    kc.fail_with, kc.fail_message = 400, "User exists with same username"
    await runner.run_all(TENANT_A_ID, SEND)
    invite = await _invite_row(db, TENANT_A_ID, body["inviteId"])
    assert (invite.status, invite.last_error) == ("failed", "User exists with same username")
    events = await su_fetch(
        db, "SELECT event_type FROM auth_event WHERE user_id = $1", UUID(body["userId"])
    )
    assert ("invite.failed",) in events

    kc.fail_with = None
    r = await client.post(f"{INVITES}/{body['inviteId']}/resend", headers=ALICE)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending" and r.json()["lastError"] is None
    await runner.run_all(TENANT_A_ID, SEND)
    assert (await _invite_row(db, TENANT_A_ID, body["inviteId"])).status == "sent"


async def test_keycloak_unavailable_retries(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner, kc: FakeKeycloak
) -> None:
    body = (await _invite(client)).json()
    kc.fail_with = 503
    [job] = await runner.queued(TENANT_A_ID, SEND)
    with pytest.raises(KeycloakUnavailable):
        await runner.run(TENANT_A_ID, job)
    assert (await _invite_row(db, TENANT_A_ID, body["inviteId"])).status == "pending"


async def test_an_sso_invite_cannot_be_resent(client: httpx.AsyncClient) -> None:
    body = (await _invite(client, "dan@kaefer.test")).json()
    r = await client.post(f"{INVITES}/{body['inviteId']}/resend", headers=ALICE)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "INVITE_NOT_LOCAL"


async def test_first_sign_in_accepts_the_invite(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner
) -> None:
    body, kc_id = await _sent_invite(client, db, runner)
    result = await _jit(db).provision(_local_identity(kc_id))
    assert isinstance(result, Provisioned), result
    assert str(result.user_id) == body["userId"]
    assert (await _user(db, TENANT_A_ID, body["userId"])).status == "active"
    invite = await _invite_row(db, TENANT_A_ID, body["inviteId"])
    assert invite.status == "accepted" and invite.accepted_at is not None
    events = await su_fetch(
        db, "SELECT event_type FROM auth_event WHERE user_id = $1", UUID(body["userId"])
    )
    assert ("invite.accepted",) in events


async def test_a_revoked_invite_cannot_sign_in_and_its_account_is_disabled(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner, kc: FakeKeycloak
) -> None:
    body, kc_id = await _sent_invite(client, db, runner)
    r = await client.delete(f"{INVITES}/{body['inviteId']}", headers=ALICE)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "revoked"
    assert await runner.run_all(TENANT_A_ID, "identity.disable_keycloak_user") == 1
    assert kc.users[str(kc_id)]["enabled"] is False

    result = await _jit(db).provision(_local_identity(kc_id))
    assert isinstance(result, Denied) and result.code == "INVITE_INVALID"
    assert (await _user(db, TENANT_A_ID, body["userId"])).status == "invited"
    again = await client.delete(f"{INVITES}/{body['inviteId']}", headers=ALICE)
    assert again.status_code == 200  # idempotent


async def test_an_expired_or_unsent_invite_cannot_sign_in(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner
) -> None:
    body, kc_id = await _sent_invite(client, db, runner)
    await su_execute(
        db,
        "UPDATE user_invite SET expires_at = now() - interval '1 minute' "
        f"WHERE id = '{body['inviteId']}'",
    )
    result = await _jit(db).provision(_local_identity(kc_id))
    assert isinstance(result, Denied) and result.code == "INVITE_INVALID"

    await su_execute(
        db,
        "UPDATE user_invite SET expires_at = now() + interval '1 day', status = 'pending' "
        f"WHERE id = '{body['inviteId']}'",
    )
    result = await _jit(db).provision(_local_identity(kc_id))
    assert isinstance(result, Denied) and result.code == "INVITE_INVALID"


async def test_invites_are_tenant_scoped(client: httpx.AsyncClient, db: TenantDb) -> None:
    body = (await _invite(client)).json()
    mine = await client.get(INVITES, headers=ALICE)
    assert [i["id"] for i in mine.json()["items"]] == [body["inviteId"]]
    assert (await client.get(INVITES, params={"status": "sent"}, headers=ALICE)).json() == {
        "items": []
    }
    assert (await client.get(INVITES, headers=BOB)).json() == {"items": []}
    assert (await client.delete(f"{INVITES}/{body['inviteId']}", headers=BOB)).status_code == 404
    async with db.with_tenant(TENANT_B_ID) as conn:
        assert await repo.list_invites(conn) == []
    async with db.no_tenant() as conn:
        assert await repo.list_invites(conn) == []


async def test_mfa_reset(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner, kc: FakeKeycloak
) -> None:
    body, kc_id = await _sent_invite(client, db, runner)
    assert isinstance(await _jit(db).provision(_local_identity(kc_id)), Provisioned)
    user_id = UUID(body["userId"])
    async with db.with_tenant(TENANT_A_ID) as conn:
        await issue_session(
            conn,
            user_id=user_id,
            user_class="staff",
            aal=2,
            amr=["pwd", "otp"],
            authenticated_at=datetime.now(UTC),
            kc_sid=None,
        )
        await repo.mark_mfa_enrolled(conn, user_id)
    kc.credentials[str(kc_id)] = [{"id": "c-otp", "type": "otp"}]

    r = await client.post(f"/api/v1/identity/users/{user_id}/reset-mfa", headers=ALICE)
    assert r.status_code == 204, r.text
    assert await runner.run_all(TENANT_A_ID, "identity.reset_keycloak_mfa") == 1
    assert kc.credentials[str(kc_id)] == []
    assert "CONFIGURE_TOTP" in kc.users[str(kc_id)]["requiredActions"]  # type: ignore[operator]
    live = await _count(
        db, "SELECT count(*) FROM user_session WHERE user_id = $1 AND revoked_at IS NULL", user_id
    )
    assert live == 0
    reasons = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE user_id = $1", user_id
    )
    assert reasons == [("mfa_reset",)]
    async with db.with_tenant(TENANT_A_ID) as conn:
        assert await repo.mfa_enrolled_at(conn, user_id) is None

    alice = await client.post(f"/api/v1/identity/users/{ALICE_ID}/reset-mfa", headers=ALICE)
    assert alice.status_code == 409
    assert alice.json()["detail"]["code"] == "MFA_MANAGED_BY_IDP"
    other = await client.post(f"/api/v1/identity/users/{BOB_ID}/reset-mfa", headers=ALICE)
    assert other.status_code == 404


async def test_reinviting_after_a_revoke_enables_the_account_again(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner, kc: FakeKeycloak
) -> None:
    body, kc_id = await _sent_invite(client, db, runner)
    assert (await client.delete(f"{INVITES}/{body['inviteId']}", headers=ALICE)).status_code == 200
    assert await runner.run_all(TENANT_A_ID, "identity.disable_keycloak_user") == 1
    assert kc.users[str(kc_id)]["enabled"] is False

    again = (await _invite(client)).json()
    assert again["userId"] == body["userId"]
    await runner.run_all(TENANT_A_ID, SEND)
    assert kc.users[str(kc_id)]["enabled"] is True
    assert len(kc.users) == 1
    assert (await _invite_row(db, TENANT_A_ID, again["inviteId"])).status == "sent"
    result = await _jit(db).provision(_local_identity(kc_id))
    assert isinstance(result, Provisioned), result


async def test_a_disable_queued_before_a_reinvite_leaves_the_account_alone(
    client: httpx.AsyncClient, db: TenantDb, runner: JobRunner, kc: FakeKeycloak
) -> None:
    body, kc_id = await _sent_invite(client, db, runner)
    await client.delete(f"{INVITES}/{body['inviteId']}", headers=ALICE)
    await _invite(client)  # re-invited before the disable job ran
    assert await runner.run_all(TENANT_A_ID, "identity.disable_keycloak_user") == 1
    assert kc.users[str(kc_id)]["enabled"] is True


async def test_resending_a_superseded_invite_is_refused(
    client: httpx.AsyncClient, runner: JobRunner, kc: FakeKeycloak
) -> None:
    first = (await _invite(client)).json()
    kc.fail_with = 400
    await runner.run_all(TENANT_A_ID, SEND)  # the first invite fails
    kc.fail_with = None
    await _invite(client)  # a newer invite for the same person
    r = await client.post(f"{INVITES}/{first['inviteId']}/resend", headers=ALICE)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "INVITE_SUPERSEDED"
