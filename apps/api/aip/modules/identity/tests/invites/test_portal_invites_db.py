"""IDENTITY-10 integration tests on real Postgres: portal (client) invites and their email job.

``create_invite(user_class="portal")`` is PORTAL-01's entry point: always a local account, a
``client`` membership, and an invite email that names the ``aip-portal`` client.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.identity import repository as repo
from aip.modules.identity.invites import InviteError, create_invite

from ..test_invites_unit import FakeKeycloak
from .conftest import JobRunner, su_fetch

SEND = "identity.send_invite"
CLIENT = "client.a@rio.example"


async def _portal_invite(db: TenantDb, email: str = CLIENT, user_class: str = "portal"):
    async with db.with_tenant(TENANT_A_ID) as conn:
        return await create_invite(
            conn,
            tenant_id=TENANT_A_ID,
            email=email,
            user_class=user_class,  # pyright: ignore[reportArgumentType]
            first_name="Rio",
            last_name="Client",
        )


async def test_a_portal_invite_is_local_with_a_client_membership(db: TenantDb) -> None:
    created = await _portal_invite(db)
    assert created.method == "local"
    async with db.with_tenant(TENANT_A_ID) as conn:
        user = await repo.get_user(conn, created.user_id)
        memberships = await repo.list_memberships(conn, created.user_id)
        events = [
            e for e in await repo.list_auth_events(conn) if e["event_type"] == "invite.created"
        ]
    assert user is not None
    assert (user.user_class, user.status, user.sso_managed, user.idp_alias) == (
        "portal",
        "invited",
        False,
        None,
    )
    assert [m.membership_type for m in memberships] == ["client"]
    registered = await su_fetch(
        db, "SELECT tenant_id FROM login_directory WHERE kind = 'email' AND key = $1", CLIENT
    )
    assert registered == [(TENANT_A_ID,)]
    jobs = await su_fetch(db, "SELECT count(*) FROM jobs WHERE job_type = $1", SEND)
    assert jobs == [(1,)]
    assert len(events) == 1
    assert events[0]["detail"]["audience"] == "portal"
    assert events[0]["detail"]["method"] == "local"


async def test_a_portal_invite_never_uses_company_sso(db: TenantDb) -> None:
    """``kaefer.test`` is the tenant's own SSO domain: a staff invite there is SSO, a portal one is
    refused by the email registration (an SSO domain cannot hold a local account)."""
    users_before = await su_fetch(db, "SELECT count(*) FROM app_user")
    with pytest.raises(InviteError) as refused:
        await _portal_invite(db, "dana@kaefer.test")
    assert (refused.value.status_code, refused.value.code) == (409, "EMAIL_DOMAIN_SSO")
    assert await su_fetch(db, "SELECT count(*) FROM app_user") == users_before
    assert await su_fetch(db, "SELECT count(*) FROM user_invite") == [(0,)]


async def test_an_invited_staff_email_cannot_be_reinvited_as_portal(db: TenantDb) -> None:
    await _portal_invite(db, "erin@rio.example", user_class="staff")
    with pytest.raises(InviteError) as refused:
        await _portal_invite(db, "erin@rio.example")
    assert (refused.value.status_code, refused.value.code) == (409, "USER_EXISTS")
    # The same class re-invites as before (the previous invite is revoked).
    again = await _portal_invite(db)
    second = await _portal_invite(db)
    assert again.user_id == second.user_id


async def test_the_invite_email_links_to_the_portal_client(
    db: TenantDb, runner: JobRunner, kc: FakeKeycloak
) -> None:
    portal = await _portal_invite(db)
    staff = await _portal_invite(db, "frank@rio.example", user_class="staff")
    assert await runner.run_all(TENANT_A_ID, SEND) == 2
    by_email = {str(u["email"]): uid for uid, u in kc.users.items()}
    clients = {str(e["user"]): e["client_id"] for e in kc.emails}
    assert clients[by_email[CLIENT]] == "aip-portal"
    assert clients[by_email["frank@rio.example"]] == "aip-api"
    async with db.with_tenant(TENANT_A_ID) as conn:
        for created in (portal, staff):
            invite = await repo.get_invite(conn, UUID(str(created.invite_id)))
            assert invite is not None and invite.status == "sent"
