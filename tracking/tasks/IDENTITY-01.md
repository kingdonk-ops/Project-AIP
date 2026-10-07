# IDENTITY-01 — Keycloak dev realm in compose + OIDC broker login + login_directory
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (Python backend, no AIP code), [0005](../../docs/adr/0005-identity-architecture.md), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) ("Recommended auth architecture")

## Spec

Run Keycloak as a federation broker defined in code, resolve the tenant before login from a non-RLS `login_directory`, and complete an OIDC authorisation-code + PKCE login in the FastAPI backend that yields a verified external identity without any Keycloak token reaching the browser.

- **files**:
  - infra/keycloak/realm-aip.json
  - infra/keycloak/realm-mock-idp.json
  - apps/api/migrations/versions/<rev>_identity_login_directory.py
  - apps/api/aip/modules/identity/__init__.py (exports `api` only)
  - apps/api/aip/modules/identity/manifest.toml
  - apps/api/aip/modules/identity/oidc.py
  - apps/api/aip/modules/identity/preauth_cookie.py
  - apps/api/aip/modules/identity/repository.py
  - apps/api/aip/modules/identity/service.py
  - apps/api/aip/modules/identity/schemas.py
  - apps/api/aip/modules/identity/routes.py
  - apps/api/aip/modules/identity/seeds.py
  - apps/api/aip/modules/identity/api.py
  - apps/api/aip/modules/identity/tests/
- **steps**:
  - 1. Realm as code. `realm-aip.json` defines realm `aip`: confidential client `aip-api` with the standard flow only (no implicit, no direct grant), PKCE S256 required, redirect URI `${APP_ORIGIN}/api/v1/auth/oidc/callback`, registration and Keycloak-local password login off, Organizations enabled with org `kaefer` (IdP alias `kaefer-oidc`, domain `kaefer.test`) and org `acme` (`acme-oidc`, `acme.test`), and a mapper that puts the broker alias in the ID token claim `identity_provider`. `realm-mock-idp.json` defines realm `mock-idp`, which stands in for customer IdPs, with users `alice@kaefer.test` and `bob@acme.test` (dev-only passwords live in the realm file). Load both through the STACK-05 compose `keycloak` service with `--import-realm`. The operator realm is out of scope (P1).
  - 2. Alembic revision (forward-only, raw SQL via `op.execute`, run as `aip_owner`) for `login_directory`: id uuid, kind text CHECK in (`email_domain`, `tenant_slug`), key citext, tenant_id uuid FK tenants, idp_alias text NULL, created_at, UNIQUE (kind, key). It is a global pre-tenant table: no RLS, `REVOKE ALL ... FROM aip_app`. Reads go only through `identity_resolve_login(p_kind text, p_key citext) RETURNS TABLE(tenant_id uuid, idp_alias text)`, a SECURITY DEFINER function owned by `aip_owner` with `SET search_path = pg_catalog, public` and `GRANT EXECUTE ... TO aip_app`. Declare the table in `tables.py` only if the schema-diff CI check requires it; the repository calls the function through `text()`. Dev seed rows for `kaefer.test` and `acme.test` come from `seeds.py` (`python -m aip.modules.identity.seeds`), not from the migration.
  - 3. `POST /api/v1/auth/login/start {email}` (public; 10 requests per minute per IP using the `limits` library with Redis storage, moving-window strategy). Take the domain and resolve it. If it maps to an IdP, return 200 `{method:'sso', redirectUrl}`, where the URL is Keycloak's authorize endpoint with `kc_idp_hint=<alias>`, state, nonce and an S256 code challenge (built with `authlib`). Otherwise return 200 `{method:'password'}`. The response shape is the same whether or not the email or domain exists, and the tenant is never revealed. Store state, nonce, code_verifier, tenant_id and a same-origin `returnTo` in a sealed 10-minute `__Host-aip_preauth` cookie (`Secure; HttpOnly; SameSite=Lax; Path=/`), encrypted with `joserfc` JWE (`alg=dir`, `enc=A256GCM`, key from `PREAUTH_COOKIE_KEY`). Request and response bodies are Pydantic v2 models in `schemas.py`.
  - 4. `GET /api/v1/auth/oidc/callback`. Use `authlib`'s async OAuth2 client (`AsyncOAuth2Client.fetch_token`) with the PKCE `code_verifier`, after checking `state` against the pre-auth cookie. Verify the ID token's iss, aud, exp and nonce with `joserfc` against Keycloak's JWKS (cached in-process with a TTL). Require the `identity_provider` claim to equal the tenant's alias from the pre-auth cookie, otherwise return 403 `IDP_TENANT_MISMATCH`. Build the Pydantic model `VerifiedExternalIdentity {tenant_id, idp_alias, subject, email, email_verified, amr: list[str]}`. Then discard the Keycloak tokens: never store them and never send them to the browser.
  - 5. Pass the identity to the `ExternalLoginHandler` `Protocol` exported from `api.py` (resolved through a FastAPI dependency so later tasks can replace it). This task ships a placeholder handler: when `AIP_ENV=test` it returns the identity as JSON; otherwise it returns 501 `PROVISIONING_NOT_IMPLEMENTED`. IDENTITY-02 replaces it with JIT provisioning and IDENTITY-03 with session issue. The tenant is never taken from a Keycloak claim mapper (ADR 0005 supersedes TENANCY-01 step 3).
  - 6. Create `manifest.toml` for the identity module (`id = "identity"`, `depends_on = ["tenancy"]`). Mark both routes as public using the access declaration ARCH-04/ACCESS-01 provide (a no-op marker until ACCESS-01 merges). Clear the pre-auth cookie on every callback outcome.
