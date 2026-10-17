# SECURITY-11 — Harden the public demo: mock-IdP secrets, API/web edge headers + HSTS, signed+scanned deploy

<!-- hand-edited: merged SECURITY-12 (Part B) and SECURITY-15 (Part C) per board re-draw 2026-10-17 -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-11, OPS-04, SECURITY-08 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. ADRs: 0011 (image scanning), 0026 (web delivery behind the ALB); see OPS-11 for the Coolify demo
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), findings **H1** (Part A), **M2** (Part B), **M6** (Part C)

> This task merges three Review-11 hardening items for the public demo surface: Part A (was SECURITY-11)
> mock-IdP secrets, Part B (was SECURITY-12) API/web edge hardening, Part C (was SECURITY-15) a gated,
> signed, scanned deploy. They share the Coolify demo pipeline and are small individually.

## Part A — mock-IdP users from secrets, not committed passwords (review 11 H1)

### Background

The repo is public, and `infra/keycloak/realm-mock-idp.json` commits `alice@kaefer.test` and
`bob@acme.test` with their passwords. The realm is built into the demo Keycloak image, publicly routed, and
`admin-bootstrap` makes both users `tenant_admin`. So anyone who reads GitHub is tenant admin of both demo tenants.

**Stopgap already done (PR #101):** the mock-IdP realm disables `UPDATE_PROFILE`, `UPDATE_EMAIL`,
`VERIFY_PROFILE`, `UPDATE_PASSWORD` and `CONFIGURE_TOTP`; username, email and names are admin-edit only; the demo
nginx returns 404 on `/auth/realms/mock-idp/account`. The running demo needs the owner's `kcadm` step from PR #101.
This task is the full fix.

### Spec

The public Coolify demo no longer ships mock-IdP users whose passwords are in the public repo; demo users are created at deploy time from Coolify secrets.

- **files**:
  - infra/keycloak/ (a demo-only mock-IdP realm with no users)
  - infra/coolify/images/keycloak.Dockerfile
  - infra/coolify/docker-compose.coolify.yml (user creation from secrets, admin-bootstrap)
  - infra/coolify/nginx.conf
  - .github/workflows/deploy-coolify.yml
  - tools/tests/test_coolify.py
- **steps**:
  - 1. Build the demo image from a mock-IdP realm with no users. Keep `realm-mock-idp.json` with users for local dev and CI only.
  - 2. At deploy time, create alice and bob (or set their passwords) from Coolify secrets, e.g. a one-shot `kcadm` container, with `${VAR:?}` so a missing secret fails the deploy.
  - 3. Keep the PR #101 account-console block and disabled required actions.
  - 4. Owner: rotate the demo passwords and `E2E_PASS_A/B`; document the step in the PR.
  - 5. Optional (owner decides): Traefik basic auth or an IP allow-list in front of the demo.
- **acceptance**:
  - No password for a demo-deployed user appears in the repo or in the demo image.
  - A deploy without the user secrets fails rather than starting with defaults.
  - The committed dev passwords do not sign in to the demo.
- **tests**:
  - **unit**:
    - the demo realm file has no `users` and no `credentials` → `test_coolify.py` passes; adding one fails it
  - **integration**:
    - compose with the demo realm and test secrets → alice signs in with the secret password, not the committed one
  - **e2e**:
    - `e2e-skeleton` against the demo with the rotated `E2E_PASS_A/B` → green

## Part B — API edge hardening: body size cap, security headers, HSTS (merged from SECURITY-12, review 11 M2)

### Background

No body-size middleware exists, and ADR 0026 routes `/api/*` straight to the API. The API sends no
`nosniff`, `frame-ancestors`/`X-Frame-Options` or HSTS. ADR 0026:28 says nginx sends HSTS, but
`apps/web/nginx.conf` has none.

### Spec

The API caps request bodies and sends security headers on the ALB→API path, and the web nginx sends the HSTS that ADR 0026 promises.

- **files**:
  - apps/api/aip/ (ASGI middleware)
  - apps/web/nginx.conf
  - tools/tests/test_nginx_headers.py
  - docs/adr/0026-web-delivery-behind-the-alb.md (if wording changes)
- **steps**:
  - 1. Add an ASGI middleware that rejects bodies over about 1 MiB with 413 (uploads use presigned POST, so the API never needs more), including chunked bodies.
  - 2. Add a security-headers middleware: `X-Content-Type-Options: nosniff`, `frame-ancestors 'none'`/`X-Frame-Options: DENY`, HSTS.
  - 3. Add HSTS to `apps/web/nginx.conf` and extend `test_nginx_headers.py`.
- **acceptance**:
  - A 2 MiB JSON body gets 413 without being buffered whole.
  - Every API response carries the headers.
  - The web nginx sends HSTS.
- **tests**:
  - **unit**:
    - body of 1 MiB + 1 byte, with and without Content-Length → 413
    - any route → nosniff, frame-ancestors and HSTS headers present
  - **integration**:
    - `test_nginx_headers.py` → HSTS present

## Part C — gate and sign the demo deploy (merged from SECURITY-15, review 11 M6)

### Background

`deploy-coolify.yml:41-62` builds, pushes and deploys on every push to main without depending on
`security.yml`. The keycloak, postgres and migrator demo images are never Trivy-scanned or SBOM'd. Lines
118-120 pin actions by tag (`security.yml` pins by SHA). Cosign signs local image ids and falls back to an
ephemeral key (`security.yml:173-179`).

### Spec

Nothing reaches the internet-facing demo unscanned or unsigned.

- **files**:
  - .github/workflows/deploy-coolify.yml
  - .github/workflows/security.yml
- **steps**:
  - 1. Gate the deploy on the security jobs (same workflow or `workflow_run`).
  - 2. Scan and SBOM all five demo images.
  - 3. SHA-pin the deploy workflow's actions.
  - 4. Sign the pushed registry digests, not local ids.
  - 5. Fail on `main` when `COSIGN_PRIVATE_KEY` is missing (owner adds the secret, review O2).
- **acceptance**:
  - A failing scan stops the deploy.
  - All five images have a Trivy result and an SBOM.
  - `cosign verify` passes on the pushed digests.
- **tests**:
  - **integration**:
    - workflow lint (actionlint) → every `uses:` is SHA-pinned
    - a dry run with a seeded critical vuln → the deploy job does not run
