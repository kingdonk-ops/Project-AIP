# PORTAL-02 — Portal sign-in and session on its own host: aip-portal client, separate cookie and idle timeout, route allow-list

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | IDENTITY-10, PORTAL-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`PORTAL-01.md`](PORTAL-01.md) (portal users, grants, `PortalGrantProvider`, `AccessPrincipal.external`)
3. [`docs/blueprint/modules/portal/advice-security.md`](../../docs/blueprint/modules/portal/advice-security.md)
4. ADRs: [0036](../../docs/adr/0036-r1-module-decisions.md) (choice 7), [0026](../../docs/adr/0026-web-delivery-behind-the-alb.md)
   §3 (own host name), [0005](../../docs/adr/0005-identity-architecture.md) (Keycloak holds passwords and second
   factors), [0010](../../docs/adr/0010-signoff-assurance.md) (addendum part 2: clients sign in with username,
   password and the second step), [0034](../../docs/adr/0034-invites-and-step-up-implementation.md)
5. Code: `apps/api/aip/modules/identity/api.py` (sessions, `Principal`, `revoke_session`, `record_auth_event`),
   `apps/api/aip/platform/access/dependencies.py` and `route_check.py`, `infra/keycloak/realm-aip.json` (the
   `aip-api` client, the model for `aip-portal`), `infra/docker-compose.yml`

## Spec

Let an invited client sign in on the portal's own host through a dedicated `aip-portal` Keycloak client with
password and second factor, holding a portal session (its own cookie, a shorter idle timeout) that can reach only
the portal-facing API routes, with rate limits on those routes (tag: extend).

Identity owns the OIDC flow, the session store and the cookies. This task needs IDENTITY-10 ("portal audience", a dependency of this row)
to have added, through `aip.modules.identity.api`:
the public routes `POST /api/v1/auth/portal/login/start` and `GET /api/v1/auth/portal/oidc/callback` (the
`aip-portal` client, `PORTAL_ORIGIN` redirect URI, `issue_session(..., audience="portal")`, only `user_class =
'portal'` local accounts, `aal = 2` required); audience-specific cookies `__Host-aip_portal_sid` /
`__Host-aip_portal_csrf`; `Principal.audience`; `clear_session_cookies(response, audience=...)`; a session whose
audience does not match the cookie it came in is refused; and the staff callback refusing `user_class = 'portal'`.
This task does not edit identity files. If that row has not merged, stop and report.

Out of scope: the portal web app (PORTAL-03), sign-off actions and their step-up (PORTAL-04), magic links and PINs
(not R1), per-tenant portal on/off and `portal_settings` (not R1; the tenant's `tenant_auth_policy` already holds
the `portal` session policy).

- **files**:
  - infra/keycloak/realm-aip.json
  - infra/docker-compose.yml
  - infra/coolify/docker-compose.coolify.yml
  - infra/coolify/env.example
  - apps/api/aip/platform/access/dependencies.py
  - apps/api/aip/platform/access/route_check.py
  - apps/api/aip/platform/access/tests/test_external_routes.py
  - apps/api/aip/modules/portal/manifest.toml
  - apps/api/aip/modules/portal/routes.py
  - apps/api/aip/modules/portal/schemas.py
  - apps/api/aip/modules/portal/service.py
  - apps/api/aip/modules/portal/rate_limit.py
  - apps/api/aip/modules/portal/api.py
  - apps/api/aip/modules/portal/tests/test_rate_limit.py
  - apps/api/aip/modules/portal/tests/test_portal_session_db.py
  - apps/api/aip/main.py
  - config/terms/en-AU/portal.json
  - packages/api-client/openapi.json
  - tools/tests/test_compose.py
  - e2e/web/portal-auth.spec.ts
  - e2e/playwright.config.ts
