# OPS-04 — Health endpoints and structured logging with PII scrubber

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Provide liveness/readiness and JSON logs carrying tenant_id and request id without PII.

- **files**:
  - backend/app/modules/ops/health.py
  - backend/app/modules/ops/observability.py
  - backend/tests/ops/test_observability.py
- **steps**:
  - 1. GET /health/live returns 200 always.
  - 2. GET /health/ready checks DB, Redis and migrations head, and returns 503 on any failure.
  - 3. Add logging middleware setting a request_id contextvar.
  - 4. Emit JSON logs with tenant_id and request_id.
  - 5. Add a scrubber redacting emails, bearer tokens and fields named password, token or pin.
  - 6. Initialise OpenTelemetry with an OTLP exporter set from the environment.
- **acceptance**:
  - Ready returns 503 when Redis is down.
  - No log line contains a raw email or token.
  - Every log line carries a request_id.
- **tests**:
  - **e2e**:
    - The ECS-style health probe against docker-compose passes after startup.
  - **integration**:
    - Stop the Redis container: /health/ready returns 503 with the failing check named; /health/live returns 200.
    - A request logs a JSON line with request_id and tenant_id, and a header X-Request-ID is returned.
  - **unit**:
    - scrub('user a@b.com token=abc') contains neither a@b.com nor abc.
    - scrub of a dict masks the key 'pin'.
