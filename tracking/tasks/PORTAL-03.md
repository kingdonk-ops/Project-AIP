# PORTAL-03 — Portal app: Vite build and container, sign-in, needs-my-action inbox

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-01, INSPECTIONS-05, PORTAL-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`PORTAL-01.md`](PORTAL-01.md) and [`PORTAL-02.md`](PORTAL-02.md) (grants, portal session, `external=True` routes)
3. [`docs/blueprint/modules/portal/routes.md`](../../docs/blueprint/modules/portal/routes.md) and
   [`ui-layout.md`](../../docs/blueprint/modules/portal/ui-layout.md): the portal home and sign-in sections only
4. ADRs: [0026](../../docs/adr/0026-web-delivery-behind-the-alb.md) (own host name, nginx security headers),
   [0036](../../docs/adr/0036-r1-module-decisions.md) (choice 7), [0025](../../docs/adr/0025-time-and-timezones.md)
   (UTC stored, local shown)
5. Code: `apps/web/` (`Dockerfile`, `nginx.conf`, `security-headers.json`, `vite.config.ts`, `package.json`,
   `src/main.tsx`, `src/router.ts`, `src/terms.ts`), `@aip/ui` (`packages/ui/src/index.ts`),
   `infra/coolify/nginx.conf`, `e2e/playwright.config.ts`, `e2e/fixtures/login.ts`, `e2e/web/walking-skeleton.spec.ts`

## Spec

Turn the `apps/portal` placeholder into a Vite + React app served by its own unprivileged nginx container on the
portal's own host, with sign-in through the `aip-portal` flow, a "waiting for approval" page, and a "needs my
action" inbox that lists the inspections awaiting the client within their grants, read through `InspectionsApi` by
a portal API route (tag: extend).

Out of scope: acting on an item (review, sign-off, hold-point release: PORTAL-04), witness (PORTAL-06), client
reports (PORTAL-05), the internal admin page (PORTAL-07), branding, share packs and the condition dashboard (not R1).

- **files**:
  - apps/portal/package.json
  - apps/portal/README.md
  - apps/portal/index.html
  - apps/portal/vite.config.ts
  - apps/portal/tsconfig.json
  - apps/portal/tsconfig.app.json
  - apps/portal/tsconfig.node.json
  - apps/portal/eslint.config.js
  - apps/portal/security-headers.json
  - apps/portal/nginx.conf
  - apps/portal/Dockerfile
  - apps/portal/src/main.tsx
  - apps/portal/src/router.ts
  - apps/portal/src/terms.ts
  - apps/portal/src/session.ts
  - apps/portal/src/routes/__root.tsx
  - apps/portal/src/routes/signin.tsx
  - apps/portal/src/routes/pending.tsx
  - apps/portal/src/routes/index.tsx
  - apps/portal/src/inbox/InboxList.tsx
  - apps/portal/src/inbox/InboxList.test.tsx
  - apps/portal/src/routes/signin.test.tsx
  - apps/portal/src/app.test.ts
  - apps/api/aip/modules/portal/routes.py
  - apps/api/aip/modules/portal/schemas.py
  - apps/api/aip/modules/portal/service.py
  - apps/api/aip/modules/portal/tests/test_inbox_db.py
  - config/terms/en-AU/portal.json
  - packages/api-client/openapi.json
  - infra/docker-compose.yml
  - infra/coolify/docker-compose.coolify.yml
  - infra/coolify/portal-nginx.conf
  - infra/coolify/env.example
  - tools/tests/test_compose.py
  - tools/tests/test_coolify.py
  - e2e/playwright.config.ts
  - e2e/fixtures/portal.ts
  - e2e/portal/portal.spec.ts
