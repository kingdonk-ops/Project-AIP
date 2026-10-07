# IDENTITY-05 — SCIM 2.0 server; deprovision revokes everything in one transaction
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07); identity per ADR 0005 rev 2 -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, ARCH-05, IDENTITY-03 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md) (ignore every WorkOS / Directory Sync reference: ADR 0005)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0005](../../docs/adr/0005-identity-architecture.md) rev 2 (in-app SCIM because Keycloak has none; ≤ 60 s target; Keycloak disabled via the admin API), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox, Procrastinate)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) ("SCIM and deprovisioning" section), RFC 7643/7644

## Spec

Serve SCIM 2.0 Users and Groups per tenant from the FastAPI backend (Keycloak has no native SCIM server). Deprovisioning must do two things:

- In one transaction, revoke every app session, device, magic link and API client, emit `user.deactivated`, and refuse the user's next request within 60 s of receipt.
- Through an outbox subscriber, disable the user in Keycloak and revoke their Keycloak sessions via the admin API.

- **files**:
  - apps/api/migrations/versions/<rev>_identity_scim.py
  - apps/api/aip/modules/identity/tables.py
  - apps/api/aip/modules/identity/scim/__init__.py
  - apps/api/aip/modules/identity/scim/routes.py
  - apps/api/aip/modules/identity/scim/auth.py
  - apps/api/aip/modules/identity/scim/tokens.py
  - apps/api/aip/modules/identity/scim/filter.py
  - apps/api/aip/modules/identity/scim/patch.py
  - apps/api/aip/modules/identity/scim/schemas.py
  - apps/api/aip/modules/identity/deprovision.py
  - apps/api/aip/modules/identity/revokers.py
  - apps/api/aip/modules/identity/keycloak_admin.py
  - apps/api/aip/modules/identity/events.py
  - apps/api/aip/modules/identity/api.py
  - apps/api/aip/modules/identity/manifest.toml
  - apps/api/aip/modules/identity/tests/scim/
