# DESIGN-02 — App shell (header, nav rail, scope bar) + login/logout

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-01, IDENTITY-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md)
3. ADRs: 0004 (apps/web Next.js App Router), 0005 (the app issues opaque `__Host-` session cookies, Keycloak only brokers SSO, browsers never hold JWTs), 0007 (M0 shell)
4. Only if the step needs it: [`docs/blueprint/03-site-hierarchy.md`](../../docs/blueprint/03-site-hierarchy.md) for nav sections, and the login/callback/logout routes in IDENTITY-01's merged controller

## Spec

Build the constant frame of the desktop web app (56px header, 56px nav rail, scope bar, content slot) and the login and logout pages. Sign-in goes through the API's OIDC broker flow, so the browser only ever holds the app's session cookie.

- **files**:
  - apps/web/src/features/shell/AppShell.tsx
  - apps/web/src/features/shell/Header.tsx
  - apps/web/src/features/shell/NavRail.tsx
  - apps/web/src/features/shell/ScopeBar.tsx
  - apps/web/src/features/shell/nav-registry.ts
  - apps/web/src/features/shell/session.ts
  - apps/web/src/features/shell/t.ts
  - apps/web/src/features/shell/__tests__/
  - apps/web/src/app/(app)/layout.tsx
  - apps/web/src/app/(app)/page.tsx
  - apps/web/src/app/login/page.tsx
  - apps/web/src/middleware.ts
  - apps/web/next.config.ts
  - config/terms/en-AU/shell.json
- **steps**:
  - 1. In next.config.ts, rewrite `/api/v1/*` to the API service (`API_INTERNAL_URL`), so the browser talks to one origin and the API's `__Host-` cookie is first-party. Set security headers: CSP without `unsafe-inline` scripts (nonce via middleware), `frame-ancestors 'none'`, `Referrer-Policy: strict-origin-when-cross-origin`.
  - 2. In t.ts, add `t(key, params?)` reading `config/terms/en-AU/*.json` at build time, unless `packages/terms` (TERMS-08) is already merged, in which case re-export its `t`. A missing key renders a visible `⟦key⟧` marker and logs a warning; it never renders an empty string. TERMS-08 replaces the source without changing call sites.
  - 3. In session.ts, add server-side `getSession()`, which forwards the incoming cookie to the session or principal endpoint IDENTITY-01 exposes (switch to `GET /api/v1/me` when IDENTITY-02 is merged). It returns `{user:{id, name, email}, tenant:{slug, name}, permissions[]}` or null.
  - 4. In middleware.ts, a request to any `(app)` route with no session cookie redirects to `/login?next=<path>`, and `next` must be a same-origin relative path. The `(app)/layout.tsx` calls `getSession()` and redirects to `/login` when it returns null, for example on an expired session.
  - 5. Build the login page at `/login`: an email (or tenant slug) field posts to IDENTITY-01's login start route, which resolves the tenant via `login_directory` and redirects to Keycloak. Show the error states the API returns (unknown domain, tenant suspended) with term keys and enumeration-safe wording. Show no password field until IDENTITY-04 lands.
  - 6. Logout is a POST (a form button, never a GET link) to IDENTITY-01's logout route, which clears the cookie and ends the Keycloak session, then lands on `/login?signed_out=1`.
  - 7. Build AppShell. The header has the tenant name and logo slot, a project switcher slot (empty until PROJECTS-03), a search placeholder slot, and a user menu with name, email and Sign out. The nav rail has icons with tooltips and labels, built from `nav-registry.ts`, where features register `{id, section, href, icon, termKey, permission}`. Sections follow 03-site-hierarchy. Items whose permission the principal lacks are not rendered. The scope bar shows a tenant chip and a project chip (when selected) and leaves room for the asset-subtree chip later. Add skip-to-content, landmark roles (`banner`, `navigation`, `main`) and keyboard navigation of the rail. Add a placeholder `(app)/page.tsx` Home ("My Work" comes later).
  - 8. Responsive behaviour: at widths under 768px, the rail collapses into a menu button. Density comes from `data-density` on `<html>` (compact by default).
- **acceptance**:
  - Unauthenticated access to `/` or `/projects` redirects to `/login?next=…`. After Keycloak sign-in the user lands on `next`.
  - No JWT or Keycloak token is ever readable by page JavaScript. `document.cookie` does not contain the session cookie, because it is HttpOnly.
  - Logout invalidates the session. The browser Back button followed by a reload returns to `/login`.
  - Every shell label comes from a term key. axe shows no serious or critical violations on the shell and the login page.
- **tests**:
  - **unit**:
    - `nav-registry` with items requiring `project.view` and `audit.view`, and a principal holding only `project.view`, renders exactly 1 item.
    - The middleware with no cookie on `/projects?status=active` redirects to `/login?next=%2Fprojects%3Fstatus%3Dactive`. With `next=https://evil.example`, the login page ignores it and uses `/`.
    - `t('shell.nav.projects')` returns "Projects". `t('missing.key')` returns `⟦missing.key⟧`.
  - **integration**:
    - Run the web app against the compose stack (API plus Keycloak from IDENTITY-01) and call `getSession()` with no cookie. Expected: null. With a cookie from a completed login. Expected: the tenant slug is `kaefer-demo`.
    - Response headers on `/login` include a CSP with a nonce, `frame-ancestors 'none'` and no `unsafe-inline` in `script-src`.
  - **e2e** (Playwright, project `web`):
    - Go to `/projects`, get redirected to `/login`, enter `admin@kaefer-demo.test`, complete the Keycloak form, and land on `/projects`. The header shows tenant "Kaefer Demo" and the user menu shows the email.
    - Click Sign out. Expected: `/login?signed_out=1`. Visiting `/` again redirects to `/login`.
    - In the signed-in page, `await page.evaluate(() => document.cookie)` does not contain `__Host-`.
