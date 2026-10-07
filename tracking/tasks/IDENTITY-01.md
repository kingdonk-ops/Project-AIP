# IDENTITY-01 — Keycloak dev realm in compose + OIDC broker login + login_directory
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07); identity per ADR 0005 rev 2 -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (Python backend, no AIP code), [0005](../../docs/adr/0005-identity-architecture.md) rev 2 (Keycloak handles all staff sign-in; the app issues its own session), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) ("Recommended auth architecture"); Keycloak 26 server-admin docs (authentication flows, ACR/LoA, Organizations, themes)

## Spec

Run Keycloak, defined in code, as the sign-in service for all staff: company SSO (brokered to customer IdPs, discovered by email domain through Keycloak Organizations) and Keycloak-local email + password with mandatory MFA (TOTP or WebAuthn/passkey), password policy, brute-force protection and a custom login theme. Resolve the tenant before login from a non-RLS `login_directory`, and complete the OIDC authorisation-code + PKCE flow in the FastAPI backend so that it yields a verified identity without any Keycloak token reaching the browser.

- **files**:
  - infra/keycloak/realm-aip.json
  - infra/keycloak/realm-mock-idp.json
  - infra/keycloak/password-blocklist.txt
  - infra/keycloak/themes/aip/login/theme.properties
  - infra/keycloak/themes/aip/login/resources/css/aip.css
  - infra/keycloak/themes/aip/login/messages/messages_en.properties (generated)
  - infra/docker-compose.yml (add the `mailpit` service, theme and blocklist mounts on `keycloak`)
  - config/terms/en-AU/auth.json
  - tools/keycloak_messages.py
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
  - 1. Realm, clients and federation as code. `realm-aip.json` defines realm `aip`:
    - Confidential client `aip-api`: standard flow only (implicit and direct-access grants off), PKCE S256 required (`pkce.code.challenge.method=S256`), redirect URIs `${APP_ORIGIN}/api/v1/auth/oidc/callback` and `${APP_ORIGIN}/login`, back-channel logout URL `${APP_ORIGIN}/api/v1/auth/oidc/backchannel-logout` with "session required" on (IDENTITY-03 implements the endpoint), `default.acr.values=aal2` and `minimum.acr.value=aal2`.
    - Confidential client `aip-admin`: service account only, with `realm-management` roles `manage-users`, `view-users` and `query-users`, and nothing else (no `manage-realm`). The backend uses it through `python-keycloak` (IDENTITY-03/04/05).
    - Protocol mappers on `aip-api`: the broker alias in ID-token claim `identity_provider`; the `oidc-amr-mapper` (claim `amr`); `sid` and `auth_time` stay in the ID token.
    - Organizations on: org `kaefer-demo` (domain `kaefer.test`, IdP `kaefer-oidc`) and org `tenant-b` (domain `acme.test`, IdP `acme-oidc`), each IdP linked with "redirect when email domain matches" and hidden on the login page. Both IdPs are OIDC brokers to realm `mock-idp`. `realm-mock-idp.json` defines realm `mock-idp`, standing in for customer IdPs, with users `alice@kaefer.test` and `bob@acme.test` (dev-only passwords live in the realm file).
    - Load both files through the STACK-05 compose `keycloak` service with `--import-realm`. The operator realm is out of scope (P1).
  - 2. Local sign-in policy in `realm-aip.json`:
    - Self-registration off. `verifyEmail` and `resetPasswordAllowed` on. SMTP points at compose `mailpit` (dev) and at `KC_SMTP_*` env placeholders (AWS).
    - Password policy: `length(12) and maxLength(128) and notUsername and notEmail and passwordHistory(5) and passwordBlacklist(password-blocklist.txt) and hashAlgorithm(argon2)`.
    - Brute-force detection on: `failureFactor=5`, `waitIncrementSeconds=60`, `maxFailureWaitSeconds=900`, `maxDeltaTimeSeconds=43200`, no permanent lockout.
    - ACR: realm attribute `acr.loa.map = {"aal1":1,"aal2":2}`.
    - Browser flow `aip-browser`, bound as the realm browser flow, with these alternatives:
      - Cookie.
      - Identity Provider Redirector (honours `kc_idp_hint`).
      - Organization identity-first discovery.
      - Passkey sub-flow: WebAuthn Passwordless, user verification `required`, satisfying LoA 2 with authenticator reference `hwk`.
      - Forms sub-flow: a "Conditional - Level Of Authentication" level-1 step containing Username Password Form (reference `pwd`), then a level-2 step containing the alternatives OTP Form (reference `otp`) and WebAuthn Authenticator (reference `hwk`).
      - Because the client's minimum ACR is `aal2`, every local sign-in needs a second factor. A user with neither factor gets the `CONFIGURE_TOTP` required action at first sign-in.
    - WebAuthn policy: RP ID = the APP_ORIGIN host, ES256 and RS256, user verification `preferred` for 2FA and `required` for passwordless.
    - Required actions enabled: `VERIFY_EMAIL`, `UPDATE_PASSWORD`, `CONFIGURE_TOTP`, `webauthn-register`, `webauthn-register-passwordless`. OTP policy: TOTP, SHA1, 6 digits, 30 s, look-around 1.
    - Brokered (SSO) logins use the default first-broker-login flow with "review profile" off. MFA for brokered users is the customer IdP's job (IDENTITY-04 handles assertion and step-up).
  - 3. Login theme. `loginTheme: aip` (and `accountTheme` stays default). `themes/aip/login/theme.properties` sets `parent=keycloak.v2` and adds `css/aip.css` (colours, font and logo from DESIGN-01 tokens where merged). Labels come from terminology keys where practical: `config/terms/en-AU/auth.json` holds keys such as `auth.login.title`, `auth.login.email`, `auth.login.password`, `auth.login.submit`, `auth.otp.title`, `auth.passkey.signIn`. `tools/keycloak_messages.py` maps each to the Keycloak message key (`loginAccountTitle`, `email`, `password`, `doLogIn`, `loginTotpTitle`, `passkey-login-title`, …) through an explicit table and writes `messages_en.properties`. `--check` exits 1 if the committed file differs (CI runs it). Mount the theme and blocklist read-only into the `keycloak` service.
  - 4. Alembic revision for `login_directory`: forward-only, raw SQL via `op.execute`, run as `aip_owner`.
    - Columns: id uuid, kind text CHECK in (`email_domain`, `tenant_slug`), key citext, tenant_id uuid FK tenants, idp_alias text NULL, created_at, UNIQUE (kind, key).
    - It is a global pre-tenant table: no RLS, `REVOKE ALL ... FROM aip_app`.
    - Reads go only through `identity_resolve_login(p_kind text, p_key citext) RETURNS TABLE(tenant_id uuid, idp_alias text)`, a SECURITY DEFINER function owned by `aip_owner` with `SET search_path = pg_catalog, public` and `GRANT EXECUTE ... TO aip_app`.
    - Declare the table in `tables.py` only if the schema-diff CI check requires it; the repository calls the function through `text()`.
    - Dev seed rows for `kaefer.test` and `acme.test` come from `seeds.py` (`python -m aip.modules.identity.seeds`), not from the migration.
  - 5. `POST /api/v1/auth/login/start {email, returnTo?}` (public; 10 requests per minute per IP using the `limits` library with Redis storage, moving-window strategy).
    - Take the domain and resolve it, then build Keycloak's authorize URL with `authlib`: state, nonce, an S256 code challenge and `login_hint=<email>`.
    - If the domain maps to an IdP, add `kc_idp_hint=<alias>` and return 200 `{method:'sso', redirectUrl}`. Otherwise return 200 `{method:'password', redirectUrl}`, which leads to the themed Keycloak password page.
    - The response has the same status and keys whether or not the email or domain exists, and the tenant is never revealed.
    - Store state, nonce, code_verifier, tenant_id (NULL for an unknown domain), idp_alias (NULL for a non-SSO domain) and a same-origin `returnTo` in a sealed 10-minute `__Host-aip_preauth` cookie (`Secure; HttpOnly; SameSite=Lax; Path=/`). Encrypt it with `joserfc` JWE (`alg=dir`, `enc=A256GCM`, key from `PREAUTH_COOKIE_KEY`).
    - Request and response bodies are Pydantic v2 models in `schemas.py`.
  - 6. `GET /api/v1/auth/oidc/callback`.
    - Check `state` against the pre-auth cookie, then use `authlib`'s `AsyncOAuth2Client.fetch_token` with the PKCE `code_verifier`.
    - Verify the ID token's iss, aud, exp and nonce with `joserfc` against Keycloak's JWKS (cached in-process with a TTL).
    - IdP binding, as the pure function `check_idp_binding(claim_alias, cookie_alias)`: a present `identity_provider` claim must equal the cookie's alias, otherwise 403 `IDP_TENANT_MISMATCH`. An absent claim (a Keycloak-local account) is refused with 403 `SSO_REQUIRED` when the cookie has an alias (an SSO-domain email must not sign in locally).
    - For a local account, also require `acr == 'aal2'`; otherwise 403 `MFA_NOT_SATISFIED` (defence in depth behind the realm flow).
    - Build the Pydantic model `VerifiedExternalIdentity {tenant_id: UUID | None, idp_alias: str | None, subject (Keycloak user id), email, email_verified, acr: str | None, amr: list[str], auth_time: datetime, kc_sid: str | None}`.
    - Then discard the Keycloak tokens: never store them and never send them to the browser.
  - 7. Pass the identity to the `ExternalLoginHandler` `Protocol` exported from `api.py`, resolved through a FastAPI dependency so later tasks can replace it.
    - This task ships a placeholder handler: when `AIP_ENV=test` it returns the identity as JSON; otherwise it returns 501 `PROVISIONING_NOT_IMPLEMENTED`.
    - IDENTITY-02 replaces it with JIT provisioning, including tenant resolution for local accounts when `tenant_id` is NULL. IDENTITY-03 replaces it with session issue.
    - The tenant is never taken from a Keycloak claim mapper (ADR 0005 supersedes TENANCY-01 step 3).
  - 8. Create `manifest.toml` for the identity module (`id = "identity"`, `depends_on = ["tenancy"]`). Mark both routes as public using the access declaration ARCH-04/ACCESS-01 provide (a no-op marker until ACCESS-01 merges). Clear the pre-auth cookie on every callback outcome. The backend adds no password, TOTP or WebAuthn library for staff: no `argon2-cffi`, `pyotp` or `webauthn` import under `aip/modules/identity`.
