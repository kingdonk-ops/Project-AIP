# IDENTITY-02 — Users and tenant membership, JIT provisioning, GET /me

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

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
3. ADRs: [0005](../../docs/adr/0005-identity-architecture.md), [0002](../../docs/adr/0002-data-access-and-migrations.md)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/identity/data-model.md) (tables `app_user`, `tenant_membership`, `auth_event`), [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) (rows 5 and 6 of the gaps table)

## Spec

Keep one `app_user` per person per tenant with tenant membership, provision SSO users just in time at first login (never silently linking local accounts), and expose `GET /api/v1/me`.

- **files**:
  - db/migrations/<timestamp>_identity_users.sql
  - apps/api/src/modules/identity/users.repository.ts
  - apps/api/src/modules/identity/users.service.ts
  - apps/api/src/modules/identity/jit-provisioning.ts
  - apps/api/src/modules/identity/principal.ts
  - apps/api/src/modules/identity/me.controller.ts
  - apps/api/src/modules/identity/schemas.ts
  - apps/api/src/modules/identity/api.ts
  - apps/api/src/modules/identity/manifest.json
  - apps/api/src/modules/identity/tests/
- **steps**:
  - 1. Write the migration from the tenant-table template (FORCE RLS, `USING` + `WITH CHECK` on `app_tenant_id()`). Table `app_user`: id, tenant_id, organisation_id NULL, user_class (`staff`|`field`|`portal`), email citext, display_name, idp_alias NULL, idp_subject NULL, external_id NULL, sso_managed bool, password_hash NULL, mfa_required bool default true, status (`invited`|`active`|`deactivated`), deactivated_at, last_login_at, sync_version, created_at, updated_at, deleted_at. Indexes: UNIQUE (tenant_id, email) WHERE deleted_at IS NULL, and UNIQUE (tenant_id, idp_alias, idp_subject) WHERE idp_subject IS NOT NULL. Use `idp_alias`/`idp_subject`, not `workos_*`. Table `tenant_membership`: tenant_id, user_id, organisation_id NULL, membership_type (`member`|`client`|`subcontractor`|`guest`), valid_from, valid_to, timestamps. Table `auth_event` is append-only: id, tenant_id, user_id NULL, event_type, ip inet, user_agent, detail jsonb, occurred_at, with only INSERT and SELECT granted to `aip_app`.
  - 2. In the same migration, extend `login_directory.kind` with `email` and add SECURITY DEFINER `identity_register_email(p_email citext, p_tenant uuid)`, which IDENTITY-04 uses for password login before the tenant is known. `users.service` calls it whenever a user is created or their email changes.
  - 3. JIT provisioning in `jit-provisioning.ts` replaces the IDENTITY-01 placeholder `ExternalLoginHandler`. Inside `withTenant(identity.tenantId)`: (a) find by (idp_alias, idp_subject) and refresh email, display_name and last_login_at; (b) otherwise, if `emailVerified` and the email domain is claimed by this tenant, find by email: an invited or SSO user gets the subject linked; a local account (sso_managed=false with a password_hash) is refused with `ACCOUNT_LINK_REQUIRED`; (c) otherwise create the user (user_class `staff`, sso_managed=true, status `active`) plus a `member` membership. A deactivated user is refused with `USER_DEACTIVATED`, and login never reactivates. Write `auth_event` `login.succeeded` or `login.denied` with a reason.
  - 4. `principal.ts`: the Zod `Principal` type `{kind:'user', tenantId, userId, userClass, sessionId?, aal: 1|2, amr: string[]}` and the `PrincipalResolver` port, which IDENTITY-03's session guard implements. Until then a test-only resolver reads the `x-test-principal` header, but only when `NODE_ENV=test` and `AUTH_TEST_STUB=1`. Boot throws `test auth stub forbidden in production` if `AUTH_TEST_STUB=1` is set with `NODE_ENV=production`.
  - 5. `GET /api/v1/me` (authenticated) returns `{user:{id,email,displayName,userClass,status}, tenant:{id,slug,name}, memberships:[...], aal, amr}`. It returns 401 with no principal or a deactivated user.
  - 6. `api.ts` exports `getUser`, `listUsers(tx, {q?, status?, userClass?, cursor?, limit<=100})`, `findByEmail`, `setUserStatus`, `recordAuthEvent` and the `Principal` type. Add permissions `identity.user.read` and `identity.user.manage` (privileged) to the manifest.
- **acceptance**:
  - The first Keycloak login for `alice@kaefer.test` creates exactly one `app_user` (sso_managed=true, status active) and one `tenant_membership`. A second login creates nothing and updates `last_login_at`.
  - A local password account with the same email is never linked automatically.
  - `aip_app` cannot UPDATE or DELETE `auth_event`.
  - `/me` and `listUsers` never return another tenant's data.
- **tests**:
  - **unit**:
    - `decideJit({existing:null, emailVerified:true, domainClaimed:true})` returns `create`.
    - `decideJit({existing:{sso_managed:false, password_hash:'x', status:'active'}, emailVerified:true, domainClaimed:true})` returns `refuse:ACCOUNT_LINK_REQUIRED`.
    - `decideJit({existing:null, emailVerified:false, domainClaimed:true})` returns `refuse:EMAIL_NOT_VERIFIED`.
    - `decideJit({existing:{status:'deactivated'}})` returns `refuse:USER_DEACTIVATED`.
    - `Principal.parse({kind:'user', userClass:'admin', ...})` fails at path `['userClass']`.
  - **integration**:
    - Run JIT twice for subject `s1`. Expected: 1 `app_user` row, with `last_login_at` updated on the second run.
    - Run JIT for alice when a local password account with her email already exists. Expected: `ACCOUNT_LINK_REQUIRED`, an `auth_event` `login.denied` with reason `account_link_required`, and no new user.
    - As `aip_app` with tenant A set: `UPDATE auth_event SET event_type='x'`. Expected: permission denied.
    - Create users in tenants A and B. `withTenant(A)` then `listUsers`. Expected: only A's users.
    - `GET /me` with `x-test-principal` for a kaefer user. Expected: 200 with `tenant.slug` `kaefer`. Boot with `NODE_ENV=production` and `AUTH_TEST_STUB=1`. Expected: boot fails with `test auth stub forbidden in production`.
    - After creating alice, `identity_resolve_login('email', 'alice@kaefer.test')` returns the kaefer tenant id.
  - **e2e**:
    - Compose stack: sign in as `alice@kaefer.test` through the mock IdP (as in IDENTITY-01's e2e). Expected: the callback test response contains a userId. A second sign-in returns the same userId, and the database holds exactly 1 `app_user` for alice.
