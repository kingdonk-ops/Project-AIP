# IDENTITY-03 — Server-side sessions (__Host- cookie, user_session), rotation, revocation

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

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
3. ADRs: [0005](../../docs/adr/0005-identity-architecture.md), [0002](../../docs/adr/0002-data-access-and-migrations.md)
4. Only if the step needs it: [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) ("Session store" paragraph and the timeouts column)

## Spec

Issue every browser session as an opaque `__Host-` cookie backed by a `user_session` row (Postgres is the truth, with a Redis cache of at most 60 s), with idle and absolute timeouts, rotation on login and elevation, CSRF protection and immediate revocation.

- **files**:
  - db/migrations/<timestamp>_identity_sessions.sql
  - apps/api/src/modules/identity/sessions/session.service.ts
  - apps/api/src/modules/identity/sessions/session.store.ts
  - apps/api/src/modules/identity/sessions/session.guard.ts
  - apps/api/src/modules/identity/sessions/csrf.ts
  - apps/api/src/modules/identity/sessions/sessions.controller.ts
  - apps/api/src/modules/identity/api.ts
  - apps/web/src/features/identity/ActiveSessionsPage.tsx
  - apps/web/src/features/identity/api-fetch.ts
  - apps/api/src/modules/identity/tests/sessions/
- **steps**:
  - 1. Migration (tenant template, FORCE RLS). Table `user_session`: id, tenant_id, user_id, sid_hash bytea UNIQUE (SHA-256 of the cookie value), audience (`app`|`portal`|`device`), device_id NULL, aal smallint, amr text[], ip inet, user_agent, created_at, last_seen_at, idle_expires_at, absolute_expires_at, revoked_at, revoke_reason. Table `tenant_auth_policy`: tenant_id PK; session_policy jsonb defaulting to `{staff:{idleMin:30,absoluteH:12}, field:{idleMin:5,absoluteH:12}, portal:{idleMin:15,absoluteH:8}}`; sso_enforced bool; local_mfa_required bool default true. This is the single owner of session and MFA policy; SECURITY-07 keeps only the IP allow-list. Add SECURITY DEFINER `identity_resolve_session(p_sid_hash bytea)`, which returns tenant_id, user_id, session_id, aal, amr, audience and the expiry fields only for rows that are not revoked and not expired. Session lookup happens before the tenant is known.
  - 2. `issueSession(tx, principal, {aal, amr, audience})`: generate `randomBytes(32)` base64url and store only its SHA-256. Set `__Host-aip_sid` (Secure, HttpOnly, SameSite=Lax, Path=/, no Domain) and `__Host-aip_csrf` (Secure, readable by JS, random). Every login issues a new sid and revokes any sid presented with the login request (reason `rotated`, preventing fixation). `rotateSession` is exported for MFA elevation (IDENTITY-04) and privilege changes.
  - 3. Global session guard, which runs before the access guard. Read the cookie, try the Redis cache `aip:sess:<sid_hash hex>` (TTL = min(60 s, time left)), and fall back to the DB function. A revoked or expired session gets 401 `SESSION_EXPIRED` and the cookie is cleared. Then check that the user is active and the tenant is active, fill the ARCH-04 request context and Principal, and run the handler inside `withTenant`. Update `last_seen_at` at most once per 60 s, slide `idle_expires_at`, and never extend `absolute_expires_at`. Delete IDENTITY-02's test resolver from non-test wiring.
  - 4. CSRF in `csrf.ts`. For POST, PUT, PATCH and DELETE, require `Origin` to equal `APP_ORIGIN` and the `X-CSRF-Token` header to equal the `__Host-aip_csrf` cookie, otherwise 403 `CSRF_FAILED`. The public flow-starting endpoints (`/auth/login/start`, `/auth/password`) are checked for Origin only. Bearer-token requests (IDENTITY-06) are exempt.
  - 5. Revocation. `revokeSession(tx, id, reason)` and `revokeAllForUser(tx, userId, reason)` update rows inside the caller's transaction and delete the cache keys in an after-commit hook. Both are exported from `api.ts` for IDENTITY-05. Endpoints: `POST /api/v1/auth/logout` revokes the current session, clears both cookies and returns `{redirectUrl}` to Keycloak's end-session endpoint for SSO users; `GET /api/v1/me/sessions` lists the user's sessions and flags the current one; `DELETE /api/v1/me/sessions/:id` revokes one of the user's own sessions.
  - 6. Wire the OIDC callback. The `ExternalLoginHandler` now runs JIT (IDENTITY-02) and then `issueSession` with `aal=2` if `amr` contains `mfa`, `otp` or `hwk`, else `aal=1`, and redirects to the validated same-origin `returnTo`.
  - 7. Web. `api-fetch.ts` sends `X-CSRF-Token` from the cookie and, on 401 `SESSION_EXPIRED`, redirects to `/login?returnTo=<path>`. `/settings/profile/sessions` lists active sessions (device, IP, last seen) with a "Sign out" action per row. The Next.js `/api/*` same-origin proxy comes from DESIGN-02; add it if it is missing.
- **acceptance**:
  - No JWT and no Keycloak token reaches the browser. The only auth cookies are `__Host-aip_sid` and `__Host-aip_csrf`.
  - A revoked session is refused on the next request. If the cache purge fails, it is refused within 60 s at worst.
  - Staff sessions end after 30 minutes idle or 12 hours absolute, whichever comes first.
  - The database stores only the SHA-256 of each sid.
- **tests**:
  - **unit**:
    - The serialised session cookie contains `__Host-aip_sid=`, `Secure`, `HttpOnly`, `SameSite=Lax` and `Path=/`, and does not contain `Domain`.
    - `computeExpiry(now=10:00, staff)` gives idle 10:30 and absolute 22:00. A touch at 10:20 gives idle 10:50. A touch at 21:50 gives idle 22:00 (capped by absolute).
    - CSRF: POST with a matching token and Origin passes. POST without the header fails with `CSRF_FAILED`. POST with `Origin: https://evil.test` fails with `CSRF_FAILED`. GET without a token passes.
  - **integration**:
    - Testcontainers Postgres + Redis: issue a session. Expected: `sid_hash` equals SHA-256 of the cookie value, and the raw cookie value appears nowhere in `user_session`.
    - Log in again while presenting the old cookie. Expected: the old row has `revoked_at` set with reason `rotated`.
    - Call `revokeAllForUser` in a transaction and roll back. Expected: the sessions still work. Commit instead. Expected: the next `GET /me` returns 401 `SESSION_EXPIRED` and the Redis key is gone.
    - Fake clock: last activity 31 minutes ago. Expected: 401. Continuous activity for 12 h 1 min. Expected: 401.
    - Set the user's status to `deactivated` directly in the DB with the cache TTL forced to 1 s. Expected: 401 after 1 s.
    - Send 50 parallel `GET /me` requests with sessions for tenants A and B. Expected: each response echoes its own tenant.
  - **e2e**:
    - Playwright on compose: sign in as alice through the shell login and reload. Expected: still signed in. Sign in from a second browser context. In the first context's Active sessions page, click "Sign out" on the other session. Expected: the second context's next navigation lands on `/login`.
    - Click Logout. Expected: `GET /api/v1/me` returns 401 and both cookies are cleared.
