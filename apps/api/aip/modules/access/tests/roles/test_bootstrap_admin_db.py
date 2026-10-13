"""TESTING-09: ``aip-access bootstrap-admin`` on real Postgres (``aip_app``, RLS on).

The fixture tenants need a first ``tenant_admin`` before anyone can create projects or assign roles;
the bootstrap pre-creates an invited SSO user that the first sign-in links (identity's
``test_an_ensured_invited_sso_user_is_linked_on_first_sign_in``).
"""

from __future__ import annotations

import pytest
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.access.roles.cli import _bootstrap, main  # pyright: ignore[reportPrivateUsage]

from .conftest import seed_roles, su_fetch

EMAIL = "first.admin@kaefer.test"


async def _holders(db: TenantDb, email: str) -> list[tuple[object, ...]]:
    return await su_fetch(
        db,
        "SELECT u.status, u.sso_managed, u.idp_alias, u.keycloak_user_id, r.code, ra.scope_type,"
        " (SELECT count(*) FROM tenant_membership m WHERE m.user_id = u.id"
        "  AND m.deleted_at IS NULL)"
        " FROM app_user u"
        " JOIN role_assignment ra ON ra.user_id = u.id AND ra.deleted_at IS NULL"
        " JOIN role r ON r.id = ra.role_id"
        " WHERE u.email = $1",
        email,
    )


async def test_bootstrap_creates_an_invited_sso_admin_once(db: TenantDb) -> None:
    await seed_roles(TENANT_A_ID)
    assert await _bootstrap([(TENANT_A_ID, EMAIL, "kaefer-oidc")]) == 0
    rows = await _holders(db, EMAIL)
    assert rows == [("invited", True, "kaefer-oidc", None, "tenant_admin", "tenant", 1)]
    events = await su_fetch(
        db,
        "SELECT count(*) FROM domain_events WHERE event_name = 'access.role_assignment.created'"
        " AND tenant_id = $1 AND payload->>'roleCode' = 'tenant_admin'",
        TENANT_A_ID,
    )

    assert await _bootstrap([(TENANT_A_ID, EMAIL, "kaefer-oidc")]) == 0  # idempotent
    assert await _holders(db, EMAIL) == rows
    again = await su_fetch(
        db,
        "SELECT count(*) FROM domain_events WHERE event_name = 'access.role_assignment.created'"
        " AND tenant_id = $1 AND payload->>'roleCode' = 'tenant_admin'",
        TENANT_A_ID,
    )
    assert again == events and events[0][0] >= 1


async def test_bootstrap_stays_inside_its_tenant(db: TenantDb) -> None:
    await seed_roles(TENANT_A_ID)
    await seed_roles(TENANT_B_ID)
    await _bootstrap([(TENANT_B_ID, "admin@acme.test", "acme-oidc")])
    tenants = await su_fetch(
        db,
        "SELECT DISTINCT ra.tenant_id FROM role_assignment ra JOIN app_user u ON u.id = ra.user_id"
        " WHERE u.email = 'admin@acme.test'",
    )
    assert tenants == [(TENANT_B_ID,)]


async def test_bootstrap_without_seeded_roles_fails_loudly(db: TenantDb) -> None:
    await su_fetch(db, "UPDATE role SET deleted_at = now() WHERE code = 'tenant_admin' RETURNING 1")
    with pytest.raises(LookupError, match="seed-roles"):
        await _bootstrap([(TENANT_A_ID, EMAIL, "kaefer-oidc")])


@pytest.mark.parametrize("env", ["production", "Production", "prod", "", "staging"])
def test_bootstrap_runs_only_in_allowlisted_envs(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    monkeypatch.setenv("AIP_ENV", env)
    argv = ["bootstrap-admin", "--admin", f"{TENANT_A_ID},{EMAIL},kaefer-oidc"]
    assert main(argv) == 1


async def test_bootstrap_refuses_an_existing_local_account(db: TenantDb) -> None:
    await seed_roles(TENANT_A_ID)
    await su_fetch(
        db,
        "INSERT INTO app_user (id, tenant_id, email, display_name, user_class, status, sso_managed)"
        " VALUES (gen_random_uuid(), $1, 'local.admin@kaefer.test', 'local', 'staff', 'active',"
        " false) RETURNING 1",
        TENANT_A_ID,
    )
    with pytest.raises(ValueError, match="local or deactivated"):
        await _bootstrap([(TENANT_A_ID, "local.admin@kaefer.test", "kaefer-oidc")])
    assert await _holders(db, "local.admin@kaefer.test") == []


@pytest.mark.parametrize("value", ["nope", f"{TENANT_A_ID},not-an-email,x", "x,a@b.test,idp"])
def test_bootstrap_rejects_a_malformed_admin(value: str) -> None:
    with pytest.raises(SystemExit):
        main(["bootstrap-admin", "--admin", value])
