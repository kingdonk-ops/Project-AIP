# SECURITY-14 — Refuse dev secrets outside dev and test

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | IDENTITY-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md)
3. ADRs: 0005
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M4**. `infra/keycloak/realm-aip.json:622,691` falls back to
`${AIP_API_CLIENT_SECRET:aip_api_dev_only_secret}` and `${AIP_ADMIN_CLIENT_SECRET:aip_admin_dev_only_secret}`; `aip-admin`
holds `manage-users`. `IdentitySettings` refuses the dev cookie key only when `AIP_ENV == "production"` (a denylist).
Coolify is safe today because it uses `${VAR:?}`. The review lists the API allowlist check as a quick fix that may
land first; if it has, this task is the realm overlay only.

## Spec

Neither the API nor a deployed Keycloak realm can run with a publicly known dev secret.

- **files**:
  - apps/api/aip/modules/identity/settings.py
  - infra/keycloak/ (deployed-realm overlay)
  - tools/tests/ or identity tests
- **steps**:
  - 1. The API refuses to start with any known dev secret unless `AIP_ENV` is `development` or `test` (an allowlist).
  - 2. Add a deployed-realm overlay with no secret defaults, or a post-import check that fails on a dev secret.
- **acceptance**:
  - `AIP_ENV=demo` (or `staging`, `production`) with a dev secret → start-up fails with a clear message.
  - A Keycloak import for a deployed environment without the env vars fails instead of using the public secret.
- **tests**:
  - **unit**:
    - each non-dev `AIP_ENV` × each known dev secret → settings validation error
    - deployed overlay → no `${VAR:default}` with a default for a client secret