- **acceptance**:
  - `docker compose up` imports both realms with the `aip` login theme, and `GET {KEYCLOAK_URL}/realms/aip/.well-known/openid-configuration` returns 200.
  - Signing in as `alice@kaefer.test` goes straight to the mock IdP (no Keycloak password page) and yields a `VerifiedExternalIdentity` for tenant `kaefer-demo` with `idp_alias='kaefer-oidc'`.
  - A Keycloak-local user cannot finish sign-in without a second factor. A completed local sign-in yields `acr='aal2'`, with `amr` containing `pwd` and either `otp` or `hwk`.
  - Five wrong passwords lock the local account temporarily (Keycloak brute-force detection).
  - The browser never receives a Keycloak access, ID or refresh token.
  - `login/start` returns the same status and JSON keys for known and unknown domains.
  - `aip_app` cannot read `login_directory` directly.
  - No Node/TypeScript code is added under `apps/api`; pyright and ruff pass on the module. `tools/keycloak_messages.py --check` passes.
- **tests** (pytest; integration uses testcontainers-python; TOTP codes in tests come from a 10-line RFC 6238 helper in `tests/totp.py`, not a backend dependency):
  - **unit**:
    - `domain_of('Alice@Kaefer.TEST')` returns `kaefer.test`. `domain_of('no-at-sign')` raises `ValueError` (surfaced by the route as 422).
    - `build_authorize_url(..., idp_alias='kaefer-oidc')` contains `code_challenge_method=S256`, `kc_idp_hint=kaefer-oidc` and `login_hint=alice%40kaefer.test`, and its state is at least 32 bytes of base64url. With `idp_alias=None`, it contains no `kc_idp_hint`.
    - `check_idp_binding('acme-oidc', 'kaefer-oidc')` raises `IDP_TENANT_MISMATCH`. `check_idp_binding(None, 'kaefer-oidc')` raises `SSO_REQUIRED`. `check_idp_binding(None, None)` and `check_idp_binding('kaefer-oidc', 'kaefer-oidc')` pass.
    - A callback whose `state` differs from the pre-auth cookie returns 400 `INVALID_STATE`. A tampered pre-auth cookie (one byte flipped) also returns 400 `INVALID_STATE`.
    - `safe_return_to('//evil.test/x')` and `safe_return_to('https://evil.test')` return `/`. `safe_return_to('/projects?x=1')` returns it unchanged.
    - Realm lint, loading `realm-aip.json`. Expected:
      - `registrationAllowed` is false.
      - `bruteForceProtected` is true with `failureFactor` 5.
      - `passwordPolicy` contains `length(12)` and `hashAlgorithm(argon2)`.
      - `browserFlow` is `aip-browser`.
      - `loginTheme` is `aip`.
      - Client `aip-api` has `directAccessGrantsEnabled` false, `implicitFlowEnabled` false and attribute `minimum.acr.value` `aal2`.
      - Client `aip-admin` has no `manage-realm` role.
    - `keycloak_messages.render(terms={'auth.login.submit': 'Sign in', ...})` contains the line `doLogIn=Sign in`. A mapped term key missing from `auth.json` raises `KeyError` naming the key.
  - **integration**:
    - testcontainers `PostgresContainer` with the migrations applied: as `aip_app`, `SELECT * FROM login_directory` fails with permission denied, and `SELECT * FROM identity_resolve_login('email_domain', 'kaefer.test')` returns 1 row with alias `kaefer-oidc`.
    - `httpx.AsyncClient` against the app: `POST /api/v1/auth/login/start {email:'x@unknown.test'}` returns 200 `{method:'password', redirectUrl}` with no `kc_idp_hint`. `{email:'alice@kaefer.test'}` returns 200 `{method:'sso', redirectUrl}` with `kc_idp_hint=kaefer-oidc`. Both bodies have the same key set.
    - testcontainers `KeycloakContainer` (`quay.io/keycloak/keycloak:26`, both realm files and the theme imported). Complete the code flow headlessly (httpx following the forms) for `bob@acme.test` while holding a pre-auth cookie for `kaefer-demo`. Expected: 403 `IDP_TENANT_MISMATCH`.
    - Same Keycloak: the fixture creates local user `carol@client.test` through `python-keycloak` with a valid password and `emailVerified=true`. Run a headless login from `login/start {email:'carol@client.test'}`. Expected:
      - After the password form, the next page is the OTP setup page.
      - The test reads the hidden `totpSecret`, submits a computed code and reaches the callback.
      - The identity has `idp_alias=None`, `acr='aal2'`, `amr ⊇ {'pwd','otp'}` and a non-empty `kc_sid`.
    - Same Keycloak: submit 5 wrong passwords for carol. Expected: `GET attack-detection/brute-force/users/{id}` (admin API) reports `disabled: true`, and a 6th attempt with the right password does not reach the callback.
    - `python-keycloak` `set_user_password(carol, 'short')` fails with Keycloak's `invalidPasswordMinLengthMessage`.
    - Send 11 `login/start` calls in one minute from one IP (testcontainers Redis). Expected: the 11th returns 429.
  - **e2e**:
    - Compose stack, Playwright (`e2e/`, project `web`): call `login/start` for `alice@kaefer.test`, follow `redirectUrl`, sign in at the mock IdP and land on the callback. Expected: the test handler's JSON shows tenant `kaefer-demo` and email `alice@kaefer.test`, and no response delivered to the browser contains a JWT (no body or cookie matches `eyJ`).
    - Playwright with a CDP virtual WebAuthn authenticator: carol registers a passkey (Keycloak `webauthn-register` required action), signs out, then signs in with password + security key. Expected: the callback identity has `amr` containing `hwk` and `acr='aal2'`. The Keycloak login page uses the `aip` theme (its stylesheet `aip.css` is loaded) and shows the `auth.login.title` text.
