# SECURITY-11 — Demo mock-IdP users from secrets, not committed passwords

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | OPS-11 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. ADRs: none specific; see OPS-11 for the Coolify demo
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **H1**. The repo is public, and `infra/keycloak/realm-mock-idp.json` commits `alice@kaefer.test` and
`bob@acme.test` with their passwords. The realm is built into the demo Keycloak image, publicly routed, and
`admin-bootstrap` makes both users `tenant_admin`. So anyone who reads GitHub is tenant admin of both demo tenants.

**Stopgap already done (PR #101):** the mock-IdP realm disables `UPDATE_PROFILE`, `UPDATE_EMAIL`,
`VERIFY_PROFILE`, `UPDATE_PASSWORD` and `CONFIGURE_TOTP`; username, email and names are admin-edit only; the demo
nginx returns 404 on `/auth/realms/mock-idp/account`. The running demo needs the owner's `kcadm` step from PR #101.
This task is the full fix.

## Spec

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
