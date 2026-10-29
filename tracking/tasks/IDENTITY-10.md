# IDENTITY-10 — Portal audience: aip-portal sign-in routes, portal session cookies and invites for client accounts

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions, choice 7),
   [0005](../../docs/adr/0005-identity-architecture.md) (Keycloak holds passwords and second factors),
   [0034](../../docs/adr/0034-invites-and-step-up-implementation.md) (invites)
4. [`PORTAL-02.md`](PORTAL-02.md) ("Identity owns the OIDC flow ..." paragraph: what PORTAL-02 expects from this task)

## Spec

Give identity a portal audience: settings `PORTAL_ORIGIN`, `PORTAL_OIDC_CLIENT_ID` and `PORTAL_OIDC_CLIENT_SECRET`; public routes `POST /api/v1/auth/portal/login/start` and `GET /api/v1/auth/portal/oidc/callback` for the `aip-portal` client (local `user_class='portal'` accounts only, aal 2 required, `issue_session(audience="portal")`); the staff callback refuses portal users; cookies `__Host-aip_portal_sid` and `__Host-aip_portal_csrf` (ports do not separate cookies, so dev hosts would otherwise share `__Host-aip_sid`); `Principal.audience`, a middleware refusal on audience and cookie mismatch, CSRF accepting `PORTAL_ORIGIN`, `clear_session_cookies(response, audience=)` exported; `create_invite(user_class="portal")` forces the local method, uses `membership_type="client"` and links to the portal; tenant policy keeps portal idle at or below staff idle (tag: extend).

Spec written 2026-10-28 (PLAN-R1 merged). Consumers: PORTAL-01 (calls `create_invite(conn, ..., user_class="portal")`),
PORTAL-02 (portal routes, `Principal.audience`, `clear_session_cookies(response, audience="portal")`, the realm's
`aip-portal` client). No migration: `user_session.audience` (`app`/`portal`/`device`), `tenant_membership.membership_type`
(`client`) and `app_user.user_class` (`portal`) already exist (IDENTITY-02/03).

