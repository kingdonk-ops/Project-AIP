# IDENTITY-03 — Server-side sessions (__Host- cookie, user_session), rotation, revocation
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07); identity per ADR 0005 rev 2 -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-02, IDENTITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md) (its "15-minute access tokens + 30-day refresh" line is superseded: browsers hold no JWTs, per ADR 0005)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0005](../../docs/adr/0005-identity-architecture.md) rev 2 (Keycloak signs staff in; the app issues the session), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Procrastinate, atomic enqueue), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) ("Session store" paragraph and the timeouts column)

## Spec

After Keycloak signs a staff user in, the FastAPI backend issues every browser session itself, as an opaque `__Host-` cookie backed by a `user_session` row. Postgres is the truth, with a Redis cache of at most 60 s. Sessions have idle and absolute timeouts, rotate on login and elevation, are protected against CSRF, and can be revoked immediately. Revoking an app session also revokes the matching Keycloak SSO session through the admin API, and a Keycloak back-channel logout revokes the app session.

- **files**:
  - apps/api/migrations/versions/<rev>_identity_sessions.py
  - apps/api/aip/modules/identity/tables.py
  - apps/api/aip/modules/identity/sessions.py
  - apps/api/aip/modules/identity/session_store.py
  - apps/api/aip/modules/identity/dependencies.py
  - apps/api/aip/modules/identity/csrf.py
  - apps/api/aip/modules/identity/keycloak_admin.py
  - apps/api/aip/modules/identity/jobs.py
  - apps/api/aip/modules/identity/routes.py
  - apps/api/aip/modules/identity/schemas.py
  - apps/api/aip/modules/identity/api.py
  - apps/api/aip/modules/identity/tests/
  - apps/web/src/routes/_app/settings/profile/sessions.tsx
  - apps/web/src/features/identity/ActiveSessionsPage.tsx
  - apps/web/src/features/identity/csrf-fetch.ts
  - config/terms/en-AU/identity.json
