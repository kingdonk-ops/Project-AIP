# SECURITY-10 — Secret rotation without downtime (90-day Secrets Manager rotation)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | IDENTITY-03, STACK-07 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. ADRs: 0002 and 0012 (database roles), 0005 (identity), 0006 (KMS keys)

## Spec

Every secret the app holds must survive a 90-day AWS Secrets Manager rotation with no failed requests.
ECS injects secrets only when a task starts, so the app has to accept an old and a new value during the
change-over, and database passwords need a rotation strategy that running connection pools survive.
Record the chosen strategy in an ADR.

- **files**:
  - docs/adr/00NN-secret-rotation.md
  - apps/api/aip/modules/identity/preauth_cookie.py (key list)
  - apps/api/aip/modules/identity/settings.py
  - apps/api/aip/platform/db/engine.py (re-read credentials on new connections, if the ADR picks that)
  - apps/api/tests/platform/test_secret_rotation.py
- **steps**:
  - 1. ADR: list every secret (`aip_app`, `aip_jobs`, `aip_owner`, Keycloak DB, OIDC client secrets,
    `PREAUTH_COOKIE_KEY`, session signing keys, SES SMTP credentials, Redis AUTH) with its rotation
    method. Decide between (a) Secrets Manager's alternating-users rotation for database roles, and
    (b) single-user rotation followed by an ECS forced redeploy; and whether the app reads the secret
    at connect time instead of from the environment.
  - 2. `PREAUTH_COOKIE_KEY` becomes a list: sign with the first key, verify with any of them (same
    shape as `API_TOKEN_SIGNING_KEYS` in IDENTITY-06).
  - 3. OIDC client secret: the backend retries the token exchange with the previous secret once on
    `invalid_client` during the overlap window.
  - 4. Database: implement the ADR's choice so that existing pooled connections keep working and new
    ones use the new password.
- **acceptance**:
  - A cookie signed with the old key verifies after rotation; one signed with neither key is rejected.
  - Rotating `aip_app`'s password mid-load causes no 5xx in the API.
- **tests**:
  - **unit**:
    - Cookie signed with key 2 of `[k1, k2]` verifies; signing always uses `k1`.
  - **integration**:
    - Testcontainers Postgres: change `aip_app`'s password while the pool holds connections, then open a
      new session. Expected: queries succeed before and after.
