# IDENTITY-02 — Users and tenant membership, JIT provisioning, GET /me
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07); identity per ADR 0005 rev 2 -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02, IDENTITY-01, TENANCY-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md) (ignore every WorkOS reference: ADR 0005)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0005](../../docs/adr/0005-identity-architecture.md) rev 2 (Keycloak holds every staff password and MFA factor; the app holds none), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/identity/data-model.md) (tables `app_user`, `tenant_membership`, `auth_event`), [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) (rows 5 and 6 of the gaps table)

## Spec

Keep one `app_user` per person per tenant with tenant membership, provision SSO users just in time at first login (never silently linking Keycloak-local accounts, and never creating local accounts that were not invited), and expose `GET /api/v1/me` from the FastAPI backend.

- **files**:
  - apps/api/migrations/versions/<rev>_identity_users.py
  - apps/api/aip/modules/identity/tables.py
  - apps/api/aip/modules/identity/repository.py
  - apps/api/aip/modules/identity/service.py
  - apps/api/aip/modules/identity/jit.py
  - apps/api/aip/modules/identity/principal.py
  - apps/api/aip/modules/identity/routes.py
  - apps/api/aip/modules/identity/schemas.py
  - apps/api/aip/modules/identity/api.py
  - apps/api/aip/modules/identity/manifest.toml
  - apps/api/aip/modules/identity/tests/
- **steps**:
  - 1. Write the Alembic revision (raw SQL via `op.execute`) from the `db/templates/` tenant-table template: FORCE RLS, `USING` + `WITH CHECK` on `NULLIF(current_setting('app.tenant_id', true), '')::uuid`. Table `app_user`: id, tenant_id, organisation_id NULL, user_class (`staff`|`field`|`portal`), email citext, display_name, idp_alias NULL (NULL for a Keycloak-local account), keycloak_user_id uuid NULL (the ID token `sub`, used for admin-API calls), external_id NULL, sso_managed bool, status (`invited`|`active`|`deactivated`), deactivated_at, last_login_at, sync_version, created_at, updated_at, deleted_at. Indexes: UNIQUE (tenant_id, email) WHERE deleted_at IS NULL, and UNIQUE (tenant_id, keycloak_user_id) WHERE keycloak_user_id IS NOT NULL. Use `idp_alias`/`keycloak_user_id`, not `workos_*`. There is no password hash or MFA column: Keycloak holds every staff credential (ADR 0005 rev 2). Table `tenant_membership`: tenant_id, user_id, organisation_id NULL, membership_type (`member`|`client`|`subcontractor`|`guest`), valid_from, valid_to, timestamps. Table `auth_event` comes from the append-only template: id, tenant_id, user_id NULL, event_type, ip inet, user_agent, detail jsonb, occurred_at, with only INSERT and SELECT granted to `aip_app`. Declare all three as SQLAlchemy Core `Table` objects in `tables.py` so the CI schema-diff check passes. IDs are UUIDv7 generated in the app.
  - 2. In the same revision, extend `login_directory.kind` with `email` and add SECURITY DEFINER `identity_register_email(p_email citext, p_tenant uuid)`. The callback uses it to find the tenant of a Keycloak-local account when the pre-auth cookie carries no tenant (unknown domain). `service.py` calls it whenever a local (`sso_managed=false`) user is created or their email changes. It raises `EMAIL_IN_OTHER_TENANT` when the email is already registered to another tenant, so a local email maps to exactly one tenant. SSO users are not registered; their tenant comes from the email domain.
  - 3. JIT provisioning in `jit.py` replaces the IDENTITY-01 placeholder `ExternalLoginHandler`. When `identity.tenant_id` is NULL (a local account from an unknown domain), resolve it first with `identity_resolve_login('email', email)`; no row gives `NOT_INVITED`. Keep the decision as a pure function `decide_jit(existing, email_verified, domain_claimed, via_sso) -> JitDecision`, then apply it inside `async with with_tenant(ctx) as conn:` (from `aip.platform.db`): (a) find by `keycloak_user_id` and refresh email, display_name and last_login_at; an `invited` user becomes `active` on first sign-in; (b) otherwise, if `email_verified` (and, for SSO, the email domain is claimed by this tenant), find by email: an invited user or an SSO user gets `keycloak_user_id` linked; for an SSO login, a local account (`sso_managed=false`) is refused with `ACCOUNT_LINK_REQUIRED`; (c) otherwise, for an SSO login only, create the user (user_class `staff`, sso_managed=true, status `active`) plus a `member` membership. A local login with no matching user is refused with `NOT_INVITED`: local accounts exist only through invites (IDENTITY-04). A deactivated user is refused with `USER_DEACTIVATED`, and login never reactivates. Write `auth_event` `login.succeeded` or `login.denied` with a reason.
  - 4. `principal.py`: the Pydantic v2 model `Principal {kind: Literal['user'], tenant_id: UUID, user_id: UUID, user_class: Literal['staff','field','portal'], session_id: UUID | None, aal: Literal[1, 2], amr: list[str]}` (camelCase JSON aliases) and the `PrincipalResolver` `Protocol`, which IDENTITY-03's session dependency implements. Expose `get_principal` as a FastAPI dependency. Until IDENTITY-03, a test-only resolver reads the `x-test-principal` header, but only when `AIP_ENV=test` and `AUTH_TEST_STUB=1`. The app factory (`create_app()`) raises `RuntimeError('test auth stub forbidden in production')` if `AUTH_TEST_STUB=1` is set with `AIP_ENV=production`.
  - 5. `GET /api/v1/me` (authenticated) returns `{user:{id,email,displayName,userClass,status}, tenant:{id,slug,name}, memberships:[...], aal, amr}` as a Pydantic response model, so it appears in the OpenAPI document for `packages/api-client`. It returns 401 with no principal or a deactivated user.
  - 6. `api.py` exports `get_user`, `list_users(conn, *, q=None, status=None, user_class=None, cursor=None, limit<=100)`, `find_by_email`, `set_user_status`, `record_auth_event` and the `Principal` type. Add permissions `identity.user.read` and `identity.user.manage` (privileged) to `manifest.toml`.