- **steps**:
  - 1. Alembic revision (raw SQL via `op.execute`, tenant template, FORCE RLS).
    - Table `user_session`: id, tenant_id, user_id, sid_hash bytea UNIQUE (SHA-256 of the cookie value), audience (`app`|`portal`|`device`), device_id NULL, aal smallint, amr text[], authenticated_at timestamptz (the ID token `auth_time`), kc_sid text NULL (the Keycloak session id from the ID token `sid`), ip inet, user_agent, created_at, last_seen_at, idle_expires_at, absolute_expires_at, revoked_at, revoke_reason. Index `(kc_sid) WHERE revoked_at IS NULL`.
    - Table `tenant_auth_policy`: tenant_id PK; session_policy jsonb defaulting to `{staff:{idleMin:30,absoluteH:12}, field:{idleMin:5,absoluteH:12}, portal:{idleMin:15,absoluteH:8}}`; sso_enforced bool default false; step_up_max_age_min int default 10. This is the single owner of session policy; SECURITY-07 keeps only the IP allow-list. MFA itself is enforced by the Keycloak realm flow (IDENTITY-01), so there is no MFA flag here.
    - SECURITY DEFINER functions, each with `SET search_path = pg_catalog, public` and `GRANT EXECUTE ... TO aip_app`. Both are needed because their lookups run before the tenant is known.
      - `identity_resolve_session(p_sid_hash bytea)` returns tenant_id, user_id, session_id, aal, amr, authenticated_at, audience and the expiry fields, only for rows that are neither revoked nor expired.
      - `identity_sessions_by_kc_sid(p_kc_sid text)` returns (tenant_id, session_id) for the back-channel logout.
    - Declare the tables as SQLAlchemy Core `Table` objects in `tables.py`.
  - 2. `async def issue_session(conn, principal, *, aal, amr, authenticated_at, kc_sid, audience='app') -> IssuedSession` in `sessions.py`.
    - Generate `secrets.token_bytes(32)` as base64url and store only its SHA-256.
    - Set `__Host-aip_sid` (Secure, HttpOnly, SameSite=Lax, Path=/, no Domain) and `__Host-aip_csrf` (Secure, readable by JS, random).
    - Every login issues a new sid and revokes any sid presented with the login request (reason `rotated`, preventing fixation).
    - `rotate_session(conn, session_id, *, aal, amr, authenticated_at)` is exported from `api.py` for step-up (IDENTITY-04) and privilege changes. It issues a new sid and revokes the old one with reason `rotated`.
    - `compute_expiry(now, policy)` and `touch(now, session, policy)` are pure functions.
  - 3. Session dependency in `dependencies.py`, which implements IDENTITY-02's `PrincipalResolver` and runs before ACCESS-01's `requires()`.
    - Read the cookie and try the Redis cache `aip:sess:<sid_hash hex>` (TTL = min(60 s, time left)). On a miss, fall back to `identity_resolve_session`.
    - A revoked or expired session gets 401 `SESSION_EXPIRED`, and both cookies are cleared.
    - Then check that the user and the tenant are active, fill the ARCH-04 request context and `Principal` (aal, amr), and run the handler inside `async with with_tenant(ctx) as conn:`.
    - Update `last_seen_at` at most once per 60 s, slide `idle_expires_at`, and never extend `absolute_expires_at`.
    - Remove IDENTITY-02's `x-test-principal` resolver from non-test wiring. It stays only under `AIP_ENV=test` with `AUTH_TEST_STUB=1`.
  - 4. CSRF in `csrf.py`. For POST, PUT, PATCH and DELETE, require `Origin` to equal `APP_ORIGIN` and the `X-CSRF-Token` header to equal the `__Host-aip_csrf` cookie (compared with `hmac.compare_digest`), otherwise 403 `CSRF_FAILED`. Exemptions:
    - `POST /api/v1/auth/login/start` is checked for Origin only.
    - `POST /api/v1/auth/oidc/backchannel-logout` is exempt because it is server-to-server and authenticated by the logout token.
    - Bearer-token requests (IDENTITY-06) are exempt.
  - 5. Keycloak admin adapter in `keycloak_admin.py`, implementing the STACK-02 `IdentityProvider` protocol.
    - It uses `python-keycloak` `KeycloakAdmin` with the `aip-admin` service-account client from IDENTITY-01, with the secret in `KEYCLOAK_ADMIN_CLIENT_SECRET` (`SecretStr`).
    - This task needs `revoke_kc_session(kc_sid)` (admin REST `DELETE /admin/realms/aip/sessions/{kc_sid}`, via the client's raw connection if there is no helper) and `logout_user(keycloak_user_id)` (`user_logout`).
    - Both are idempotent: a 404 counts as success.
    - IDENTITY-04 and IDENTITY-05 add more methods.
  - 6. Revocation.
    - `revoke_session(conn, session_id, reason)` and `revoke_all_for_user(conn, user_id, reason)` update rows inside the caller's transaction, delete the cache keys in an after-commit hook, and atomically enqueue the Procrastinate job `identity.revoke_keycloak_sessions` (queue `default`, payload `{tenant_id, kc_sids:[...]}`) in the same transaction (ADR 0003). The job calls `revoke_kc_session` for each sid and retries with backoff. Both functions are exported from `api.py` for IDENTITY-05.
    - `POST /api/v1/auth/logout` revokes the current session, clears both cookies and returns 204. The Keycloak SSO session is ended by the job, so there is no browser redirect through Keycloak's end-session endpoint.
    - `GET /api/v1/me/sessions` lists the user's sessions and flags the current one.
    - `DELETE /api/v1/me/sessions/{id}` revokes one of the user's own sessions; another user's id gives 404.
  - 7. Back-channel logout from Keycloak: `POST /api/v1/auth/oidc/backchannel-logout`, form field `logout_token` (public route, no cookie).
    - Verify the token with `joserfc` against Keycloak's JWKS: iss, aud `aip-api`, iat within 5 minutes, the `events` claim containing `http://schemas.openid.net/event/backchannel-logout`, no `nonce`, and a `sid`. Any failure returns 400.
    - Revoke every app session from `identity_sessions_by_kc_sid(sid)` with reason `keycloak_logout`, without enqueuing a Keycloak revocation.
    - Return 200 even when no session matches (idempotent).
  - 8. Wire the OIDC callback. The `ExternalLoginHandler` now runs JIT (IDENTITY-02), then `issue_session` with `aal=derive_aal(identity.acr, identity.amr)` (2 if `acr == 'aal2'` or `amr` contains `otp`, `hwk` or `mfa`, otherwise 1), `amr`, `authenticated_at=identity.auth_time` and `kc_sid=identity.kc_sid`. It then redirects (303) to the validated same-origin `returnTo`.
  - 9. Web.
    - `csrf-fetch.ts` is the fetch wrapper the generated `packages/api-client` uses: it sends `X-CSRF-Token` from the cookie, and on 401 `SESSION_EXPIRED` it hands over to DESIGN-02's redirect to `/login?next=<path>`.
    - The TanStack Router route `/settings/profile/sessions` lists active sessions (device, IP, last seen) with a "Sign out" action per row. Labels are terminology keys in `identity.json`.
    - Same-origin `/api` routing comes from DESIGN-02's Vite proxy (CloudFront in AWS). There is no Next.js and no BFF.
- **acceptance**:
  - No JWT and no Keycloak token reaches the browser. The only auth cookies are `__Host-aip_sid` and `__Host-aip_csrf`.
  - A revoked session is refused on the next request. If the cache purge fails, it is refused within 60 s at worst.
  - Logout revokes the app session at once and ends the Keycloak SSO session, so the next sign-in asks for credentials again.
  - A Keycloak back-channel logout revokes the matching app sessions.
  - Staff sessions end after 30 minutes idle or 12 hours absolute, whichever comes first.
  - The database stores only the SHA-256 of each sid.
  - pyright and ruff pass. No TypeScript is added under `apps/api`.
- **tests** (pytest; integration uses testcontainers-python Postgres, Redis and Keycloak; frontend uses Vitest):
  - **unit**:
    - The serialised session cookie contains `__Host-aip_sid=`, `Secure`, `HttpOnly`, `SameSite=Lax` and `Path=/`, and does not contain `Domain`.
    - `compute_expiry(now=10:00, staff policy)` gives idle 10:30 and absolute 22:00. A touch at 10:20 gives idle 10:50. A touch at 21:50 gives idle 22:00 (capped by absolute).
    - `derive_aal('aal2', ['pwd','otp'])` returns 2. `derive_aal(None, ['pwd'])` returns 1. `derive_aal(None, ['hwk'])` returns 2.
    - CSRF: POST with a matching token and Origin passes. POST without the header fails with `CSRF_FAILED`. POST with `Origin: https://evil.test` fails with `CSRF_FAILED`. GET without a token passes.
    - Back-channel logout token checks: a token without the `events` claim, or one carrying a `nonce`, is rejected with 400.
  - **integration**:
    - Issue a session. Expected: `sid_hash` equals SHA-256 of the cookie value, and the raw cookie value appears nowhere in `user_session`.
    - Log in again while presenting the old cookie. Expected: the old row has `revoked_at` set with reason `rotated`.
    - Call `revoke_all_for_user` in a transaction and roll back. Expected: the sessions still work and no `identity.revoke_keycloak_sessions` job exists. Commit instead. Expected: the next `GET /api/v1/me` returns 401 `SESSION_EXPIRED`, the Redis key is gone, and exactly 1 job is queued (Procrastinate `InMemoryConnector` or the Postgres connector).
    - Testcontainers Keycloak: sign carol in headlessly (as in IDENTITY-01), then `POST /api/v1/auth/logout` and run the queued job. Expected: Keycloak's admin API `get_sessions(carol)` returns an empty list. Running the job a second time succeeds (404 treated as success).
    - Keycloak admin API `user_logout(carol)` while she holds an app session. Expected: Keycloak calls the back-channel endpoint, and her next `GET /api/v1/me` returns 401.
    - Fake clock: last activity 31 minutes ago. Expected: 401. Continuous activity for 12 h 1 min. Expected: 401.
    - Set the user's status to `deactivated` directly in the DB with the cache TTL forced to 1 s. Expected: 401 after 1 s.
    - Send 50 parallel `GET /api/v1/me` requests via `httpx.AsyncClient` with sessions for `kaefer-demo` and `tenant-b`. Expected: each response echoes its own tenant.
  - **e2e**:
    - Playwright on compose: sign in as alice through the shell login and reload. Expected: still signed in. Sign in from a second browser context. In the first context's Active sessions page, click "Sign out" on the other session. Expected: the second context's next navigation lands on `/login`.
    - Click Logout. Expected: `GET /api/v1/me` returns 401 and both cookies are cleared. Start sign-in again as carol. Expected: Keycloak shows the password form rather than signing her in silently.

## Carried forward from IDENTITY-01 (non-blocking)

- `jwcrypto` (LGPL-3.0) arrives transitively through `python-keycloak`, used for the admin/seed client; our own token checks use `joserfc` (BSD). LGPL is allowed as an unmodified, imported library (ADR 0011), but record it in the licence notes, or drop `python-keycloak` for plain admin REST calls when this task touches the admin client.
