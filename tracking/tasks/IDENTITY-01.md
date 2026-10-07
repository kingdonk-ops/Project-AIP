# IDENTITY-01 — Keycloak dev realm in compose + OIDC broker login + login_directory

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-01, STACK-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md) (ignore every WorkOS reference: ADR 0005)
3. ADRs: [0005](../../docs/adr/0005-identity-architecture.md), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) ("Recommended auth architecture")

## Spec

Run Keycloak as a federation broker defined in code, resolve the tenant before login from a non-RLS `login_directory`, and complete an OIDC authorisation-code + PKCE login that yields a verified external identity without any Keycloak token reaching the browser.

- **files**:
  - infra/keycloak/realm-aip.json
  - infra/keycloak/realm-mock-idp.json
  - db/migrations/<timestamp>_identity_login_directory.sql
  - apps/api/src/modules/identity/manifest.json
  - apps/api/src/modules/identity/oidc/oidc-client.ts
  - apps/api/src/modules/identity/oidc/preauth-cookie.ts
  - apps/api/src/modules/identity/login-directory.repository.ts
  - apps/api/src/modules/identity/login.service.ts
  - apps/api/src/modules/identity/login.controller.ts
  - apps/api/src/modules/identity/seed/dev-login-directory.ts
  - apps/api/src/modules/identity/api.ts
  - apps/api/src/modules/identity/tests/
- **steps**:
  - 1. Realm as code. `realm-aip.json` defines realm `aip`: confidential client `aip-api` with the standard flow only (no implicit, no direct grant), PKCE S256 required, redirect URI `${APP_ORIGIN}/api/v1/auth/oidc/callback`, registration and Keycloak-local password login off, Organizations enabled with org `kaefer` (IdP alias `kaefer-oidc`, domain `kaefer.test`) and org `acme` (`acme-oidc`, `acme.test`), and a mapper that puts the broker alias in the ID token claim `identity_provider`. `realm-mock-idp.json` defines realm `mock-idp`, which stands in for customer IdPs, with users `alice@kaefer.test` and `bob@acme.test` (dev-only passwords live in the realm file). Load both through the STACK-05 compose `keycloak` service with `--import-realm`. The operator realm is out of scope (P1).
  - 2. Migration `login_directory`: id uuid, kind text CHECK in (`email_domain`, `tenant_slug`), key citext, tenant_id uuid FK tenants, idp_alias text NULL, created_at, UNIQUE (kind, key). It is a global pre-tenant table: no RLS, `REVOKE ALL ... FROM aip_app`. Reads go only through `identity_resolve_login(p_kind text, p_key citext) RETURNS TABLE(tenant_id uuid, idp_alias text)`, a SECURITY DEFINER function owned by `aip_owner` with `SET search_path = pg_catalog, public` and `GRANT EXECUTE ... TO aip_app`. Dev seed rows for `kaefer.test` and `acme.test` come from `seed/dev-login-directory.ts`, not from the migration.
  - 3. `POST /api/v1/auth/login/start {email}` (public; 10 requests per minute per IP with rate-limiter-flexible). Take the domain and resolve it. If it maps to an IdP, return 200 `{method:'sso', redirectUrl}`, where the URL is Keycloak's authorize endpoint with `kc_idp_hint=<alias>`, state, nonce and an S256 code challenge. Otherwise return 200 `{method:'password'}`. The response shape is the same whether or not the email or domain exists, and the tenant is never revealed. Store state, nonce, code_verifier, tenant_id and a same-origin `returnTo` in a sealed 10-minute `__Host-aip_preauth` cookie (jose JWE, `dir` + A256GCM, key from `PREAUTH_COOKIE_KEY`).
  - 4. `GET /api/v1/auth/oidc/callback`. Use `openid-client` v6 `authorizationCodeGrant` with the PKCE verifier and state/nonce checks. Verify the ID token's iss, aud, exp and nonce against Keycloak's cached JWKS. Require the `identity_provider` claim to equal the tenant's alias from the pre-auth cookie, otherwise return 403 `IDP_TENANT_MISMATCH`. Build `VerifiedExternalIdentity {tenantId, idpAlias, subject, email, emailVerified, amr[]}`. Then discard the Keycloak tokens: never store them and never send them to the browser.
  - 5. Pass the identity to the `ExternalLoginHandler` port exported from `api.ts`. This task ships a placeholder handler: under `NODE_ENV=test` it returns the identity as JSON; otherwise it returns 501 `PROVISIONING_NOT_IMPLEMENTED`. IDENTITY-02 replaces it with JIT provisioning and IDENTITY-03 with session issue. The tenant is never taken from a Keycloak claim mapper (ADR 0005 supersedes TENANCY-01 step 3).
  - 6. Create `manifest.json` for the identity module (id `identity`, dependsOn `tenancy`). Clear the pre-auth cookie on every callback outcome.
- **acceptance**:
  - `docker compose up` imports both realms and `GET {KEYCLOAK_URL}/realms/aip/.well-known/openid-configuration` returns 200.
  - Signing in as `alice@kaefer.test` reaches the callback and yields a `VerifiedExternalIdentity` for tenant `kaefer`. The browser never receives a Keycloak access, ID or refresh token.
  - `login/start` returns the same status and JSON keys for known and unknown domains.
  - `aip_app` cannot read `login_directory` directly.
- **tests**:
  - **unit**:
    - `domainOf('Alice@Kaefer.TEST')` returns `kaefer.test`. `domainOf('no-at-sign')` throws ValidationError.
    - `buildAuthorizeUrl` output contains `code_challenge_method=S256` and `kc_idp_hint=kaefer-oidc`, and its state is at least 32 bytes of base64url.
    - A callback whose `state` differs from the pre-auth cookie returns 400 `INVALID_STATE`. A tampered pre-auth cookie also returns 400 `INVALID_STATE`.
    - `returnTo` of `//evil.test/x` or `https://evil.test` is replaced by `/`.
  - **integration**:
    - Testcontainers Postgres: as `aip_app`, `SELECT * FROM login_directory` fails with permission denied, and `SELECT * FROM identity_resolve_login('email_domain', 'kaefer.test')` returns 1 row with alias `kaefer-oidc`.
    - `POST /auth/login/start {email:'x@unknown.test'}` returns 200 `{method:'password'}`. `{email:'alice@kaefer.test'}` returns 200 `{method:'sso'}` with a redirectUrl on Keycloak's authorize endpoint.
    - Testcontainers Keycloak (`quay.io/keycloak/keycloak:26`, both realm files): complete the code flow headlessly for `bob@acme.test` while holding a pre-auth cookie for kaefer. Expected: 403 `IDP_TENANT_MISMATCH`.
    - Send 11 `login/start` calls in one minute from one IP. Expected: the 11th returns 429.
  - **e2e**:
    - Compose stack, Playwright: call `login/start` for `alice@kaefer.test`, follow `redirectUrl`, sign in at the mock IdP and land on the callback. Expected: the test handler's JSON shows tenant `kaefer` and email `alice@kaefer.test`, and no response delivered to the browser contains a JWT (no body or cookie matches `eyJ`).
