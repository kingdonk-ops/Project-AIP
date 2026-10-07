# IDENTITY-06 — OAuth2 client-credentials API clients (ES256, scoped, expiring)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | ACCESS-01, IDENTITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md) (its separate "API keys" product is dropped: an API key is just a client secret, shown once)
3. ADRs: [0005](../../docs/adr/0005-identity-architecture.md) (API client row: OAuth2 client credentials, ES256 JWT, 15 min)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) (API client row of the architecture table)

## Spec

Give integrations OAuth 2.0 client credentials. Each client has a hashed, expiring secret and scopes drawn from the permission catalogue, and exchanges them for 15-minute ES256 JWTs verified by a bearer guard against a published JWKS.

- **files**:
  - db/migrations/<timestamp>_identity_api_clients.sql
  - apps/api/src/modules/identity/api-clients/api-clients.service.ts
  - apps/api/src/modules/identity/api-clients/api-clients.controller.ts
  - apps/api/src/modules/identity/api-clients/token.controller.ts
  - apps/api/src/modules/identity/api-clients/jwt-signer.ts
  - apps/api/src/modules/identity/api-clients/bearer.guard.ts
  - apps/api/src/modules/identity/tests/api-clients/
- **steps**:
  - 1. Migration (tenant template, FORCE RLS). Table `api_client`: id, tenant_id, client_id text UNIQUE (`aipc_` + 16 base32 characters), name, secret_hash (Argon2id), scopes text[], owner_user_id, created_by, expires_at (default 90 days, maximum 365), last_used_at, revoked_at, created_at. Add SECURITY DEFINER `identity_resolve_client(p_client_id text)`, which returns tenant_id, id, secret_hash, scopes, expires_at and revoked_at, because the token endpoint runs before the tenant is known.
  - 2. Admin API with `@Requires('identity.api_client.manage')` (privileged; add it to the manifest). `POST /api/v1/identity/api-clients {name, scopes[], expiresInDays}` returns 201 `{clientId, clientSecret}`; the secret (`aips_` + 32 random bytes) is shown only once. `GET` lists clients without secrets. `POST :id/rotate-secret` issues a new secret and the old one stops working immediately. `DELETE :id` revokes. Each scope must be a catalogue permission (ACCESS-01) that is not privileged and does not match `identity.*`, `access.*`, `*.approve` or `*.sign`; otherwise 400 `SCOPE_NOT_ALLOWED`. The actor must hold every scope they grant.
  - 3. `POST /oauth/token`: form-encoded, `grant_type=client_credentials`, `client_secret_basic` or `client_secret_post`, with an optional `scope` subset. It returns `{access_token, token_type:'Bearer', expires_in:900, scope}`. Errors follow RFC 6749: `invalid_client` (401), `invalid_scope` (400), `unsupported_grant_type` (400). Rate limit 30 requests per minute per client_id. The JWT is signed with `jose` ES256 and carries `iss` = APP_ORIGIN, `aud` = `aip-api`, `sub` = client_id, `tenant_id`, `scope`, `jti`, `kid`, `iat`, and `exp` = iat + 900.
  - 4. Keys come from `API_TOKEN_SIGNING_KEYS` (Secrets Manager in AWS): a JSON array of private JWKs where the first is current and the rest are verify-only during rotation. `GET /.well-known/jwks.json` publishes the public keys only. Boot fails if there is no key or any key is not ES256.
  - 5. Bearer guard. Verify `Authorization: Bearer` with the algorithm pinned to ES256 and checks on iss, aud and exp (60 s clock skew). Check the client is not revoked or expired: Redis denylist `aip:client-revoked:<client_id>` first, then the DB function on a miss. Build Principal `{kind:'api_client', tenantId, clientId, scopes}`; ACCESS-01's PolicyService allows an action only if it is in `scopes`. A request carrying both a session cookie and a bearer token gets 400.
  - 6. Export `revokeClientsOwnedBy(tx, userId)` from `api.ts`, and register it as the `api_clients` revoker in IDENTITY-05's registry when that registry exists.
- **acceptance**:
  - A client can exchange its credentials for a 15-minute ES256 token that verifies against `/.well-known/jwks.json`.
  - A revoked or expired client is refused on its next request, including with tokens it already holds.
  - Clients can never hold privileged, identity, access, approve or sign scopes.
  - Secrets are stored only as Argon2id hashes.
- **tests**:
  - **unit**:
    - The signed token header is `{alg:'ES256', kid:'k1'}`. An HS256 token signed with the public key as the secret is rejected (algorithm confusion).
    - Scope validation: `['assets.asset.read']` is ok. `['access.role.manage']` and `['inspections.inspection.sign']` give `SCOPE_NOT_ALLOWED`.
    - `expiresInDays: 400` gives a 400 validation error.
  - **integration**:
    - Create a client and call `POST /oauth/token` with basic auth. Expected: 200, `expires_in` 900, and the JWT verifies with the published JWKS.
    - A wrong secret gives 401 `{error:'invalid_client'}`. The 31st request in a minute gives 429.
    - A token with scope `assets.asset.read`: `GET /api/v1/assets` returns 200 and `POST /api/v1/assets` returns 403.
    - Revoke the client, then use a token issued before the revocation. Expected: 401.
    - A client with `expires_at` in the past requests a token. Expected: 401 `invalid_client`.
    - A token for tenant A requests a tenant B record by id. Expected: 404.
    - `secret_hash` starts with `$argon2id$` and the plaintext secret is nowhere in `api_client`.
  - **e2e**:
    - Playwright APIRequestContext on compose: a signed-in tenant admin creates a client with scope `projects.project.read`, exchanges it for a token and calls `GET /api/v1/projects`. Expected: 200. Rotate the secret. Expected: the old secret gives 401 `invalid_client` and the new one works.