- **acceptance**:
  - `docker compose up` imports both realms and `GET {KEYCLOAK_URL}/realms/aip/.well-known/openid-configuration` returns 200.
  - Signing in as `alice@kaefer.test` reaches the callback and yields a `VerifiedExternalIdentity` for tenant `kaefer`. The browser never receives a Keycloak access, ID or refresh token.
  - `login/start` returns the same status and JSON keys for known and unknown domains.
  - `aip_app` cannot read `login_directory` directly.
  - No Node/TypeScript code is added under `apps/api`; pyright and ruff pass on the module.
- **tests** (pytest; integration uses testcontainers-python):
  - **unit**:
    - `domain_of('Alice@Kaefer.TEST')` returns `kaefer.test`. `domain_of('no-at-sign')` raises `ValueError` (surfaced by the route as 422).
    - `build_authorize_url(...)` output contains `code_challenge_method=S256` and `kc_idp_hint=kaefer-oidc`, and its state is at least 32 bytes of base64url.
    - A callback whose `state` differs from the pre-auth cookie returns 400 `INVALID_STATE`. A tampered pre-auth cookie (one byte flipped) also returns 400 `INVALID_STATE`.
    - `safe_return_to('//evil.test/x')` and `safe_return_to('https://evil.test')` return `/`; `safe_return_to('/projects?x=1')` returns it unchanged.
  - **integration**:
    - testcontainers `PostgresContainer` with the migrations applied: as `aip_app`, `SELECT * FROM login_directory` fails with permission denied, and `SELECT * FROM identity_resolve_login('email_domain', 'kaefer.test')` returns 1 row with alias `kaefer-oidc`.
    - `httpx.AsyncClient` against the app: `POST /api/v1/auth/login/start {email:'x@unknown.test'}` returns 200 `{method:'password'}`. `{email:'alice@kaefer.test'}` returns 200 `{method:'sso'}` with a `redirectUrl` on Keycloak's authorize endpoint.
    - testcontainers `KeycloakContainer` (`quay.io/keycloak/keycloak:26`, both realm files imported): complete the code flow headlessly (httpx following the login forms) for `bob@acme.test` while holding a pre-auth cookie for kaefer. Expected: 403 `IDP_TENANT_MISMATCH`.
    - Send 11 `login/start` calls in one minute from one IP (testcontainers Redis). Expected: the 11th returns 429.
  - **e2e**:
    - Compose stack, Playwright (`e2e/`, project `web`): call `login/start` for `alice@kaefer.test`, follow `redirectUrl`, sign in at the mock IdP and land on the callback. Expected: the test handler's JSON shows tenant `kaefer` and email `alice@kaefer.test`, and no response delivered to the browser contains a JWT (no body or cookie matches `eyJ`).
