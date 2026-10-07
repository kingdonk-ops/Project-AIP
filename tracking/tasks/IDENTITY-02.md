# IDENTITY-02 — Users and tenant membership, JIT provisioning, GET /me
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0005](../../docs/adr/0005-identity-architecture.md), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/identity/data-model.md) (tables `app_user`, `tenant_membership`, `auth_event`), [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) (rows 5 and 6 of the gaps table)

## Spec

Keep one `app_user` per person per tenant with tenant membership, provision SSO users just in time at first login (never silently linking local accounts), and expose `GET /api/v1/me` from the FastAPI backend.

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
  - 1. Write the Alembic revision (raw SQL via `op.execute`) from the `db/templates/` tenant-table template: FORCE RLS, `USING` + `WITH CHECK` on `NULLIF(current_setting('app.tenant_id', true), '')::uuid`. Table `app_user`: id, tenant_id, organisation_id NULL, user_class (`staff`|`field`|`portal`), email citext, display_name, idp_alias NULL, idp_subject NULL, external_id NULL, sso_managed bool, password_hash NULL, mfa_required bool default true, status (`invited`|`active`|`deactivated`), deactivated_at, last_login_at, sync_version, created_at, updated_at, deleted_at. Indexes: UNIQUE (tenant_id, email) WHERE deleted_at IS NULL, and UNIQUE (tenant_id, idp_alias, idp_subject) WHERE idp_subject IS NOT NULL. Use `idp_alias`/`idp_subject`, not `workos_*`. Table `tenant_membership`: tenant_id, user_id, organisation_id NULL, membership_type (`member`|`client`|`subcontractor`|`guest`), valid_from, valid_to, timestamps. Table `auth_event` comes from the append-only template: id, tenant_id, user_id NULL, event_type, ip inet, user_agent, detail jsonb, occurred_at, with only INSERT and SELECT granted to `aip_app`. Declare all three as SQLAlchemy Core `Table` objects in `tables.py` so the CI schema-diff check passes. IDs are UUIDv7 generated in the app.
  - 2. In the same revision, extend `login_directory.kind` with `email` and add SECURITY DEFINER `identity_register_email(p_email citext, p_tenant uuid)`, which IDENTITY-04 uses for password login before the tenant is known. `service.py` calls it whenever a user is created or their email changes.
  - 3. JIT provisioning in `jit.py` replaces the IDENTITY-01 placeholder `ExternalLoginHandler`. Keep the decision as a pure function `decide_jit(existing, email_verified, domain_claimed) -> JitDecision`, then apply it inside `async with with_tenant(ctx) as conn:` (from `aip.platform.db`): (a) find by (idp_alias, idp_subject) and refresh email, display_name and last_login_at; (b) otherwise, if `email_verified` and the email domain is claimed by this tenant, find by email: an invited or SSO user gets the subject linked; a local account (sso_managed=false with a password_hash) is refused with `ACCOUNT_LINK_REQUIRED`; (c) otherwise create the user (user_class `staff`, sso_managed=true, status `active`) plus a `member` membership. A deactivated user is refused with `USER_DEACTIVATED`, and login never reactivates. Write `auth_event` `login.succeeded` or `login.denied` with a reason.
  - 4. `principal.py`: the Pydantic v2 model `Principal {kind: Literal['user'], tenant_id: UUID, user_id: UUID, user_class: Literal['staff','field','portal'], session_id: UUID | None, aal: Literal[1, 2], amr: list[str]}` (camelCase JSON aliases) and the `PrincipalResolver` `Protocol`, which IDENTITY-03's session dependency implements. Expose `get_principal` as a FastAPI dependency. Until IDENTITY-03, a test-only resolver reads the `x-test-principal` header, but only when `AIP_ENV=test` and `AUTH_TEST_STUB=1`. The app factory (`create_app()`) raises `RuntimeError('test auth stub forbidden in production')` if `AUTH_TEST_STUB=1` is set with `AIP_ENV=production`.
  - 5. `GET /api/v1/me` (authenticated) returns `{user:{id,email,displayName,userClass,status}, tenant:{id,slug,name}, memberships:[...], aal, amr}` as a Pydantic response model, so it appears in the OpenAPI document for `packages/api-client`. It returns 401 with no principal or a deactivated user.
  - 6. `api.py` exports `get_user`, `list_users(conn, *, q=None, status=None, user_class=None, cursor=None, limit<=100)`, `find_by_email`, `set_user_status`, `record_auth_event` and the `Principal` type. Add permissions `identity.user.read` and `identity.user.manage` (privileged) to `manifest.toml`.
- **acceptance**:
  - The first Keycloak login for `alice@kaefer.test` creates exactly one `app_user` (sso_managed=true, status active) and one `tenant_membership`. A second login creates nothing and updates `last_login_at`.
  - A local password account with the same email is never linked automatically.
  - `aip_app` cannot UPDATE or DELETE `auth_event`.
  - `/me` and `list_users` never return another tenant's data.
- **tests** (pytest; integration uses testcontainers-python Postgres connected as `aip_app`):
  - **unit**:
    - `decide_jit(existing=None, email_verified=True, domain_claimed=True)` returns `create`.
    - `decide_jit(existing=UserRow(sso_managed=False, password_hash='x', status='active'), email_verified=True, domain_claimed=True)` returns `refuse:ACCOUNT_LINK_REQUIRED`.
    - `decide_jit(existing=None, email_verified=False, domain_claimed=True)` returns `refuse:EMAIL_NOT_VERIFIED`.
    - `decide_jit(existing=UserRow(status='deactivated'), ...)` returns `refuse:USER_DEACTIVATED`.
    - `Principal.model_validate({'kind':'user', 'userClass':'admin', ...})` raises `ValidationError` whose error `loc` is `('userClass',)`.
  - **integration**:
    - Run JIT twice for subject `s1`. Expected: 1 `app_user` row, with `last_login_at` updated on the second run.
    - Run JIT for alice when a local password account with her email already exists. Expected: `ACCOUNT_LINK_REQUIRED`, an `auth_event` `login.denied` with reason `account_link_required`, and no new user.
    - As `aip_app` with tenant A set: `UPDATE auth_event SET event_type='x'`. Expected: permission denied.
    - Create users in tenants A and B. `with_tenant(A)` then `list_users`. Expected: only A's users.
    - `GET /api/v1/me` via `httpx.AsyncClient` with `x-test-principal` for a kaefer user. Expected: 200 with `tenant.slug` `kaefer`. `create_app()` with `AIP_ENV=production` and `AUTH_TEST_STUB=1`. Expected: raises `test auth stub forbidden in production`.
    - After creating alice, `identity_resolve_login('email', 'alice@kaefer.test')` returns the kaefer tenant id.
  - **e2e**:
    - Compose stack, Playwright: sign in as `alice@kaefer.test` through the mock IdP (as in IDENTITY-01's e2e). Expected: the callback test response contains a userId. A second sign-in returns the same userId, and the database holds exactly 1 `app_user` for alice.
