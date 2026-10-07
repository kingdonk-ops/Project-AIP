# IDENTITY-06 — OAuth2 client-credentials API clients (ES256, scoped, expiring)
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07); identity per ADR 0005 rev 2 -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0005](../../docs/adr/0005-identity-architecture.md) rev 2 (API clients are issued by the backend, not Keycloak: OAuth2 client credentials, ES256 JWT, 15 min)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) (API client row of the architecture table)

## Spec

Give integrations OAuth 2.0 client credentials issued by the FastAPI backend. Each client has a hashed, expiring secret and scopes drawn from the permission catalogue. It exchanges them for 15-minute ES256 JWTs, which a bearer dependency verifies against a published JWKS.

- **files**:
  - apps/api/migrations/versions/<rev>_identity_api_clients.py
  - apps/api/aip/modules/identity/tables.py
  - apps/api/aip/modules/identity/api_clients.py
  - apps/api/aip/modules/identity/token_endpoint.py
  - apps/api/aip/modules/identity/jwt_signer.py
  - apps/api/aip/modules/identity/bearer.py
  - apps/api/aip/modules/identity/routes.py
  - apps/api/aip/modules/identity/schemas.py
  - apps/api/aip/modules/identity/api.py
  - apps/api/aip/modules/identity/manifest.toml
  - apps/api/aip/modules/identity/tests/api_clients/
- **steps**:
  - 1. Alembic revision (raw SQL via `op.execute`, tenant template, FORCE RLS).
    - Table `api_client`: id, tenant_id, client_id text UNIQUE (`aipc_` + 16 base32 characters), name, secret_hash text, scopes text[], owner_user_id, created_by, expires_at (default 90 days, maximum 365), last_used_at, revoked_at, created_at.
    - Add SECURITY DEFINER `identity_resolve_client(p_client_id text)` (`SET search_path = pg_catalog, public`, `GRANT EXECUTE ... TO aip_app`). It returns tenant_id, id, secret_hash, scopes, expires_at and revoked_at, because the token endpoint runs before the tenant is known.
    - Declare the table in `tables.py`.
  - 2. Admin API with `requires('identity.api_client.manage')` (privileged; add it to `manifest.toml`), plus IDENTITY-04's `step_up()` on create, rotate and delete when IDENTITY-04 is merged.
    - `POST /api/v1/identity/api-clients {name, scopes[], expiresInDays}` returns 201 `{clientId, clientSecret}`. The secret is `aips_` + `secrets.token_urlsafe(32)` and is shown only once.
    - `GET` lists clients without secrets.
    - `POST /{id}/rotate-secret` issues a new secret, and the old one stops working immediately.
    - `DELETE /{id}` revokes.
    - Scope rules:
      - Each scope must be a catalogue permission (ACCESS-01) that is not privileged and does not match `identity.*`, `access.*`, `*.approve` or `*.sign`; otherwise 400 `SCOPE_NOT_ALLOWED`.
      - The actor must hold every scope they grant.
      - `expiresInDays` is a Pydantic field constrained to 1..365.
    - The secret is hashed with `argon2-cffi` Argon2id (`PasswordHasher` defaults). This is a machine secret, not a staff credential.
  - 3. `POST /oauth/token` (public route):
    - Form-encoded, `grant_type=client_credentials`, authenticated by `client_secret_basic` or `client_secret_post`, with an optional `scope` subset.
    - Returns `{access_token, token_type:'Bearer', expires_in:900, scope}`.
    - Errors follow RFC 6749: `invalid_client` (401), `invalid_scope` (400), `unsupported_grant_type` (400). An unknown client_id runs a dummy Argon2 verify to equalise timing.
    - Rate limit: 30 requests per minute per client_id (`limits` + Redis).
    - `joserfc` signs the JWT with ES256. Claims: `iss` = APP_ORIGIN, `aud` = `aip-api`, `sub` = client_id, `tenant_id`, `scope`, `jti`, `iat`, `exp` = iat + 900. Header: `kid`.
  - 4. Keys come from `API_TOKEN_SIGNING_KEYS` (Secrets Manager in AWS; a pydantic-settings `SecretStr`). It is a JSON array of private JWKs: the first is current and the rest are verify-only during rotation.
    - `GET /.well-known/jwks.json` (public) publishes the public keys only.
    - `create_app()` fails if there is no key or any key is not EC P-256 / ES256.
  - 5. Bearer dependency in `bearer.py`, which implements IDENTITY-02's `PrincipalResolver` for `Authorization: Bearer`:
    - Verify with the algorithm pinned to ES256, and check iss, aud and exp (60 s clock skew).
    - Check that the client is neither revoked nor expired: Redis denylist `aip:client-revoked:<client_id>` first, then `identity_resolve_client` on a miss.
    - Build `ApiClientPrincipal {kind:'api_client', tenant_id, client_id, scopes}`, adding it to the `Principal` union. ACCESS-01's `PolicyService` allows an action only if it is in `scopes`.
    - A request carrying both a session cookie and a bearer token gets 400 `AMBIGUOUS_CREDENTIALS`.
    - Bearer requests are exempt from CSRF (IDENTITY-03).
  - 6. Export `revoke_clients_owned_by(conn, tenant_id, user_id) -> int` from `api.py`. When the IDENTITY-05 registry exists, register it as the `api_clients` revoker; otherwise leave a TODO tied to IDENTITY-05.
- **acceptance**:
  - A client can exchange its credentials for a 15-minute ES256 token that verifies against `/.well-known/jwks.json`.
  - A revoked or expired client is refused on its next request, including with tokens it already holds.
  - Clients can never hold privileged, identity, access, approve or sign scopes.
  - Secrets are stored only as Argon2id hashes.
  - API clients never involve Keycloak. pyright and ruff pass; no TypeScript under `apps/api`.
- **tests** (pytest; integration uses testcontainers-python Postgres and Redis):
  - **unit**:
    - The signed token header is `{'alg':'ES256', 'kid':'k1'}`. An HS256 token signed with the public key as the secret is rejected (algorithm confusion).
    - Scope validation: `['assets.asset.read']` is ok. `['access.role.manage']` and `['inspections.inspection.sign']` give `SCOPE_NOT_ALLOWED`.
    - `expiresInDays: 400` gives a 422 validation error.
    - `create_app()` with `API_TOKEN_SIGNING_KEYS='[]'` raises at startup.
  - **integration**:
    - Create a client and call `POST /oauth/token` with basic auth. Expected: 200, `expires_in` 900, and the JWT verifies with the published JWKS.
    - A wrong secret gives 401 `{error:'invalid_client'}`. The 31st request in a minute gives 429.
    - A token with scope `assets.asset.read`: `GET /api/v1/assets` returns 200 and `POST /api/v1/assets` returns 403. (Before ASSETS routes exist, use the test-only `widgets` module with `widgets.widget.read`.)
    - Revoke the client, then use a token issued before the revocation. Expected: 401.
    - A client with `expires_at` in the past requests a token. Expected: 401 `invalid_client`.
    - A token for `kaefer-demo` requests a `tenant-b` record by id. Expected: 404.
    - `secret_hash` starts with `$argon2id$`, and the plaintext secret is nowhere in `api_client`.
    - A request with both `__Host-aip_sid` and `Authorization: Bearer`. Expected: 400 `AMBIGUOUS_CREDENTIALS`.
  - **e2e**:
    - Playwright APIRequestContext on compose: a signed-in tenant admin (alice) creates a client with scope `projects.project.read`, exchanges it for a token and calls `GET /api/v1/projects`. Expected: 200. Rotate the secret. Expected: the old secret gives 401 `invalid_client` and the new one works.