- **steps**:
  - 1. Alembic revision (raw SQL via `op.execute`, tenant template, FORCE RLS).
    - Table `scim_token`: id, tenant_id, token_hash bytea UNIQUE, label, created_by, created_at, expires_at, revoked_at, last_used_at.
    - Table `scim_group`: id, tenant_id, external_id, display_name, timestamps, deleted_at.
    - Table `scim_group_member`: tenant_id, group_id, user_id, UNIQUE (group_id, user_id).
    - Add `scim_status` (`none`|`active`|`suspended`) to `app_user` (`external_id` already exists).
    - Add SECURITY DEFINER `identity_resolve_scim_token(p_slug citext, p_hash bytea)` (`SET search_path = pg_catalog, public`, `GRANT EXECUTE ... TO aip_app`). It returns tenant_id only when the token belongs to the tenant with that slug and is neither revoked nor expired.
    - Declare the tables in `tables.py`.
  - 2. Token management with `requires('identity.scim.manage')` (privileged; add it to `manifest.toml`) plus IDENTITY-04's `step_up()`.
    - `POST /api/v1/identity/scim/tokens {label}` returns `scim_` + `secrets.token_urlsafe(32)` once, and stores only its SHA-256.
    - A GET lists tokens without their values, and DELETE revokes.
    - At most 2 active tokens per tenant, so tokens can be rotated.
  - 3. Endpoints under `/scim/v2/{tenant_slug}` (an `APIRouter` marked `public()` for the session layer; `scim/auth.py` does the bearer check). They use Content-Type `application/scim+json`, a bearer token, and 600 requests per minute per tenant (`limits` + Redis).
    - Discovery: `ServiceProviderConfig` (patch true, filter true with maxResults 200; bulk, changePassword, sort and etag false), `ResourceTypes`, `Schemas`.
    - `/Users`: GET with filters `userName eq` and `externalId eq` plus `startIndex`/`count`, GET by id, POST (409 `uniqueness` on userName), PUT, PATCH and DELETE.
    - `/Groups`: GET, POST, PATCH (add and remove members) and DELETE.
    - Parsing and validation:
      - Resource bodies are Pydantic v2 models in `scim/schemas.py`. The `scim2-models` package may be used if it passes pyright strict, otherwise hand-written models.
      - `scim/filter.py` is a small hand-written parser for `attr eq "value"` joined by `and` over `userName`, `externalId`, `displayName` and `members.value`. Anything else gives `invalidFilter`.
      - `scim/patch.py` applies `add`/`replace`/`remove` for the supported paths.
    - Entra quirks accepted: case-insensitive `op`, a path-less replace, and `"False"`/`"True"` as strings.
    - Errors use `urn:ietf:params:scim:api:messages:2.0:Error` with `scimType`. Every call writes `auth_event` `scim.<operation>`.
    - SCIM users get `sso_managed=true`, `user_class='staff'`, `status='active'` (IDENTITY-02 JIT links their Keycloak user id by email at first SSO sign-in), and `scim_status='active'`. SCIM never creates a Keycloak user: brokered users appear in Keycloak at first sign-in.
    - Groups are stored only. Mapping groups to roles is a later ACCESS task and must never grant privileged permissions.
  - 4. Revoker registry in `revokers.py`, exported from `api.py`: `register_revoker(name, fn)` where `fn: Callable[[AsyncConnection, UUID, UUID], Awaitable[int]]` takes `(conn, tenant_id, user_id)`. Field devices and magic links (OFFLINE/IDENTITY field-login tasks), portal grants and API clients (IDENTITY-06) register their revokers as those features land. A duplicate name raises at startup.
  - 5. `async def deprovision_user(conn, user_id, *, reason, source: Literal['scim','admin'])` does all of the following on the caller's `with_tenant` connection, in ONE transaction:
    - set the user `deactivated` with `deactivated_at`, and `scim_status='suspended'`;
    - call `revoke_all_for_user` (IDENTITY-03; its Keycloak-session job is enqueued in the same transaction);
    - run every registered revoker;
    - revoke pending or sent invites (IDENTITY-04);
    - write `auth_event` `user.deactivated`;
    - emit the outbox event `user.deactivated` v1 `{user_id, keycloak_user_id, reason, source}` with ARCH-05's `emit`.
    - If any revoker raises, everything rolls back and SCIM returns 500 so the IdP retries. After commit, the session cache keys are purged.
    - SCIM `active=true` sets the user `active`, sets `scim_status='active'` and emits `user.reactivated` v1. It restores no sessions or credentials.
    - Triggers: SCIM `active=false` or DELETE, plus `POST /api/v1/identity/users/{id}/deactivate` (`requires('identity.user.manage')` + `step_up()`).
  - 6. Outbox subscribers in `events.py`, registered with ARCH-07's `@subscriber`, listed under `subscribes` in `manifest.toml`, and idempotent on `event.id`. They use the `keycloak_admin.py` adapter with the `aip-admin` service account:
    - `identity.keycloak_disable` on `user.deactivated` v1: `disable_user` and then `logout_user` (revokes all the user's Keycloak sessions). Keycloak's back-channel logout to IDENTITY-03 is then a harmless no-op.
    - `identity.keycloak_enable` on `user.reactivated` v1: `enable_user`.
    - When `keycloak_user_id` is NULL, look the user up by exact email. An unknown user counts as success.
    - `KeycloakUnavailable` raises, so ARCH-07 retries and dead-letters. App-side access is already gone at commit, so Keycloak lag never re-opens access.
  - 7. Conformance. Commit request/response fixtures for the Microsoft Entra SCIM validator cases as `tests/scim/entra_cases.json` and replay them with a parametrised pytest. Run the Entra validator and the Okta SCIM test suite manually against staging before the Kaefer pilot, and attach the results to the PR.
- **acceptance**:
  - SCIM `PATCH active=false` deactivates the user, revokes their app sessions and writes the `user.deactivated` outbox row in one transaction. The user's next request with their old cookie returns 401 within 60 s of receipt (target ≤ 60 s; expected immediate).
  - After the subscriber runs, the user is disabled in Keycloak and has no Keycloak sessions, so they cannot sign in again even through SSO.
  - A token for one tenant cannot read or write another tenant's `/scim/v2/<slug>`.
  - The Entra fixture suite passes. pyright and ruff pass; no TypeScript under `apps/api`.
- **tests** (pytest; integration uses testcontainers-python Postgres, Redis and Keycloak `quay.io/keycloak/keycloak:26` with IDENTITY-01's realm):
  - **unit**:
    - `parse_filter('userName eq "alice@kaefer.test"')` returns `Filter(attr='userName', op='eq', value='alice@kaefer.test')`. `parse_filter('name.givenName sw "A"')` raises `ScimError(400, scim_type='invalidFilter')`.
    - `apply_patch(user, {'Operations':[{'op':'Replace', 'value':{'active':'False'}}]})` gives `active is False`.
    - `to_scim_user(app_user)` has `schemas == ['urn:ietf:params:scim:schemas:core:2.0:User']`, `meta.resourceType == 'User'`, and a `meta.location` ending in `/Users/<id>`.
    - `register_revoker('api_clients', f)` twice raises `ValueError`.
  - **integration**:
    - `POST /scim/v2/kaefer-demo/Users` with no bearer gives 401 with a SCIM error body. With `tenant-b`'s token, also 401.
    - POST a user, then POST the same userName. Expected: 409 with scimType `uniqueness`.
    - `GET /scim/v2/kaefer-demo/Users?filter=userName eq "alice@kaefer.test"&startIndex=1&count=1`. Expected: totalResults 1 and itemsPerPage 1.
    - Deprovision a user with 2 sessions and 1 fake registered revoker. Expected:
      - both sessions have `revoked_at`, and the revoker ran once;
      - there is exactly 1 `user.deactivated` outbox row and 1 `identity.revoke_keycloak_sessions` job;
      - an `auth_event` row exists.
    - The registered revoker raises. Expected: the user is still active, the sessions still work, the outbox and job queue are empty, and SCIM returns 500.
    - POST a group with 2 members, then PATCH to remove one. Expected: `scim_group_member` count 1.
    - Run `identity.keycloak_disable` for alice (after a headless SSO sign-in created her brokered Keycloak user). Expected: Keycloak reports alice `enabled=false` and `get_sessions` is empty. Running it again succeeds. For an unknown user, the handler succeeds. Then `identity.keycloak_enable` gives `enabled=true`.
    - `POST /api/v1/identity/scim/tokens` without a fresh step-up gives 401 `STEP_UP_REQUIRED`. A third active token gives 409.
  - **e2e**:
    - Playwright on compose: alice is signed in. The test sends SCIM `PATCH active=false` for alice. Expected:
      - Within 60 s (CI asserts ≤ 5 s) the next navigation lands on `/login`, and `GET /api/v1/me` returns 401.
      - After the outbox drains, signing in again through the mock IdP ends on Keycloak's "account is disabled" page or the app's `USER_DEACTIVATED` page, and never yields a session.
