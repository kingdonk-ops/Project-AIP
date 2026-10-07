# STACK-05 — Platform version endpoint and docker-compose stack

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Provide a reproducible local stack and a version endpoint for evidence.

- **depends on**:
  - STACK-02
- **files**:
  - docker-compose.yml
  - apps/api/src/platform/version/version.controller.ts
  - apps/api/Dockerfile
  - apps/worker/Dockerfile
  - services/sidecar/Dockerfile
- **steps**:
  - 1. Compose services: api, worker, sidecar, postgres (PostGIS, ltree, pgvector), redis, rustfs, gotenberg and keycloak.
  - 2. Run the containers non-root with read-only root filesystems where possible.
  - 3. Add GET /api/v1/platform/version returning build, commit and the key dependency versions.
  - 4. Add health checks to every service.
  - 5. Document the environment variables in .env.example, with no secrets.
- **acceptance**:
  - docker compose up reaches a healthy state within 3 minutes.
  - The version endpoint matches the commit SHA.
  - No container runs as root.
- **tests**:
  - **e2e**:
    - curl /api/v1/platform/version. Expected: 200 with fields build, commit and dependencies.node starting with '22'.
  - **integration**:
    - docker compose up --wait. Expected: all services healthy.
    - docker compose exec api id -u. Expected: non-zero.
  - **unit**:
    - The version controller returns commit from the GIT_SHA env value.
