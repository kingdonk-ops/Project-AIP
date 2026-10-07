# IDENTITY-05 — SCIM 2.0 server; deprovision revokes everything in one transaction

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-05, IDENTITY-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md) (ignore every WorkOS / Directory Sync reference: ADR 0005)
3. ADRs: [0005](../../docs/adr/0005-identity-architecture.md) (in-app SCIM, ≤ 60 s target), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) ("SCIM and deprovisioning" section)

## Spec

Serve SCIM 2.0 Users and Groups per tenant from NestJS, and make deprovisioning revoke every session and credential in one transaction, emit `user.deactivated`, and refuse the user's next request within 60 s of receipt.

- **files**:
  - db/migrations/<timestamp>_identity_scim.sql
  - apps/api/src/modules/identity/scim/scim.controller.ts
  - apps/api/src/modules/identity/scim/scim-auth.guard.ts
  - apps/api/src/modules/identity/scim/scim-tokens.controller.ts
  - apps/api/src/modules/identity/scim/scim-filter.ts
  - apps/api/src/modules/identity/scim/scim-patch.ts
  - apps/api/src/modules/identity/scim/scim.schemas.ts
  - apps/api/src/modules/identity/deprovision/deprovision.service.ts
  - apps/api/src/modules/identity/deprovision/revoker-registry.ts
  - apps/api/src/modules/identity/deprovision/keycloak-logout.subscriber.ts
  - apps/api/src/modules/identity/events.ts
  - apps/api/src/modules/identity/api.ts
  - apps/api/src/modules/identity/tests/scim/
- **steps**:
  - 1. Migration (tenant template, FORCE RLS). Table `scim_token`: id, tenant_id, token_hash bytea UNIQUE, label, created_by, created_at, expires_at, revoked_at, last_used_at. Table `scim_group`: id, tenant_id, external_id, display_name, timestamps, deleted_at. Table `scim_group_member`: tenant_id, group_id, user_id, UNIQUE (group_id, user_id). Add `scim_status` (`none`|`active`|`suspended`) to `app_user` (`external_id` already exists). Add SECURITY DEFINER `identity_resolve_scim_token(p_slug citext, p_hash bytea)`, which returns tenant_id only when the token belongs to the tenant with that slug and is neither revoked nor expired.
  - 2. Token management with `@Requires('identity.scim.manage')` (privileged; add it to the manifest). `POST /api/v1/identity/scim/tokens {label}` returns `scim_<32 random bytes base64url>` once. A GET lists tokens without their values, and DELETE revokes. At most 2 active tokens per tenant, so tokens can be rotated.
  - 3. Endpoints under `/scim/v2/:tenantSlug`, using Content-Type `application/scim+json`, a bearer token, and 600 requests per minute per tenant: `ServiceProviderConfig` (patch true, filter true with maxResults 200, bulk, changePassword, sort and etag false), `ResourceTypes`, `Schemas`. `/Users` supports GET with filters `userName eq` and `externalId eq` plus `startIndex`/`count`, GET by id, POST (409 `uniqueness` on userName), PUT, PATCH and DELETE. `/Groups` supports GET, POST, PATCH (add and remove members) and DELETE. Parse with `scim2-parse-filter`, apply PATCH with `scim-patch`, and validate with Zod. Accept Entra quirks: case-insensitive `op`, a path-less replace, and `"False"`/`"True"` as strings. Errors use `urn:ietf:params:scim:api:messages:2.0:Error` with `scimType`. Every call writes `auth_event` `scim.<operation>`. SCIM users get `sso_managed=true`, `user_class='staff'` and `scim_status='active'`. Groups are stored only: mapping groups to roles is a later ACCESS task and must never grant privileged permissions.
  - 4. Revoker registry in `api.ts`: `registerRevoker(name, (tx, tenantId, userId) => Promise<number>)`. Magic links, devices, portal grants and API clients (IDENTITY-06) register their revokers as those features land.
  - 5. `deprovisionUser(tx, userId, {reason, source:'scim'|'admin'})` does all of the following in ONE transaction: set the user `deactivated` with `deactivated_at`, set `scim_status='suspended'`, call `revokeAllForUser` (IDENTITY-03), run every registered revoker, revoke pending invites, write `auth_event` `user.deactivated`, and emit the outbox event `user.deactivated` v1 `{userId, reason, source}` (ARCH-05). If any revoker throws, everything rolls back and SCIM returns 500 so the IdP retries. After commit, purge the session cache keys. SCIM `active=true` reactivates the user but restores no sessions or credentials. Triggers: SCIM `active=false` or DELETE, plus `POST /api/v1/identity/users/:id/deactivate` (`@Requires('identity.user.manage')`).
  - 6. Outbox subscriber `identity.keycloak-logout` on `user.deactivated`: use `@keycloak/keycloak-admin-client` to log out the user's Keycloak sessions and disable the brokered user in realm `aip`. It is best effort and idempotent: an unknown user counts as success, and retries come from the ARCH-07 dispatcher.
  - 7. Conformance. Commit request/response fixtures for the Microsoft Entra SCIM validator cases as `tests/scim/entra-cases.json` and replay them in Vitest. Run the Entra validator and the Okta SCIM test suite manually against staging before the Kaefer pilot, and attach the results to the PR.
- **acceptance**:
  - SCIM `PATCH active=false` deactivates the user, revokes their sessions and writes the `user.deactivated` outbox row in one transaction. The user's next request with their old cookie returns 401 within 60 s of receipt (target ≤ 60 s; expected immediate).
  - A token for one tenant cannot read or write another tenant's `/scim/v2/<slug>`.
  - The Entra fixture suite passes.
- **tests**:
  - **unit**:
    - `parseFilter('userName eq "alice@kaefer.test"')` returns `{attr:'userName', op:'eq', value:'alice@kaefer.test'}`. `parseFilter('name.givenName sw "A"')` gives a SCIM 400 with scimType `invalidFilter`.
    - `applyPatch(user, {Operations:[{op:'Replace', value:{active:'False'}}]})` gives `active: false`.
    - `toScimUser(appUser)` has `schemas` `['urn:ietf:params:scim:schemas:core:2.0:User']`, `meta.resourceType` `User`, and a `meta.location` ending in `/Users/<id>`.
  - **integration**:
    - `POST /scim/v2/kaefer/Users` with no bearer gives 401 with a SCIM error body. With acme's token, also 401.
    - POST a user, then POST the same userName. Expected: 409 with scimType `uniqueness`.
    - `GET /Users?filter=userName eq "alice@kaefer.test"&startIndex=1&count=1`. Expected: totalResults 1 and itemsPerPage 1.
    - Deprovision a user with 2 sessions and 1 fake registered revoker. Expected: both sessions have `revoked_at`, the revoker ran once, there is exactly 1 `user.deactivated` outbox row, and an `auth_event` row exists.
    - The registered revoker throws. Expected: the user is still active, the sessions still work, the outbox is empty and SCIM returns 500.
    - POST a group with 2 members, then PATCH to remove one. Expected: `scim_group_member` count 1.
    - Run the Keycloak subscriber against Testcontainers Keycloak. Expected: alice is disabled in realm `aip`. For an unknown user, the handler succeeds.
  - **e2e**:
    - Playwright on compose: alice is signed in. The test sends SCIM `PATCH active=false` for alice. Expected: within 60 s (CI asserts ≤ 5 s) the next navigation lands on `/login` and `GET /api/v1/me` returns 401. Signing in again through the mock IdP shows the `USER_DEACTIVATED` page.
