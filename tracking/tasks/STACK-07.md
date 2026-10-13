# STACK-07 — TLS to Postgres and Redis (RDS and ElastiCache ready)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`stack`](../../docs/blueprint/modules/stack/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | STACK-05, OPS-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/stack/README.md`](../../docs/blueprint/modules/stack/README.md)
3. ADRs: 0002 (database roles), 0003 (Redis is cache only)
4. `apps/api/aip/platform/db/engine.py`, `apps/api/aip/platform/jobs/app.py`, `apps/api/aip/modules/ops/health.py`

## Spec

Make every database and Redis connection able to require and verify TLS, configured the same way for
all clients, so the stack runs unchanged against Amazon RDS (`verify-full` with the RDS CA bundle) and
Amazon ElastiCache (in-transit encryption plus an AUTH token), and in plain text on Coolify and in dev.

- **files**:
  - apps/api/aip/platform/db/engine.py
  - apps/api/aip/platform/jobs/app.py
  - apps/api/aip/platform/version/routes.py
  - apps/api/aip/modules/ops/health.py
  - apps/api/aip/modules/identity/service.py
  - apps/api/Dockerfile (ship the RDS CA bundle)
  - apps/api/tests/platform/db/test_tls.py
- **steps**:
  - 1. One setting pair, `DB_SSLMODE` (`disable|require|verify-full`, default `disable` in dev) and
    `DB_SSLROOTCERT`, applied to asyncpg (API, version route) and psycopg (Procrastinate worker), so the
    two drivers never disagree about URL query syntax.
  - 2. `AIP_ENV=production` refuses to start with `DB_SSLMODE` other than `verify-full`.
  - 3. Redis: every client (rate limiter, health check, later the session cache) accepts `rediss://`
    with a password and `REDIS_SSL_CA_CERTS`; production refuses plain `redis://`.
  - 4. Add the Amazon RDS global CA bundle to the API image at a fixed path.
- **acceptance**:
  - API, worker and migrator connect to a Postgres that only accepts TLS, with `verify-full`.
  - The health check stays green against a TLS-only Valkey with AUTH.
  - Production with `DB_SSLMODE=disable` or `redis://` exits at startup with a clear error.
- **tests**:
  - **unit**:
    - `AIP_ENV=production` plus `DB_SSLMODE=require` raises.
    - The asyncpg and psycopg connection arguments built from the same settings both ask for `verify-full`.
  - **integration**:
    - Testcontainers Postgres with `ssl=on` and `hostssl`-only `pg_hba`: the engine and the worker connect.
    - Testcontainers Valkey with `--tls-port` and `--requirepass`: `/api/v1/health/ready` reports redis ok.