- **steps**:
  - 1. Realm config as code (`infra/keycloak/realm-aip.json`), a new client `aip-portal` copied from `aip-api`:
    confidential, `clientAuthenticatorType: client-secret` with secret `${PORTAL_OIDC_CLIENT_SECRET:...dev-only...}`
    (the dev value obviously fake, refused outside dev/test by SECURITY-14's check), standard flow only (no implicit,
    no direct access grants, no service account), `rootUrl` / `baseUrl` `${PORTAL_ORIGIN:http://portal.localhost:8081}`,
    `redirectUris` exactly `["${PORTAL_ORIGIN:http://portal.localhost:8081}/api/v1/auth/portal/oidc/callback"]`,
    `webOrigins: []`, attributes `pkce.code.challenge.method: S256`, `default.acr.values: aal2`,
    `minimum.acr.value: aal2` (every portal sign-in takes the second factor), `backchannel.logout.url`
    `${PORTAL_ORIGIN:...}/api/v1/auth/oidc/backchannel-logout`, `post.logout.redirect.uris`
    `${PORTAL_ORIGIN:...}/signin`, `use.refresh.tokens: false`, the same `acr`/`amr` mappers, and no
    `identity_provider` mapper (portal users are local accounts: no IdP broker for this client, enforced by identity).
    Pass `PORTAL_ORIGIN` and `PORTAL_OIDC_CLIENT_SECRET` to the `keycloak` and API services in
    `infra/docker-compose.yml` (dev `PORTAL_ORIGIN=http://portal.localhost:8081`) and in
    `infra/coolify/docker-compose.coolify.yml` / `env.example` (the portal's own host name, e.g.
    `https://portal.<demo domain>`, never a path on the app host, ADR 0026 §3). Extend `tools/tests/test_compose.py`:
    the realm has `aip-portal` with exactly one redirect URI on `PORTAL_ORIGIN`, `minimum.acr.value` `aal2` and
    `directAccessGrantsEnabled: false`.
  - 2. Route allow-list, deny by default, in platform access:
    - `dependencies.py`: `authenticated(external=False)` and `requires(code, resource=None, external=False)`. A
      route declared with `external=True` accepts **only** external principals (an internal principal → 404
      `NOT_FOUND`); every other non-`public()` route refuses an external principal with 404 `NOT_FOUND` (not 403, so
      the portal cannot map the staff API). The access marker records the flag.
    - `route_check.py`: app start fails when a route declared `external=True` is mounted outside
      `EXTERNAL_PREFIXES = ("/api/v1/portal/",)`, or a route under that prefix is not declared `external=True`.
    - `main.py` builds `AccessPrincipal(external=...)` from `Principal.user_class == "portal"` (PORTAL-01) and also
      treats `Principal.audience == "portal"` as external, so a portal-audience session is external even if its user
      class were wrong; a portal-class user with an `app` audience session is refused by identity.
  - 3. Portal routes (`routes.py`, router prefix `/portal`, all `external=True`):
    - `GET /api/v1/portal/me` (`authenticated(external=True)`): calls `PortalApi.mark_signed_in` (PORTAL-01, so the
      first sign-in moves `invited` → `pending_approval`), then returns `{userId, displayName, companyName,
      effectiveStatus, projects: [{id, code, name, actions}]}` from `live_grants` and `ProjectsApi.get_project`
      (projects only while the status is `active`; `[]` otherwise). A user whose `portal_users` row is missing →
      404. Writes `AuditApi.record_security_event(conn, SecurityEventInput(event_type="portal.signed_in", ...))` once
      per session (first call of the session only).
    - `POST /api/v1/portal/logout` (`authenticated(external=True)`, CSRF checked by identity's middleware):
      `revoke_session(conn, session_id, "logout")`, then `clear_session_cookies(response, audience="portal")`; 204,
      `Cache-Control: no-store`.
    - Every portal response carries `Cache-Control: no-store`.
  - 4. Session policy: the portal session uses identity's `portal` policy (default 15 min idle, 8 h absolute, against
    30 min / 12 h for staff), set per tenant in `tenant_auth_policy.session_policy.portal`. Nothing new is stored;
    this task proves the behaviour (tests) and documents the keys in the module manifest comment.
  - 5. Rate limits (`rate_limit.py`): a fixed-window limiter on `/api/v1/portal/*`, keyed per session id (120
    requests per minute) and per client IP (300 per minute), shared through Valkey (`REDIS_URL`) with an in-process
    fallback when it is unset (tests); over the limit → 429 `{code: "RATE_LIMITED"}` with `Retry-After` in seconds,
    and one `portal.rate_limited` security event per key and window. Limits come from the manifest settings
    `PORTAL_RATE_LIMIT_SESSION_PER_MIN` / `PORTAL_RATE_LIMIT_IP_PER_MIN`. Sign-in attempts are limited by identity's
    login limiter on the portal login route.
  - 6. Term keys (en-AU) for `portal.signin.*`, `portal.status.pending_approval` ("Waiting for approval"),
    `RATE_LIMITED` and `NOT_FOUND`; regenerate `packages/api-client/openapi.json`.
