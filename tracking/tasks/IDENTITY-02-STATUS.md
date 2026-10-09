# IDENTITY-02 status (WIP, 2026-10-09)

Branch `claude/p0-identity-02`. Migration revision **202610091851** (`identity_users`, revises 202610081200).

## Built and tested
- Migration: `app_user`, `tenant_membership` (tenant-table template, FORCE RLS, composite
  `(user_id, tenant_id)` FKs, FKs to `tenants`), append-only `auth_event` (aip_app: SELECT+INSERT
  only), `login_directory.kind` += `email`, SECURITY DEFINER `identity_register_email` (only for
  the bound `app.tenant_id` and only for a live local user of that tenant). Tables in `tables.py`.
- `jit.py`: pure `decide_jit` + `JitProvisioner` + `JitLoginHandler` (now the default behind the
  unchanged `ExternalLoginHandler` port). Tenant only from the IdP binding (SSO: cookie tenant +
  token email domain must be claimed by that tenant/IdP) or the local email registration.
  Fails closed for inactive/deleted tenant, deactivated or soft-deleted user, unverified email,
  unclaimed domain, no current membership, local/SSO mismatch. Advisory locks + one retry make
  concurrent first logins race-safe (mutation-checked: test fails without the locks).
- `principal.py` (Principal, PrincipalResolver, get_principal, x-test-principal stub gated by
  AIP_ENV=test + AUTH_TEST_STUB=1; create_app refuses the stub in production / non-test).
- `GET /api/v1/me` (principal -> require_active_tenant -> active live user, else 401/403).
- `api.py` exports get_user, list_users, find_by_email, set_user_status, record_auth_event,
  Principal; manifest permissions `identity.user.read`, `identity.user.manage`.
- Tenancy `api.py` now also exports `load_tenant`, `access_for_status`, `Denial` (smoke test updated).
- Tests: test_jit_unit.py (35), test_jit_db.py (30), test_me_db.py (15), all green against local
  Postgres; identity+tenancy+arch+schema+openapi export: 244 passed, 8 skipped (Keycloak, no Docker).
  New real-Keycloak e2e `test_alice_sso_is_provisioned_once_by_jit` (test_keycloak_flows.py) NOT run locally.

## Not done
- `db/schema.snapshot.sql` not regenerated (`uv run aip-db snapshot` on a fresh migrated DB, see agent rules).
- TS API client not regenerated (node_modules missing): `pnpm install && make generate-client`;
  `packages/api-client/openapi.json` is updated.
- `make check` and `python3 tools/next_task.py --check` not run in full; PROGRESS line, ADR not added.
- auth_event `ip`/`user_agent` stay NULL at login: the port passes only the identity (needs ADR to change).
- Stale `email` directory rows on email change are not removed (no unregister function).

## Commands
    cd apps/api && AIP_TEST_DATABASE_URL=postgresql://aip_test:aip_test@localhost:5432/aip_test uv run pytest -q aip/modules/identity
    make check && python3 tools/next_task.py --check
    uv run --python 3.13 pytest apps/api/tests/test_openapi_export.py

## For the security reviewer
- `identity_register_email` (SECURITY DEFINER): tenant-context and local-user checks; error leaks
  only "EMAIL_IN_OTHER_TENANT" to the calling tenant (spec-required 409).
- Local login: registration tenant is authoritative; a differing cookie tenant is refused (TENANT_MISMATCH).
- Denial codes (e.g. USER_DEACTIVATED vs NOT_INVITED) are shown only after Keycloak authenticated the account.
- Soft-deleted users block re-provisioning by subject or email until restored (deliberate fail-closed).
- `test_me_db.py` points the process engine at the test DB via DATABASE_URL and disposes it after.
