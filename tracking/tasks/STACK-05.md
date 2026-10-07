# STACK-05 — Platform version endpoint and docker-compose stack
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`stack`](../../docs/blueprint/modules/stack/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | STACK-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/stack/README.md`](../../docs/blueprint/modules/stack/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`infra/docker-compose.yml`, `apps/sandbox/`), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (worker process, sandbox constraints), [0002](../../docs/adr/0002-data-access-and-migrations.md) (Postgres 16 extensions, migrator role), [0005](../../docs/adr/0005-identity-architecture.md) (Keycloak as broker), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md) (LocalStack KMS in dev)

## Spec

Provide a reproducible local stack and a version endpoint for evidence.

- **depends on**:
  - STACK-02
- **files**:
  - infra/docker-compose.yml
  - apps/api/Dockerfile (one image for API and worker; multi-stage with uv)
  - apps/sandbox/Dockerfile (hardened base image for the sandbox workers)
  - apps/api/aip/platform/version/routes.py
  - apps/api/tests/platform/version/test_version.py
  - .env.example
- **steps**:
  - 1. Compose services: `api` (`uvicorn aip.main:create_app --factory`), `worker` (same image, `procrastinate --app=aip.platform.jobs.app.app worker`, or a stub that exits 0 until OPS-02 lands), `migrator` (one-shot, from DATABASE-08 if present; `api` and `worker` wait on `service_completed_successfully`), `postgres` (`pgvector/pgvector:pg16`; ltree, pgcrypto, pg_trgm come with it; no PostGIS per ADR 0002), `redis` (cache, rate limits, SSE only), `rustfs`, `gotenberg`, `keycloak` (broker realm import placeholder), and `localstack` (S3 + KMS). The sandbox base image is built under a `sandbox` profile and is not a long-running service; dev runs it with `docker run --network none --read-only --user 10001` per job.
  - 2. All app images run as a non-root UID (10001) with `read_only: true` and a `tmpfs` for `/tmp`; drop all capabilities.
  - 3. `GET /api/v1/platform/version` returns `{build, commit, dependencies: {python, fastapi, pydantic, sqlalchemy, alembic, procrastinate, postgres}}`: `build` and `commit` from `BUILD_ID` / `GIT_SHA` (baked in as image labels and env at build time), library versions from `importlib.metadata`, `python` from `platform.python_version()`, and `postgres` from `SHOW server_version` (omitted with `"unavailable"` if the DB is down).
  - 4. Health checks on every service (`/api/v1/health` for `api`, `pg_isready`, `redis-cli ping`, Gotenberg `/health`, Keycloak `/health/ready`, LocalStack `/_localstack/health`, RustFS readiness).
  - 5. Document every environment variable in `.env.example` with placeholder values only (no secrets), including `DATABASE_URL`, `DATABASE_MIGRATOR_URL`, `DATABASE_JOBS_URL`, `OBJECT_STORE`, `PDF_RENDERER`, `GIT_SHA`.
- **acceptance**:
  - `docker compose -f infra/docker-compose.yml up --wait` reaches a healthy state within 3 minutes.
  - The version endpoint's `commit` matches the built commit SHA.
  - No container runs as root.
- **tests**:
  - **unit**:
    - With `GIT_SHA=abc123`, the version route (via `httpx.AsyncClient` on `create_app()`) returns `commit == "abc123"` and `dependencies.python` starting with `3.12`.
    - With the DB unreachable, `dependencies.postgres == "unavailable"` and the status is still 200.
  - **integration**:
    - `docker compose -f infra/docker-compose.yml up --wait` (CI, timeout 180 s). Expected: all services healthy and `migrator` exited 0.
    - `docker compose exec api id -u` and `docker compose exec worker id -u`. Expected: `10001`.
    - `docker run --rm --network none <sandbox image> id -u`. Expected: non-zero.
  - **e2e**:
    - `curl localhost:8000/api/v1/platform/version`. Expected: 200 with fields `build`, `commit`, `dependencies.python` starting with `3.12` and `dependencies.postgres` starting with `16`.
