"""JIT provisioning, users and memberships against real Postgres (IDENTITY-02).

Every assertion reads through ``aip_app`` (``tenant_db``), so row-level security applies. Seeding
runs as the superuser/owner only (``idb`` fixture in ``conftest.py``). Tenant A is
``kaefer-demo`` (``kaefer.test``, IdP ``kaefer-oidc``), tenant B is ``tenant-b`` (``acme.test``,
``acme-oidc``).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.fixtures.postgres import TenantDb, assert_unprivileged_url

from aip.modules.identity import repository as repo
from aip.modules.identity.jit import Denied, JitLoginHandler, JitProvisioner, Provisioned
from aip.modules.identity.schemas import VerifiedExternalIdentity
from aip.modules.identity.service import create_local_user
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.session import with_tenant

from .conftest import TENANT_A_ID, TENANT_B_ID, seed_sql

ALICE = "alice@kaefer.test"
BOB = "bob@acme.test"


def identity(
    email: str = ALICE,
    subject: UUID | str | None = None,
    *,
    tenant_id: UUID | None = TENANT_A_ID,
    idp_alias: str | None = "kaefer-oidc",
    verified: bool = True,
) -> VerifiedExternalIdentity:
    return VerifiedExternalIdentity(
        tenant_id=tenant_id,
        idp_alias=idp_alias,
        subject=str(subject or uuid4()),
        email=email,
        email_verified=verified,
        acr="aal1" if idp_alias else "aal2",
        amr=["fed"] if idp_alias else ["pwd", "otp"],
        auth_time=datetime.now(UTC),
        kc_sid=None,
    )


def local_identity(email: str, subject: UUID | None = None, *, tenant_id: UUID | None = None):
    return identity(email, subject, tenant_id=tenant_id, idp_alias=None)


def provisioner(db: TenantDb) -> JitProvisioner:
    return JitProvisioner(connect=db.with_tenant, connect_pre=db.no_tenant)


async def count(db: TenantDb, tenant: UUID, sql: str, **params: Any) -> int:
    async with db.with_tenant(tenant) as conn:
        return int((await conn.execute(text(sql), params)).scalar_one())


async def users(db: TenantDb, tenant: UUID, email: str | None = None) -> int:
    if email is None:
        return await count(db, tenant, "SELECT count(*) FROM app_user")
    return await count(db, tenant, "SELECT count(*) FROM app_user WHERE email = :e", e=email)


async def events(db: TenantDb, tenant: UUID) -> list[dict[str, Any]]:
    async with db.with_tenant(tenant) as conn:
        return [dict(e) for e in await repo.list_auth_events(conn)]


async def seed_user(db: TenantDb, tenant: UUID, email: str, **kw: Any) -> UUID:
    """Insert a user (and a current membership unless ``membership=False``) as ``aip_app``."""
    membership = kw.pop("membership", True)
    values: dict[str, Any] = {
        "display_name": email.split("@")[0],
        "user_class": "staff",
        "status": "active",
        "sso_managed": True,
    }
    values.update(kw)
    async with db.with_tenant(tenant) as conn:
        user_id = await repo.insert_user(conn, tenant_id=tenant, email=email, **values)
        if membership:
            await repo.insert_membership(
                conn, tenant_id=tenant, user_id=user_id, membership_type="member"
            )
    return user_id


async def get(db: TenantDb, tenant: UUID, user_id: UUID) -> repo.UserRow | None:
    async with db.with_tenant(tenant) as conn:
        return await repo.get_user(conn, user_id)


# --- the spec's integration cases --------------------------------------------------------------


async def test_jit_twice_creates_one_user_and_refreshes_last_login(idb: TenantDb) -> None:
    s1 = uuid4()
    jit = provisioner(idb)
    first = await jit.provision(identity(ALICE, s1))
    assert isinstance(first, Provisioned) and first.action == "created"
    assert first.tenant_id == TENANT_A_ID
    user = await get(idb, TENANT_A_ID, first.user_id)
    assert user is not None and user.sso_managed and user.status == "active"
    assert user.keycloak_user_id == s1 and user.idp_alias == "kaefer-oidc"
    assert user.user_class == "staff" and user.last_login_at is not None
    first_login = user.last_login_at

    second = await jit.provision(identity(ALICE, s1))
    assert isinstance(second, Provisioned) and second.action == "refreshed"
    assert second.user_id == first.user_id
    assert await users(idb, TENANT_A_ID) == 1
    assert await count(idb, TENANT_A_ID, "SELECT count(*) FROM tenant_membership") == 1
    async with idb.with_tenant(TENANT_A_ID) as conn:
        memberships = await repo.list_memberships(conn, first.user_id)
    assert [m.membership_type for m in memberships] == ["member"]
    again = await get(idb, TENANT_A_ID, first.user_id)
    assert again is not None and again.last_login_at is not None
    assert again.last_login_at > first_login
    kinds = [(e["event_type"], e["detail"].get("action")) for e in await events(idb, TENANT_A_ID)]
    assert kinds == [("login.succeeded", "refreshed"), ("login.succeeded", "created")]
    # Nothing leaked into tenant B.
    assert await users(idb, TENANT_B_ID) == 0
    assert await events(idb, TENANT_B_ID) == []


async def test_local_login_with_no_directory_row_is_not_invited(idb: TenantDb) -> None:
    result = await provisioner(idb).provision(local_identity("nobody@client.test"))
    assert isinstance(result, Denied) and result.code == "NOT_INVITED"
    assert await users(idb, TENANT_A_ID) == 0
    assert await users(idb, TENANT_B_ID) == 0


async def test_sso_never_links_a_local_account_with_the_same_email(idb: TenantDb) -> None:
    local_id = await seed_user(idb, TENANT_A_ID, ALICE, sso_managed=False, status="active")
    result = await provisioner(idb).provision(identity(ALICE))
    assert isinstance(result, Denied) and result.code == "ACCOUNT_LINK_REQUIRED"
    assert await users(idb, TENANT_A_ID) == 1
    user = await get(idb, TENANT_A_ID, local_id)
    assert user is not None and user.keycloak_user_id is None and not user.sso_managed
    [event] = await events(idb, TENANT_A_ID)
    assert event["event_type"] == "login.denied"
    assert event["detail"]["reason"] == "account_link_required"
    assert event["user_id"] == local_id


async def test_sso_never_links_an_invited_local_account(idb: TenantDb) -> None:
    await seed_user(idb, TENANT_A_ID, ALICE, sso_managed=False, status="invited")
    result = await provisioner(idb).provision(identity(ALICE))
    assert isinstance(result, Denied) and result.code == "ACCOUNT_LINK_REQUIRED"
    assert await users(idb, TENANT_A_ID) == 1


async def test_aip_app_cannot_update_or_delete_auth_events(idb: TenantDb) -> None:
    result = await provisioner(idb).provision(identity(ALICE))
    assert isinstance(result, Provisioned)
    for sql in (
        "UPDATE auth_event SET event_type = 'x'",
        "DELETE FROM auth_event",
        "TRUNCATE auth_event",
    ):
        with pytest.raises(DBAPIError) as info:
            async with idb.with_tenant(TENANT_A_ID) as conn:
                await conn.execute(text(sql))
        assert isinstance(info.value.orig, Exception)
        assert "permission denied" in str(info.value.orig)
    assert len(await events(idb, TENANT_A_ID)) == 1


async def test_list_users_sees_only_the_bound_tenant(idb: TenantDb) -> None:
    a1 = await seed_user(idb, TENANT_A_ID, "a1@kaefer.test")
    a2 = await seed_user(idb, TENANT_A_ID, "a2@kaefer.test", status="invited")
    b1 = await seed_user(idb, TENANT_B_ID, "b1@acme.test")
    async with idb.with_tenant(TENANT_A_ID) as conn:
        page = await repo.list_users(conn)
        assert {u.id for u in page.items} == {a1, a2}
        assert all(u.tenant_id == TENANT_A_ID for u in page.items)
        assert await repo.get_user(conn, b1) is None  # B's id is invisible, not an error
        assert await repo.find_by_email(conn, "b1@acme.test") is None
        assert [u.id for u in (await repo.list_users(conn, status="invited")).items] == [a2]
        assert [u.id for u in (await repo.list_users(conn, q="A1@")).items] == [a1]
        assert (await repo.list_users(conn, q="%")).items == []  # LIKE wildcards are escaped
        first = await repo.list_users(conn, limit=1)
        assert len(first.items) == 1 and first.next_cursor is not None
        rest = await repo.list_users(conn, limit=1, cursor=first.next_cursor)
        assert {first.items[0].id, rest.items[0].id} == {a1, a2} and rest.next_cursor is None
        with pytest.raises(ValueError, match="limit"):
            await repo.list_users(conn, limit=101)
        with pytest.raises(ValueError, match="cursor"):
            await repo.list_users(conn, cursor="!!")
    async with idb.with_tenant(TENANT_B_ID) as conn:
        assert [u.id for u in (await repo.list_users(conn)).items] == [b1]
    async with idb.no_tenant() as conn:
        assert (await repo.list_users(conn)).items == []


async def test_local_email_registration_maps_to_one_tenant(idb: TenantDb) -> None:
    carol = "carol@client.test"
    async with idb.with_tenant(TENANT_A_ID) as conn:
        await create_local_user(conn, tenant_id=TENANT_A_ID, email=carol, display_name="Carol")
    async with idb.no_tenant() as conn:
        target = await repo.resolve_login(conn, "email", carol)
        assert target is not None and target.tenant_id == TENANT_A_ID
        assert target.idp_alias is None
        upper = await repo.resolve_login(conn, "email", carol.upper())
        assert upper is not None and upper.tenant_id == TENANT_A_ID
    with pytest.raises(repo.EmailInOtherTenantError):
        async with idb.with_tenant(TENANT_B_ID) as conn:
            await create_local_user(conn, tenant_id=TENANT_B_ID, email=carol, display_name="C")
    assert await users(idb, TENANT_B_ID) == 0  # rolled back with the failed registration
    async with idb.no_tenant() as conn:
        target = await repo.resolve_login(conn, "email", carol)
        assert target is not None and target.tenant_id == TENANT_A_ID


async def test_register_email_is_bound_to_the_current_tenant_and_a_local_user(
    idb: TenantDb,
) -> None:
    # Another tenant's id, or an email with no local user in this tenant, is refused.
    sql = "SELECT identity_register_email(CAST(:e AS citext), :t)"
    await seed_user(idb, TENANT_A_ID, "dan@client.test", sso_managed=False, status="invited")
    await seed_user(idb, TENANT_A_ID, "sso@kaefer.test", sso_managed=True)
    for email, tenant in (
        ("dan@client.test", TENANT_B_ID),  # tenant B named while bound to A
        ("ghost@client.test", TENANT_A_ID),  # no such user
        ("sso@kaefer.test", TENANT_A_ID),  # SSO users are never registered
    ):
        with pytest.raises(DBAPIError) as info:
            async with idb.with_tenant(TENANT_A_ID) as conn:
                await conn.execute(text(sql), {"e": email, "t": tenant})
        assert isinstance(info.value.orig, Exception)
        assert "TENANT_CONTEXT_MISMATCH" in str(info.value.orig) or "EMAIL_NOT_A_LOCAL_USER" in str(
            info.value.orig
        )
    with pytest.raises(DBAPIError):
        async with idb.no_tenant() as conn:
            await conn.execute(text(sql), {"e": "dan@client.test", "t": TENANT_A_ID})
    # aip_app still cannot touch the directory table itself.
    with pytest.raises(DBAPIError) as info:
        async with idb.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(
                text(
                    "INSERT INTO login_directory (kind, key, tenant_id) "
                    "VALUES ('email', 'x@client.test', :t)"
                ),
                {"t": TENANT_A_ID},
            )
    assert isinstance(info.value.orig, Exception)
    assert "permission denied" in str(info.value.orig)


# --- cross-tenant -------------------------------------------------------------------------------


async def test_same_email_in_both_tenants_is_two_users_with_no_leakage(idb: TenantDb) -> None:
    # tenant-b invited alice@kaefer.test (e.g. as a guest). Her kaefer SSO login must never
    # touch that row: the tenant comes from the kaefer IdP binding, not from the email.
    b_alice = await seed_user(idb, TENANT_B_ID, ALICE, sso_managed=True, status="invited")
    result = await provisioner(idb).provision(identity(ALICE))
    assert isinstance(result, Provisioned) and result.action == "created"
    assert result.tenant_id == TENANT_A_ID and result.user_id != b_alice
    b_row = await get(idb, TENANT_B_ID, b_alice)
    assert b_row is not None and b_row.status == "invited" and b_row.keycloak_user_id is None
    assert b_row.last_login_at is None
    assert await get(idb, TENANT_A_ID, b_alice) is None
    assert await get(idb, TENANT_B_ID, result.user_id) is None
    assert await users(idb, TENANT_A_ID, ALICE) == 1
    assert await users(idb, TENANT_B_ID, ALICE) == 1
    assert [e["event_type"] for e in await events(idb, TENANT_B_ID)] == []


async def test_one_tenants_idp_cannot_provision_another_tenants_email(idb: TenantDb) -> None:
    # kaefer's IdP asserts bob@acme.test: acme.test is tenant B's domain. Nothing is created in
    # either tenant, and nothing is written to tenant B.
    result = await provisioner(idb).provision(identity(BOB))
    assert isinstance(result, Denied) and result.code == "DOMAIN_NOT_CLAIMED"
    assert await users(idb, TENANT_A_ID) == 0 and await users(idb, TENANT_B_ID) == 0
    assert await events(idb, TENANT_B_ID) == []
    [event] = await events(idb, TENANT_A_ID)
    assert event["detail"]["reason"] == "domain_not_claimed"


async def test_tenant_and_idp_must_match_the_claimed_domain(idb: TenantDb) -> None:
    # Defence in depth behind IDENTITY-01's binding check: a tenant B binding with kaefer's IdP,
    # or tenant A with acme's IdP, never provisions.
    for ident in (
        identity(ALICE, tenant_id=TENANT_B_ID, idp_alias="kaefer-oidc"),
        identity(ALICE, tenant_id=TENANT_A_ID, idp_alias="acme-oidc"),
        identity(BOB, tenant_id=TENANT_A_ID, idp_alias="acme-oidc"),
    ):
        result = await provisioner(idb).provision(ident)
        assert isinstance(result, Denied) and result.code == "DOMAIN_NOT_CLAIMED"
    assert await users(idb, TENANT_A_ID) == 0 and await users(idb, TENANT_B_ID) == 0


async def test_sso_identity_without_a_tenant_binding_is_refused(idb: TenantDb) -> None:
    result = await provisioner(idb).provision(identity(ALICE, tenant_id=None))
    assert isinstance(result, Denied) and result.code == "TENANT_UNRESOLVED"
    assert await users(idb, TENANT_A_ID) == 0


async def test_local_account_registered_to_a_is_refused_with_a_b_binding(idb: TenantDb) -> None:
    carol = "carol@client.test"
    async with idb.with_tenant(TENANT_A_ID) as conn:
        await create_local_user(conn, tenant_id=TENANT_A_ID, email=carol, display_name="Carol")
    result = await provisioner(idb).provision(local_identity(carol, tenant_id=TENANT_B_ID))
    assert isinstance(result, Denied) and result.code == "TENANT_MISMATCH"
    assert await users(idb, TENANT_B_ID) == 0
    async with idb.with_tenant(TENANT_A_ID) as conn:
        user = await repo.find_by_email(conn, carol)
    assert user is not None and user.keycloak_user_id is None and user.status == "invited"


async def test_invited_local_account_is_linked_and_activated(idb: TenantDb) -> None:
    carol, sub = "carol@client.test", uuid4()
    async with idb.with_tenant(TENANT_A_ID) as conn:
        carol_id = await create_local_user(
            conn, tenant_id=TENANT_A_ID, email=carol, display_name="Carol"
        )
    result = await provisioner(idb).provision(local_identity(carol, sub))
    assert isinstance(result, Provisioned) and result.action == "linked"
    assert result.user_id == carol_id and result.tenant_id == TENANT_A_ID
    user = await get(idb, TENANT_A_ID, carol_id)
    assert user is not None and user.status == "active" and user.keycloak_user_id == sub
    assert not user.sso_managed and user.idp_alias is None
    again = await provisioner(idb).provision(local_identity(carol, sub))
    assert isinstance(again, Provisioned) and again.action == "refreshed"
    # A second Keycloak account with the same email is never linked over the first.
    other = await provisioner(idb).provision(local_identity(carol, uuid4()))
    assert isinstance(other, Denied) and other.code == "ACCOUNT_LINK_REQUIRED"
    assert await users(idb, TENANT_A_ID) == 1


async def test_local_sign_in_never_creates_a_user(idb: TenantDb) -> None:
    # Even for a known tenant domain (cookie bound to tenant A) and a verified email.
    for ident in (
        local_identity("newbie@client.test"),
        local_identity("newbie@kaefer.test", tenant_id=TENANT_A_ID),
    ):
        result = await provisioner(idb).provision(ident)
        assert isinstance(result, Denied) and result.code == "NOT_INVITED"
    assert await users(idb, TENANT_A_ID) == 0


# --- every other denial path --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("suspended", "TENANT_SUSPENDED"),
        ("offboarding", "TENANT_OFFBOARDED"),
        ("offboarded", "TENANT_OFFBOARDED"),
        ("provisioning", "TENANT_NOT_READY"),
    ],
)
async def test_inactive_tenant_fails_closed(idb: TenantDb, status: str, code: str) -> None:
    existing = await seed_user(idb, TENANT_A_ID, "linked@kaefer.test", keycloak_user_id=uuid4())
    await seed_sql(idb, f"UPDATE tenants SET status = '{status}' WHERE id = '{TENANT_A_ID}'")
    result = await provisioner(idb).provision(identity(ALICE))
    assert isinstance(result, Denied) and result.code == code and result.status_code == 403
    assert await users(idb, TENANT_A_ID) == 1  # only the pre-existing user
    row = await get(idb, TENANT_A_ID, existing)
    assert row is not None and row.last_login_at is None
    [event] = await events(idb, TENANT_A_ID)
    assert event["event_type"] == "login.denied" and event["detail"]["reason"] == code.lower()


async def test_soft_deleted_tenant_fails_closed(idb: TenantDb) -> None:
    await seed_sql(idb, f"UPDATE tenants SET deleted_at = now() WHERE id = '{TENANT_A_ID}'")
    result = await provisioner(idb).provision(identity(ALICE))
    assert isinstance(result, Denied) and result.code == "TENANT_UNKNOWN"
    assert await users(idb, TENANT_A_ID) == 0


async def test_deactivated_user_is_refused_and_never_reactivated(idb: TenantDb) -> None:
    sub = uuid4()
    user_id = await seed_user(idb, TENANT_A_ID, ALICE, keycloak_user_id=sub)
    async with idb.with_tenant(TENANT_A_ID) as conn:
        await repo.set_user_status(conn, user_id, "deactivated")
    for ident in (identity(ALICE, sub), identity(ALICE)):  # by subject, then by email
        result = await provisioner(idb).provision(ident)
        assert isinstance(result, Denied) and result.code == "USER_DEACTIVATED"
    row = await get(idb, TENANT_A_ID, user_id)
    assert row is not None and row.status == "deactivated" and row.deactivated_at is not None
    assert row.last_login_at is None
    assert await users(idb, TENANT_A_ID) == 1


async def test_soft_deleted_user_is_refused_and_not_recreated(idb: TenantDb) -> None:
    sub = uuid4()
    user_id = await seed_user(idb, TENANT_A_ID, ALICE, keycloak_user_id=sub)
    await seed_sql(
        idb,
        f"UPDATE app_user SET deleted_at = now() WHERE id = '{user_id}'",
    )
    for ident in (identity(ALICE, sub), identity(ALICE)):  # by subject, then by email
        result = await provisioner(idb).provision(ident)
        assert isinstance(result, Denied) and result.code == "USER_REMOVED"
    assert await users(idb, TENANT_A_ID) == 1  # the deleted row only; nothing new


async def test_unverified_email_never_provisions(idb: TenantDb) -> None:
    result = await provisioner(idb).provision(identity(ALICE, verified=False))
    assert isinstance(result, Denied) and result.code == "EMAIL_NOT_VERIFIED"
    invited = await seed_user(idb, TENANT_A_ID, "inv@kaefer.test", status="invited")
    result = await provisioner(idb).provision(identity("inv@kaefer.test", verified=False))
    assert isinstance(result, Denied) and result.code == "EMAIL_NOT_VERIFIED"
    row = await get(idb, TENANT_A_ID, invited)
    assert row is not None and row.keycloak_user_id is None and row.status == "invited"


async def test_invited_or_scim_sso_user_is_linked_by_email(idb: TenantDb) -> None:
    invited = await seed_user(idb, TENANT_A_ID, ALICE, status="invited")
    scim = await seed_user(idb, TENANT_A_ID, "scim@kaefer.test", status="active")
    sub = uuid4()
    result = await provisioner(idb).provision(identity(ALICE, sub))
    assert isinstance(result, Provisioned) and result.action == "linked"
    assert result.user_id == invited
    row = await get(idb, TENANT_A_ID, invited)
    assert row is not None and row.status == "active" and row.keycloak_user_id == sub
    result = await provisioner(idb).provision(identity("SCIM@kaefer.test"))  # citext match
    assert isinstance(result, Provisioned) and result.user_id == scim
    assert await users(idb, TENANT_A_ID) == 2


async def test_user_without_a_current_membership_is_refused(idb: TenantDb) -> None:
    sub = uuid4()
    user_id = await seed_user(idb, TENANT_A_ID, ALICE, keycloak_user_id=sub, membership=False)
    result = await provisioner(idb).provision(identity(ALICE, sub))
    assert isinstance(result, Denied) and result.code == "MEMBERSHIP_INACTIVE"
    async with idb.with_tenant(TENANT_A_ID) as conn:
        await repo.insert_membership(
            conn,
            tenant_id=TENANT_A_ID,
            user_id=user_id,
            membership_type="member",
            valid_from=date.today() - timedelta(days=30),
            valid_to=date.today() - timedelta(days=1),
        )
    result = await provisioner(idb).provision(identity(ALICE, sub))
    assert isinstance(result, Denied) and result.code == "MEMBERSHIP_INACTIVE"


async def test_sso_user_cannot_sign_in_with_a_local_password(idb: TenantDb) -> None:
    sub = uuid4()
    await seed_user(idb, TENANT_A_ID, "eve@client.test", keycloak_user_id=sub, sso_managed=True)
    # A stale directory row (seeded directly; the function refuses SSO users) lets the local
    # sign-in reach tenant A: the linked SSO user must still refuse a password login.
    await seed_sql(
        idb,
        "INSERT INTO login_directory (kind, key, tenant_id) "
        f"VALUES ('email', 'eve@client.test', '{TENANT_A_ID}')",
    )
    result = await provisioner(idb).provision(local_identity("eve@client.test", sub))
    assert isinstance(result, Denied) and result.code == "SSO_REQUIRED"


async def test_unusable_subject_or_email_is_refused(idb: TenantDb) -> None:
    result = await provisioner(idb).provision(identity(ALICE, "not-a-uuid"))
    assert isinstance(result, Denied) and result.code == "INVALID_SUBJECT"
    result = await provisioner(idb).provision(
        identity(ALICE, "00000000-0000-0000-0000-000000000000")
    )
    assert isinstance(result, Denied) and result.code == "INVALID_SUBJECT"
    result = await provisioner(idb).provision(identity("no-at-sign"))
    assert isinstance(result, Denied) and result.code == "INVALID_EMAIL"
    assert await users(idb, TENANT_A_ID) == 0


async def test_refusal_bodies_name_no_tenant_email_or_subject(idb: TenantDb) -> None:
    sub = uuid4()
    handler = JitLoginHandler(provisioner(idb))
    for ident in (identity(BOB, sub), local_identity("nobody@client.test", sub)):
        response = await handler(ident)
        assert response.status_code == 403
        body = bytes(response.body).decode()
        assert set(json.loads(body)) == {"code", "detail"}
        for secret in (str(TENANT_A_ID), str(TENANT_B_ID), "kaefer", "acme", "@", str(sub)):
            assert secret not in body


# --- concurrency --------------------------------------------------------------------------------


async def test_concurrent_first_logins_create_exactly_one_user(idb: TenantDb) -> None:
    assert_unprivileged_url(idb.db.app_url)
    engine = create_app_engine(EngineSettings(url=idb.db.app_url, pool_size=8, max_overflow=0))
    try:

        def connect(tenant: UUID):
            return with_tenant(tenant, engine=engine)

        def connect_pre():
            return engine.begin()

        jit = JitProvisioner(connect=connect, connect_pre=connect_pre)
        sub = uuid4()
        results = await asyncio.gather(*(jit.provision(identity(ALICE, sub)) for _ in range(8)))
        assert all(isinstance(r, Provisioned) for r in results)
        provisioned = [r for r in results if isinstance(r, Provisioned)]
        assert len({r.user_id for r in provisioned}) == 1
        assert sorted(r.action for r in provisioned) == ["created"] + ["refreshed"] * 7

        # Same email, two different Keycloak accounts racing: one wins, the other is refused.
        bob_like = "racer@kaefer.test"
        racing = await asyncio.gather(
            jit.provision(identity(bob_like, uuid4())), jit.provision(identity(bob_like, uuid4()))
        )
        assert sorted(type(r).__name__ for r in racing) == ["Denied", "Provisioned"]
    finally:
        await engine.dispose()
    assert await users(idb, TENANT_A_ID, ALICE) == 1
    assert await users(idb, TENANT_A_ID, "racer@kaefer.test") == 1
    assert await count(idb, TENANT_A_ID, "SELECT count(*) FROM tenant_membership") == 2


async def test_rls_blocks_writing_a_user_into_another_tenant(idb: TenantDb) -> None:
    with pytest.raises(DBAPIError) as info:
        async with idb.with_tenant(TENANT_A_ID) as conn:
            await repo.insert_user(
                conn,
                tenant_id=TENANT_B_ID,
                email="x@acme.test",
                display_name="x",
                user_class="staff",
                status="active",
                sso_managed=True,
            )
    assert isinstance(info.value.orig, Exception)
    assert "row-level security" in str(info.value.orig)
    # A membership cannot point at another tenant's user (composite foreign key).
    b_user = await seed_user(idb, TENANT_B_ID, "b@acme.test")
    with pytest.raises(DBAPIError):
        async with idb.with_tenant(TENANT_A_ID) as conn:
            await repo.insert_membership(
                conn, tenant_id=TENANT_A_ID, user_id=b_user, membership_type="member"
            )