- **acceptance**:
  - The first Keycloak login for `alice@kaefer.test` creates exactly one `app_user` (sso_managed=true, status active) and one `tenant_membership`. A second login creates nothing and updates `last_login_at`.
  - A Keycloak-local account with the same email is never linked to an SSO identity automatically, and a local sign-in never creates a user.
  - `aip_app` cannot UPDATE or DELETE `auth_event`.
  - `/me` and `list_users` never return another tenant's data.
- **tests** (pytest; integration uses testcontainers-python Postgres connected as `aip_app`):
  - **unit**:
    - `decide_jit(existing=None, email_verified=True, domain_claimed=True, via_sso=True)` returns `create`.
    - `decide_jit(existing=None, email_verified=True, domain_claimed=False, via_sso=False)` returns `refuse:NOT_INVITED`.
    - `decide_jit(existing=UserRow(sso_managed=False, status='active'), email_verified=True, domain_claimed=True, via_sso=True)` returns `refuse:ACCOUNT_LINK_REQUIRED`.
    - `decide_jit(existing=UserRow(sso_managed=False, status='invited'), email_verified=True, domain_claimed=False, via_sso=False)` returns `link`.
    - `decide_jit(existing=None, email_verified=False, domain_claimed=True, via_sso=True)` returns `refuse:EMAIL_NOT_VERIFIED`.
    - `decide_jit(existing=UserRow(status='deactivated'), ...)` returns `refuse:USER_DEACTIVATED`.
    - `Principal.model_validate({'kind':'user', 'userClass':'admin', ...})` raises `ValidationError` whose error `loc` is `('userClass',)`.
  - **integration**:
    - Run JIT twice for Keycloak user id `s1`. Expected: 1 `app_user` row, with `last_login_at` updated on the second run.
    - Run JIT for a local identity (`idp_alias=None`, `tenant_id=None`) for `nobody@client.test`, which has no `login_directory` row. Expected: `NOT_INVITED`, and no `app_user` row is created.
    - Run JIT for alice's SSO identity when a local (`sso_managed=false`) account with her email already exists. Expected: `ACCOUNT_LINK_REQUIRED`, an `auth_event` `login.denied` with reason `account_link_required`, and no new user.
    - As `aip_app` with tenant A set: `UPDATE auth_event SET event_type='x'`. Expected: permission denied.
    - Create users in tenants A and B. `with_tenant(A)` then `list_users`. Expected: only A's users.
    - `GET /api/v1/me` via `httpx.AsyncClient` with `x-test-principal` for a kaefer user. Expected: 200 with `tenant.slug` `kaefer-demo`. `create_app()` with `AIP_ENV=production` and `AUTH_TEST_STUB=1`. Expected: raises `test auth stub forbidden in production`.
    - After creating local user `carol@client.test` in `kaefer-demo`, `identity_resolve_login('email', 'carol@client.test')` returns the `kaefer-demo` tenant id. Registering the same email for `tenant-b` raises `EMAIL_IN_OTHER_TENANT`.
  - **e2e**:
    - Compose stack, Playwright: sign in as `alice@kaefer.test` through the mock IdP (as in IDENTITY-01's e2e). Expected: the callback test response contains a userId. A second sign-in returns the same userId, and the database holds exactly 1 `app_user` for alice.

## Implementation notes (2026-10-09)

Migration revision `202610091851_identity_users` (revises `202610081200`).

- Migration: `app_user`, `tenant_membership` (tenant-table template, FORCE RLS, composite `(user_id, tenant_id)` FKs, FKs to `tenants`), append-only `auth_event` (`aip_app`: SELECT + INSERT only), `login_directory.kind` += `email`, SECURITY DEFINER `identity_register_email` (only for the bound `app.tenant_id` and only for a live local user of that tenant).
- `jit.py`: pure `decide_jit`, `JitProvisioner` and `JitLoginHandler` (default behind the unchanged `ExternalLoginHandler` port). Tenant comes only from the IdP binding (SSO: cookie tenant plus a token email domain claimed by that tenant/IdP) or the local email registration. Fails closed for inactive/deleted tenant, deactivated or soft-deleted user, unverified email, unclaimed domain, no current membership and local/SSO mismatch. Advisory locks plus one retry make concurrent first logins race-safe (mutation-checked).
- `principal.py`: `Principal`, `PrincipalResolver`, `get_principal`; the `x-test-principal` stub needs `AIP_ENV=test` and `AUTH_TEST_STUB=1`, and `create_app()` refuses it outside test.
- `GET /api/v1/me`; `api.py` exports per spec; tenancy `api.py` also exports `load_tenant`, `access_for_status`, `Denial`.
- Not run locally: the real-Keycloak e2e `test_alice_sso_is_provisioned_once_by_jit` (needs Docker/compose).
- Carried forward: `auth_event` ip/user agent at login -> IDENTITY-03; stale `email` directory rows on email change -> IDENTITY-04.

### For the security reviewer

- `identity_register_email` (SECURITY DEFINER) checks tenant context and local user; it leaks only `EMAIL_IN_OTHER_TENANT` to the calling tenant (spec-required 409).
- Local login: the registration tenant is authoritative; a differing cookie tenant is refused (`TENANT_MISMATCH`).
- Denial codes (e.g. `USER_DEACTIVATED` vs `NOT_INVITED`) are shown only after Keycloak authenticated the account.
- Soft-deleted users block re-provisioning by subject or email until restored (deliberate fail-closed).
- `test_me_db.py` points the process engine at the test DB via `DATABASE_URL` and disposes it afterwards.