- **steps**:
  - 1. Inbox API. `GET /api/v1/portal/inbox?cursor=&limit=` (`requires("portal.record.view", external=True)`, limit
    1–50, default 20) in `routes.py`; `service.inbox(conn, principal)`:
    - (a) the caller's live grants that include `sign_off` (`PortalApi.live_grants`, PORTAL-01) become scopes
      `[(project_id, asset_id | None)]`; no such grant → `{items: [], nextCursor: null}` without calling inspections;
    - (b) `aip.modules.inspections.api.InspectionsApi.list_awaiting_party(conn, party="client", scopes=..., limit=..., after=...)`
      returns inspections in the client-review step for those scopes, oldest first, each with `inspectionId`,
      `projectId`, `assetId`, `assetPath`, `assetTag`, `title`, `state`, `awaitingSince` (UTC);
    - (c) each item is re-checked with `PolicyService.can(principal, "portal.record.sign_off", Resource(project_id=..., asset_path=...))`
      and dropped when denied (defence in depth: the list query and the policy must agree);
    - (d) the response `{items: [{id, kind: "inspection", title, projectCode, projectName, assetTag, stateKey, awaitingSince}], nextCursor}`
      carries no internal user names or comments; project code and name come from `ProjectsApi.get_project`;
    - (e) one `AuditApi.record_security_event(conn, SecurityEventInput(event_type="portal.inbox_viewed", detail={"count": n, "projectIds": [...]}))`
      per request, so every external view is in the audit chain.
  - 2. App scaffold in `apps/portal` (same toolchain and versions as `apps/web`): `package.json` `@aip/portal` with
    `dev`, `build` (`tsc -b && vite build`), `preview`, `lint`, `typecheck`, `test` scripts and the `@aip/ui`,
    `@aip/api-client`, React 19, TanStack Router and Query dependencies; `vite.config.ts` proxies `/api` to the API in
    dev and preview and applies `security-headers.json` as `apps/web` does (no CSP in `vite dev`); `index.html` with
    no inline script. `README.md` replaces the placeholder text (how to run, host name, what the app may call).
    Terms: `src/terms.ts` looks up `portal.*` keys with the en-AU defaults from `config/terms/en-AU/portal.json`.
  - 3. Pages (TanStack Router, `@aip/ui` components only, tokens from DESIGN-01, light and dark):
    - `/signin`: a "Work email" field and Continue; `POST /api/v1/auth/portal/login/start` → `window.location.assign`
      to the returned authorize URL; error codes (`INVALID_EMAIL`, `RATE_LIMITED`, `SESSION_EXPIRED` from a
      `?reason=` query) shown as term strings in an `aria-live` region. No password field in the app (Keycloak's
      themed page, DESIGN-07, takes the password and the code).
    - `__root.tsx`: loads `GET /api/v1/portal/me`; 401 → `/signin`; `effectiveStatus` `pending_approval` → `/pending`;
      `suspended` / `expired` → `/signin?reason=...`; a header with the company name, the signed-in name and Sign out
      (`POST /api/v1/portal/logout` with the CSRF header read from `__Host-aip_portal_csrf`, then `/signin`).
    - `/pending`: "Waiting for approval" with the named-owner explanation term; no data calls besides `/me`.
    - `/` (inbox): `InboxList` renders the items as a list (title, project, asset tag, a `StatusChip` for the state,
      "waiting since" in the browser's time zone via `Intl.DateTimeFormat`, ADR 0025), a Load more button for
      `nextCursor`, an empty state ("Nothing needs your action"), a loading state and an error state with retry. Rows
      are not links yet (PORTAL-04 adds the action page).
    - Any API 401 `SESSION_EXPIRED` → `/signin?reason=session_expired`.
  - 4. Container: `apps/portal/Dockerfile` copied from `apps/web/Dockerfile` (node build stage filtered to
    `@aip/portal...`, `nginxinc/nginx-unprivileged` runtime, UID 10001, read-only root, same base-image package
    upgrades). `apps/portal/nginx.conf` from `apps/web/nginx.conf`: the full security header set from
    `apps/portal/security-headers.json` repeated in every location (same values as the web app's, plus
    `form-action 'self' <keycloak origin>` only if the sign-in redirect needs it), the same `set_real_ip_from` /
    `X-Forwarded-For` handling, SPA fallback to `index.html`, and an API allow-list: only `/api/v1/portal/`,
    `/api/v1/auth/portal/`, `/api/v1/auth/oidc/backchannel-logout` and `/api/v1/health` are proxied to `api:8000`;
    every other `/api/` path returns 404 from nginx (defence in depth on top of PORTAL-02's route guard).
  - 5. Deployment: `infra/docker-compose.yml` gains a `portal` service (built from `apps/portal/Dockerfile`, the shared
    hardening anchor, port `127.0.0.1:8081:8080`, depends on `api` healthy) reached as
    `http://portal.localhost:8081`; `infra/coolify/docker-compose.coolify.yml` gains `portal` (image
    `aip-portal-demo`, built with `NGINX_CONF=infra/coolify/portal-nginx.conf`, which adds the `/auth` proxy to Keycloak
    like `infra/coolify/nginx.conf`) on its own host name from `env.example` (`PORTAL_HOST`), never a path on the
    app's host (ADR 0026 §3). The image build that publishes `aip-web-demo` also publishes `aip-portal-demo`.
    Extend `tools/tests/test_compose.py` and `tools/tests/test_coolify.py`: the `portal` service exists, runs as
    10001 with a read-only root, and both portal nginx configs carry every header in
    `apps/portal/security-headers.json` in every `location` and proxy no `/api/` path outside the allow-list.
  - 6. Term keys (en-AU) in `config/terms/en-AU/portal.json`: `portal.app.title` ("Client portal"),
    `portal.signin.*`, `portal.pending.*`, `portal.inbox.title` ("Needs your action"), `portal.inbox.empty`,
    `portal.inbox.waitingSince`, `portal.inbox.loadMore`, `portal.signout`, error codes. Regenerate
    `packages/api-client/openapi.json`; the portal uses the generated client.
  - 7. e2e (skeleton lane, needs the compose stack and Keycloak): `e2e/playwright.config.ts` adds projects `portal`
    and `portal-mobile` (`testMatch: "portal/*.spec.ts"`, `baseURL: process.env.E2E_PORTAL_URL ?? "http://portal.localhost:8081"`,
    Desktop Chrome and Pixel 7), only when `E2E_SKELETON` is set. `e2e/fixtures/portal.ts`: `invitePortalUser`
    (signs in a `kaefer-demo` admin with `loginAs`, steps up, POSTs the PORTAL-01 invite with a run-id email),
    `acceptInvite` (reads the invite link from Mailpit's API, sets a password and enrols TOTP by reading the secret
    from Keycloak's setup page and computing codes with the `otpauth` package), `approvePortalUser` (the named owner
    approves through the PORTAL-01 route) and `portalSignIn`. Credentials come only from the environment, as in
    `e2e/fixtures/tenants.ts`; generated passwords are never logged.
- **acceptance**:
  - `docker compose up` serves the portal at `http://portal.localhost:8081` with every security header; `/api/v1/projects`
    through the portal host is 404 from nginx.
  - A client signs in with password and code, sees "Waiting for approval" until the named owner approves, and then
    sees exactly the inspections awaiting them on the projects and asset subtrees they were granted.
  - Every inbox load writes one `portal.inbox_viewed` security event.
  - The portal build contains no staff routes or admin calls (only `/api/v1/portal/*` and the portal sign-in route).
- **tests**:
  - **unit**:
    - `InboxList` (Vitest + Testing Library) with 2 items → 2 list items, the second showing "Waiting since" in the
      test's `TZ=Australia/Perth` for `2026-11-02T01:30:00Z` as `2 Nov 2026, 9:30 am`; with `[]` → the
      `portal.inbox.empty` text; with a rejected query → the error text and a Retry button that refetches.
    - `/signin`: submitting `not-an-email` shows the `INVALID_EMAIL` term; a 429 response shows the `RATE_LIMITED`
      term; a 200 calls `window.location.assign` with the returned URL.
    - `app.test.ts`: the built route tree has exactly `/`, `/signin`, `/pending`; no source file under
      `apps/portal/src` references `/api/v1/` outside `/api/v1/portal/` and `/api/v1/auth/portal/` (static scan).
    - axe-core on the rendered `InboxList` and `/signin` → 0 violations.
  - **integration** (testcontainers Postgres, TESTING-01 tenants; inspections in the client-review step created
    through `InspectionsApi` in the test setup):
    - Portal user U1 with a `sign_off` grant on P1 (no asset) and P1 holding 3 inspections awaiting the client plus 1
      in draft → `GET /api/v1/portal/inbox` → 200 with 3 items, oldest `awaitingSince` first; 1
      `audit.security_event` `domain_events` row with `portal.inbox_viewed` and `count: 3`.
    - U2 with a `sign_off` grant on P1 limited to asset A (subtree) → only the items whose asset is A or under A; an
      item on A's sibling is absent.
    - U3 with only a `view` grant on P1 → 200 `items: []`.
    - U1 with `limit=2` → 2 items and a `nextCursor`; the next page → 1 item, `nextCursor: null`.
    - After `DELETE` of U1's grant (PORTAL-01) → `items: []` on the next request.
    - A `tenant-b` portal user with a `sign_off` grant on a `tenant-b` project → sees only `tenant-b` items, never
      the 3 `kaefer-demo` ones.
    - A staff session on `GET /api/v1/portal/inbox` → 404 (PORTAL-02 guard).
  - **e2e** (`e2e/portal/portal.spec.ts`, projects `portal` and `portal-mobile`):
    - Main journey: the fixture invites a client on project P1 with `["view","sign_off"]`; the client accepts the
      invite (password, TOTP), opens `/signin`, enters the email, completes Keycloak's password and code steps, lands
      on `/pending` ("Waiting for approval"); the owner approves; after reload the inbox shows the seeded inspection
      awaiting client review; Sign out returns to `/signin` and the `__Host-aip_portal_sid` cookie is gone; the
      staff cookie `__Host-aip_sid` was never set for the portal host.
    - Cross-grant: a second client granted only on P2 sees an inbox without the P1 inspection, and a direct
      `fetch("/api/v1/portal/inbox")` from that page returns no P1 item.
    - Cross-tenant: a `tenant-b` client signed in on the same portal sees none of `kaefer-demo`'s items, and
      `fetch("/api/v1/projects")` from the portal page → 404.
    - Session: after the fixture moves the session's idle expiry (`AIP_TEST_CLOCK_OFFSET` on the compose API), the next
      inbox refresh lands on `/signin?reason=session_expired`.
    - axe (`@axe-core/playwright`) on `/signin`, `/pending` and the inbox → 0 violations, on both projects.
