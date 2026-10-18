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
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Give identity a portal audience: settings `PORTAL_ORIGIN`, `PORTAL_OIDC_CLIENT_ID` and `PORTAL_OIDC_CLIENT_SECRET`; public routes `POST /api/v1/auth/portal/login/start` and `GET /api/v1/auth/portal/oidc/callback` for the `aip-portal` client (local `user_class='portal'` accounts only, aal 2 required, `issue_session(audience="portal")`); the staff callback refuses portal users; cookies `__Host-aip_portal_sid` and `__Host-aip_portal_csrf` (ports do not separate cookies, so dev hosts would otherwise share `__Host-aip_sid`); `Principal.audience`, a middleware refusal on audience and cookie mismatch, CSRF accepting `PORTAL_ORIGIN`, `clear_session_cookies(response, audience=)` exported; `create_invite(user_class="portal")` forces the local method, uses `membership_type="client"` and links to the portal; tenant policy keeps portal idle at or below staff idle (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