Out of scope: the `aip-portal` client in `infra/keycloak/realm-aip.json` and the compose/Coolify variables (PORTAL-02
step 1; until then a portal sign-in against the dev Keycloak fails at Keycloak, and the portal invite email's "back to
the application" link needs that client); the portal route allow-list and `AccessPrincipal.external` (PORTAL-01/02);
portal step-up for client sign-off (PORTAL-04: `GET /api/v1/auth/step-up/start` stays a staff-audience flow and
refuses a portal session); the portal web app (PORTAL-03). A client who must work with two tenants is still one
email registered to one tenant (`identity_register_email`, unchanged).

- **files**:
  - apps/api/aip/modules/identity/settings.py
  - apps/api/aip/modules/identity/sessions.py
  - apps/api/aip/modules/identity/session_store.py
  - apps/api/aip/modules/identity/principal.py
  - apps/api/aip/modules/identity/csrf.py
  - apps/api/aip/modules/identity/wiring.py
  - apps/api/aip/modules/identity/preauth_cookie.py
  - apps/api/aip/modules/identity/schemas.py
  - apps/api/aip/modules/identity/service.py
  - apps/api/aip/modules/identity/jit.py
  - apps/api/aip/modules/identity/login_session.py
  - apps/api/aip/modules/identity/oidc.py
  - apps/api/aip/modules/identity/routes.py
  - apps/api/aip/modules/identity/invites.py
  - apps/api/aip/modules/identity/jobs.py
  - apps/api/aip/modules/identity/api.py
  - apps/api/aip/modules/identity/manifest.toml
  - apps/api/aip/modules/identity/tests/conftest.py (the OIDC stub takes a client id and secret)
  - apps/api/aip/modules/identity/tests/test_portal_unit.py (new)
  - apps/api/aip/modules/identity/tests/test_portal_routes.py (new)
  - apps/api/aip/modules/identity/tests/sessions/test_portal_sessions_db.py (new)
  - apps/api/aip/modules/identity/tests/invites/test_portal_invites_db.py (new)
  - apps/api/aip/platform/dev_secrets.py
  - packages/api-client/ (regenerated: the two portal auth routes)
- **steps**:
  - 1. **Settings** (`settings.py`): `portal_origin` (`PORTAL_ORIGIN`, default `http://portal.localhost:8081`),
    `portal_oidc_client_id` (`PORTAL_OIDC_CLIENT_ID`, default `aip-portal`), `portal_oidc_client_secret`
    (`PORTAL_OIDC_CLIENT_SECRET`, optional `SecretStr`: a deployment without the portal keeps staff sign-in working,
    and the portal routes answer 503 `PORTAL_NOT_CONFIGURED`), property `portal_redirect_uri` =
    `<PORTAL_ORIGIN>/api/v1/auth/portal/oidc/callback`. The dev secret `aip_portal_dev_only_secret` joins
    `DEV_SECRETS` (SECURITY-11 Part D) and is refused outside development and test, like `OIDC_CLIENT_SECRET`.
    The compose/Coolify variables and `.env.example` entries come with PORTAL-02 step 1 (it owns the realm client).
  - 2. **Cookies per audience** (`sessions.py`): `SESSION_COOKIES = {"app": ("__Host-aip_sid", "__Host-aip_csrf"),
    "portal": ("__Host-aip_portal_sid", "__Host-aip_portal_csrf")}` (the `device` audience has no browser cookie:
    `ValueError`). `IssuedSession` gains `audience` (default `app`), `issue_session(..., audience=)` records it,
    `rotate_session` keeps it, `set_session_cookies(response, issued)` writes the names of `issued.audience`,
    `clear_session_cookies(response, audience="app")` clears that audience's pair only (the portal host never gets a
    staff `Set-Cookie`). Pure `audience_allows(audience, user_class)`: a `portal` session only for a `portal` user and
    a `portal` user only in a `portal` session (`device` is the field class's, unchanged: allowed for non-portal).
  - 3. **Which cookie a request uses** (`session_store.py`, shared with `csrf.py`): `select_session_cookie(path,
    cookies) -> (audience, value) | None`. One session cookie → that one. Both (dev hosts that share cookies) → the
    portal cookie under `/api/v1/portal/` and `/api/v1/auth/portal/`, else the staff cookie. `SessionMiddleware`
    resolves only the selected cookie and records its audience; `SessionStore.resolve(sid, audience=)` returns
    `None` (so 401 `SESSION_EXPIRED`) when the row's audience differs from the cookie's, or `audience_allows` fails
    (also for a cached entry). The `SESSION_EXPIRED` handler and `POST /api/v1/auth/logout` clear the cookies of
    the audience that was presented.
  - 4. **`Principal.audience`** (`principal.py`): `Literal["app", "portal", "device"]`; built from the session row.
    When omitted (the test header stub) it defaults to `portal` for a `portal` user class, else `app`.
  - 5. **CSRF** (`csrf.py`): `CsrfMiddleware(app_origin=, portal_origin=)` (`PORTAL_ORIGIN` from the environment). A
    request carrying the staff cookie needs `Origin == APP_ORIGIN` and `X-CSRF-Token == __Host-aip_csrf`; one
    carrying the portal cookie needs `Origin == PORTAL_ORIGIN` and `X-CSRF-Token == __Host-aip_portal_csrf` (with
    both, the selected cookie of step 3 decides). `POST /api/v1/auth/portal/login/start` is checked for `Origin`
    only, against `PORTAL_ORIGIN` (the staff login start keeps `APP_ORIGIN`).
  - 6. **Portal sign-in** (`service.py`, `routes.py`):
    - `PreAuthState.audience` (`app`/`portal`, default `app`) seals which flow started; `LoginService.complete`
      refuses a cookie of the other audience (400 `INVALID_STATE`), so a portal pre-auth cookie cannot finish at the
      staff callback or the reverse.
    - `LoginService(..., audience="portal").start(email, return_to)`: never consults the login directory and never sends
      `kc_idp_hint` (portal accounts are local); the authorize URL carries `client_id=<PORTAL_OIDC_CLIENT_ID>`,
      `redirect_uri=<portal_redirect_uri>` and `acr_values=aal2`; the answer is always `{method: "password",
      redirectUrl}` (no account enumeration).
    - `POST /api/v1/auth/portal/login/start` (public, the same 10/min per IP limiter as staff, its own key) and
      `GET /api/v1/auth/portal/oidc/callback` (public; clears the pre-auth cookie on every outcome; `no-store`), with a
      portal `LoginService` built on the `aip-portal` client (`get_portal_login_service`, overridable).
    - `complete` for the portal audience: an `identity_provider` claim is refused (`IDP_TENANT_MISMATCH`, no broker),
      `acr` must be `aal2` (`MFA_NOT_SATISFIED`), and the callback refuses any `aal` below 2.
    - `VerifiedExternalIdentity.audience` carries the flow's audience into JIT. `decide_jit(..., audience=)`: an
      existing `portal` user at the staff callback → `PORTAL_SIGN_IN_REQUIRED`; a non-portal user (or an SSO sign-in)
      at the portal callback → `STAFF_SIGN_IN_REQUIRED`; both are `login.denied` auth events with nothing changed
      (no link, no activation, no invite accepted). An invited portal user signing in through the portal is linked
      and activated as for staff (`invite.accepted`).
    - `portal_login_handler` (`login_session.py`): `issue_session(audience="portal", user_class="portal")`, 303 to the
      safe same-origin `returnTo` with only `__Host-aip_portal_sid` / `__Host-aip_portal_csrf` set. Overridable
      dependency `get_portal_login_handler`.
  - 7. **Back-channel logout** (`oidc.py`, `routes.py`): `verify_logout_token(client, token, audiences=)` accepts a
    logout token for the staff or the portal client (same realm, same JWKS), so the `aip-portal` client can use the
    existing `POST /api/v1/auth/oidc/backchannel-logout`.
  - 8. **Portal invites** (`invites.py`, `jobs.py`): `create_invite(..., user_class="portal")` always uses the
    `local` method (no SSO user, no `kc_idp_hint`; a domain an SSO IdP claims is still refused by
    `identity_register_email` → 409 `EMAIL_DOMAIN_SSO`), creates the membership as `membership_type="client"`, and
    re-inviting an existing invited user of another class is 409 `USER_EXISTS`. The `invite.created` event detail adds
    `"audience": "portal"`. `send_invite` asks Keycloak for the actions email with `client_id=<PORTAL_OIDC_CLIENT_ID>`
    for a portal invite (its "back to the application" link is the `aip-portal` client's base URL, `PORTAL_ORIGIN`),
    `aip-api` for staff. `CreatedInvite` is unchanged.
  - 9. **Policy** (`sessions.load_policy`): the `portal` idle timeout is capped at the tenant's `staff` idle timeout
    (`min(portal idle, staff idle)`), defaults included; the absolute timeout is unchanged.
  - 10. **Published interface** (`api.py`, additive only): `Audience`, `clear_session_cookies`, `set_session_cookies`,
    `SESSION_COOKIES`, `get_portal_login_handler`. Manifest comment and `settings` list gain the three variables.
    Regenerate `packages/api-client` (`make generate-client`).
- **acceptance**:
  - A portal user signs in only through the portal routes, with a local account at aal 2, and receives only the
    portal cookies; the staff callback refuses them, and the portal callback refuses staff.
  - A session presented under the other audience's cookie is refused (401 `SESSION_EXPIRED`).
  - Unsafe portal-cookie requests pass CSRF only from `PORTAL_ORIGIN` with the portal CSRF token.
  - `create_invite(user_class="portal")` makes a local, `client`-membership invite whose email links to the portal.
  - A tenant cannot configure a portal idle timeout longer than its staff idle timeout.
  - Existing staff sign-in, sessions, CSRF and invites behave as before (their tests unchanged and green).
- **tests**:
  - **unit** (`test_portal_unit.py`):
    - `select_session_cookie`: one staff cookie → `app`; one portal cookie → `portal` on any path; both →
      `portal` under `/api/v1/portal/x` and `/api/v1/auth/portal/login/start`, `app` under `/api/v1/me`.
    - `audience_allows`: (`portal`, `portal`) and (`app`, `staff`) true; (`app`, `portal`), (`portal`, `staff`) false.
    - `set_session_cookies` for a portal `IssuedSession` sets exactly the two portal `__Host-` cookies (sid
      HttpOnly, csrf readable); `clear_session_cookies(r, audience="portal")` clears only those.
    - `csrf_ok`: portal cookie + `PORTAL_ORIGIN` + matching portal token → allowed; portal cookie with `APP_ORIGIN`,
      or the staff token → refused; staff cookie with `PORTAL_ORIGIN` → refused; portal login start from `APP_ORIGIN`
      → refused, from `PORTAL_ORIGIN` or without `Origin` → allowed.
    - `Principal` from JSON with `userClass: "portal"` and no audience → `audience == "portal"`; staff → `app`.
    - `_policy_from` / the cap: `{"staff": {"idleMin": 10}, "portal": {"idleMin": 20}}` → portal idle 10 min; the
      defaults → portal 15 min (staff 30).
    - `decide_jit`: a `portal` user at audience `app` → `PORTAL_SIGN_IN_REQUIRED`; a `staff` user at `portal` →
      `STAFF_SIGN_IN_REQUIRED`; an SSO sign-in at `portal` → `STAFF_SIGN_IN_REQUIRED`; an invited local portal user at
      `portal` → `link`.
    - Settings: the dev portal secret with `AIP_ENV=production` → `IdentitySettingsError`; `portal_redirect_uri`.
    - `check_logout_claims` with `audiences=("aip-api", "aip-portal")` accepts a token for `aip-portal`.
  - **routes** (`test_portal_routes.py`, the in-process OIDC stub of `conftest.py`):
    - `POST /api/v1/auth/portal/login/start` for a known SSO domain and an unknown one → same shape, `method:
      "password"`, no `kc_idp_hint`, `client_id=aip-portal`, `acr_values=aal2`, `redirect_uri` on `PORTAL_ORIGIN`.
    - The portal callback with a stub token: `aal2` local → the placeholder echo carries `audience: "portal"`; an
      `identity_provider` claim → 403 `IDP_TENANT_MISMATCH`; `acr=aal1` → 403 `MFA_NOT_SATISFIED`; a staff pre-auth
      cookie at the portal callback (and the reverse) → 400 `INVALID_STATE`.
    - Portal login start without `PORTAL_OIDC_CLIENT_SECRET` → 503 `PORTAL_NOT_CONFIGURED`; staff login start still 200.
  - **integration** (`test_portal_sessions_db.py`, Testcontainers Postgres, tenants `kaefer-demo` / `tenant-b`):
    - Full portal sign-in: an invited portal user (`create_invite(user_class="portal")`, invite marked sent) →
      login start, stub authorize, portal callback → 303, `Set-Cookie` only `__Host-aip_portal_sid` and
      `__Host-aip_portal_csrf`, the `user_session` row `audience = 'portal'`, the user `active`, the invite
      `accepted`; `GET /api/v1/me` with the portal cookie → 200 with the portal user.
    - The same portal user at the staff callback → 403 `PORTAL_SIGN_IN_REQUIRED`, one `login.denied` event, no session;
      Alice (staff) at the portal callback → 403 `STAFF_SIGN_IN_REQUIRED`.
    - A portal-audience session's sid sent as `__Host-aip_sid` → 401 `SESSION_EXPIRED` clearing the staff pair; a
      staff session's sid as `__Host-aip_portal_sid` → 401 clearing the portal pair; a portal session row for a staff
      user → 401.
    - `POST /api/v1/auth/logout` with the portal cookie from `PORTAL_ORIGIN` + portal CSRF token → 204, row
      `revoke_reason = 'logout'`, only portal cookies cleared; the same without the token → 403 `CSRF_FAILED`.
    - Tenant policy `{"staff": {"idleMin": 10}, "portal": {"idleMin": 60}}` → a new portal session's
      `idle_seconds` is 600.
    - The back-channel logout route with a verified token for the portal client revokes the portal session.
  - **integration** (`test_portal_invites_db.py`): `create_invite(user_class="portal")` for an unknown-domain email →
    `method == "local"`, `app_user.user_class = 'portal'`, `sso_managed = false`, membership `client`, the email
    registered to `kaefer-demo`, one `identity.send_invite` job, event detail `audience: "portal"`; for an email of
    the tenant's own SSO domain (`kaefer.test`) → 409 `EMAIL_DOMAIN_SSO` and nothing written; re-inviting an invited
    staff email as portal → 409 `USER_EXISTS`; `send_invite` with a fake Keycloak admin sends the actions email with
    `client_id="aip-portal"` for the portal invite and `aip-api` for a staff one.
  - **e2e**:
    - None in this task: the `aip-portal` Keycloak client and the portal host arrive with PORTAL-02/PORTAL-03, whose
      e2e (`e2e/web/portal-auth.spec.ts`) covers the authorize URL against the compose stack.
