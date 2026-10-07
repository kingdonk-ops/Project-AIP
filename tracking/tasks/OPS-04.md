# OPS-04 — Health endpoints and structured logging with PII scrubber
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (FastAPI), [0002](../../docs/adr/0002-data-access-and-migrations.md) (Alembic head check), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Redis is cache/session/pubsub only), [0004](../../docs/adr/0004-repository-layout.md) (`aip/platform`, `infra/docker-compose.yml`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Provide liveness and readiness endpoints and JSON logs carrying `tenant_id` and `request_id` without PII, plus OpenTelemetry tracing.

- **files**:
  - apps/api/aip/modules/ops/health.py (router mounted at `/api/v1/health`)
  - apps/api/aip/platform/observability/logging.py (structlog JSON config, request-id middleware)
  - apps/api/aip/platform/observability/scrub.py
  - apps/api/aip/platform/observability/otel.py
  - apps/api/aip/main.py (register middleware and router)
  - apps/api/aip/modules/ops/tests/test_observability.py
- **steps**:
  - 1. `GET /api/v1/health/live` returns 200 `{"status":"ok"}` always, without touching dependencies.
  - 2. `GET /api/v1/health/ready` checks Postgres (`select 1` as `aip_app`), Redis (`PING`) and that the database's `alembic_version` equals the `ScriptDirectory` head; each check has a 2 s timeout; any failure returns 503 `{"status":"fail","checks":{"db":"ok","redis":"fail: ...","migrations":"ok"}}`. Both routes are unauthenticated and not tenant-scoped.
  - 3. Add a pure ASGI middleware that reads `X-Request-ID` (or generates a UUIDv7), stores it in a `contextvars.ContextVar`, binds it to structlog context, and returns it in the `X-Request-ID` response header.
  - 4. Emit JSON logs with structlog (`JSONRenderer`), routing stdlib/uvicorn logging through it; every line carries `request_id` and, when set, `tenant_id` from the request context.
  - 5. `scrub(value)` redacts email addresses, `Bearer ...` tokens, `token=`/`password=` query pairs, and dict keys named `password`, `token`, `pin`, `secret` or `authorization` (case-insensitive, recursive); register it as a structlog processor before rendering.
  - 6. Initialise OpenTelemetry (`opentelemetry-sdk`, OTLP exporter, `opentelemetry-instrumentation-fastapi`, `-sqlalchemy`, `-redis`) from `OTEL_EXPORTER_OTLP_ENDPOINT`; a no-op when unset.
- **acceptance**:
  - Ready returns 503 when Redis is down, naming the failing check.
  - No log line contains a raw email or token.
  - Every request log line carries a `request_id`.
- **tests**:
  - **e2e**:
    - With `docker compose -f infra/docker-compose.yml up --wait`, the compose healthcheck (`curl -f http://localhost:8000/api/v1/health/ready`) passes after startup (same probe ECS uses).
  - **integration** (pytest + testcontainers-python Postgres and Redis, httpx `AsyncClient`):
    - Stop the Redis container. Expected: `/api/v1/health/ready` returns 503 with `checks.redis` starting `fail`; `/api/v1/health/live` returns 200.
    - Run migrations to head minus one. Expected: ready returns 503 with `checks.migrations` failing.
    - A request logs a JSON line (captured with `capsys`/structlog testing) containing `request_id` and `tenant_id`, and the response has header `X-Request-ID` equal to that id.
  - **unit**:
    - `scrub("user a@b.com token=abc")` contains neither `a@b.com` nor `abc`.
    - `scrub({"pin": "1234", "nested": {"Password": "x"}})` masks both values.