- **acceptance**:
  - A client signs in only through `aip-portal` on the portal host, with password and second factor, and receives
    only `__Host-aip_portal_sid` / `__Host-aip_portal_csrf`; the staff cookie is never set on the portal host.
  - With a portal session every staff route (e.g. `GET /api/v1/projects`, `GET /api/v1/admin/portal/users`,
    `GET /api/v1/me/sessions`) answers 404; the portal routes answer.
  - A staff session on `GET /api/v1/portal/me` answers 404.
  - The app refuses to start if a portal-facing route sits outside `/api/v1/portal/` or a route there lacks the flag.
  - An idle portal session ends after 15 minutes by default; a staff session idle for the same time is still live.
- **tests**:
  - **unit**:
    - `route_check` with a route `GET /api/v1/projects` declared `requires("project.view", external=True)` → start
      refused naming the path; with `GET /api/v1/portal/x` declared `requires("portal.record.view")` (no flag) →
      refused.
    - A test app with `GET /api/v1/portal/ping` (`authenticated(external=True)`) and `GET /api/v1/things`
      (`authenticated()`): external principal → 200 and 404 `NOT_FOUND`; internal principal → 404 and 200; no
      principal → 401 on both.
    - Limiter with limit 3 per minute, a fixed clock: calls 1–3 → allowed, call 4 → `retry_after` 60 − elapsed
      seconds; the next window → allowed. Two session keys do not share a budget.
  - **integration** (testcontainers Postgres and Valkey, TESTING-01 tenants; sessions created with identity's
    `issue_session(..., audience="portal")` for a PORTAL-01 portal user, the Keycloak redirect covered by identity's
    own flow tests):
    - `GET /api/v1/portal/me` with the portal cookie of an `invited` user → 200 `effectiveStatus:
      "pending_approval"`, `projects: []`; `SELECT status FROM portal_users WHERE user_id = :u` → `pending_approval`;
      1 `audit.security_event` `domain_events` row with `portal.signed_in`; a second call adds none.
    - After the named owner approves (PORTAL-01 route) → `projects` lists P1 with `actions ["view","sign_off"]`.
    - The same portal session on `GET /api/v1/projects`, `GET /api/v1/admin/portal/users` and
      `GET /api/v1/approvals/instances/{id}` → 404 each; on `POST /api/v1/admin/portal/users` → 404 and
      `SELECT count(*) FROM portal_users` unchanged.
    - A staff session (`audience = "app"`) on `GET /api/v1/portal/me` → 404.
    - A `tenant-b` portal user's session → `/api/v1/portal/me` lists no `kaefer-demo` project, and
      `PolicyService.can(..., Resource(project_id=<kaefer P1>, tenant_id=<kaefer>))` is denied.
    - With `AIP_TEST_CLOCK_OFFSET` moved 16 minutes, the portal session → 401 `SESSION_EXPIRED` with both portal
      cookies cleared; a staff session moved 16 minutes → still 200 on `GET /api/v1/me`.
    - Tenant policy `{"portal": {"idleMin": 5}}` → expired after 6 minutes.
    - `POST /api/v1/portal/logout` → 204; the next `GET /api/v1/portal/me` with the same cookie → 401; the
      `user_session` row has `revoke_reason = 'logout'`.
    - 121 requests in one minute on one session → the 121st is 429 `RATE_LIMITED` with `Retry-After`; 1
      `portal.rate_limited` security event.
    - A suspended portal user (PORTAL-01 suspend) → their live sessions are revoked and the cookie gives 401.
  - **e2e**:
    - `e2e/web/portal-auth.spec.ts`, added to the `SKELETON` list in `e2e/playwright.config.ts` (it needs the compose
      stack and Keycloak), using Playwright's `request` fixture against the API (the portal host arrives with PORTAL-03):
      `POST /api/v1/auth/portal/login/start` with a seeded portal user's email → 200 whose authorize URL has
      `client_id=aip-portal`, `acr_values=aal2` and `redirect_uri` on `PORTAL_ORIGIN`; `GET /api/v1/portal/me`
      without a session → 401 `NOT_AUTHENTICATED`; a token request to the realm with `grant_type=password` and the
      `aip-portal` client → 400 `unauthorized_client`. The signed-in browser journey (invite email, password, TOTP enrolment, sign-in,
      pending approval, approval, inbox), the cross-tenant check and axe are PORTAL-03's, because the sign-in pages
      live in the portal app.
