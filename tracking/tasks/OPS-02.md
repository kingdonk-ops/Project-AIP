# OPS-02 — arq runner and handler registry

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Run jobs through arq with time and memory limits and tenant-scoped queues, with state in Postgres.

- **depends on**:
  - OPS-01
- **files**:
  - backend/app/modules/ops/jobs/runner.py
  - backend/app/modules/ops/jobs/registry.py
  - backend/tests/ops/test_runner.py
- **steps**:
  - 1. Implement register(job_type, handler, timeout, max_attempts).
  - 2. Implement a worker task wrapper that loads the job, checks status is queued, sets tenant context, runs the handler under asyncio.timeout, and writes the result or error.
  - 3. Name queues aip:{tenant_id}:jobs.
  - 4. Apply retry with backoff per type.
  - 5. Set a memory limit via the container, and check RSS in the wrapper.
  - 6. Make the wrapper idempotent: a succeeded job is skipped on redelivery.
- **acceptance**:
  - A handler over its timeout is marked failed with the error 'timeout'.
  - Redelivery does not re-run a succeeded job.
  - A tenant's payload cannot be read by another tenant's worker context.
- **tests**:
  - **e2e**:
    - Enqueue an export job and it completes with a result_ref.
  - **integration**:
    - Handler sleeps 5s with timeout 1s: status failed, error contains timeout.
    - Enqueue the same job id twice: the handler is called once.
    - Handler raising an exception: attempts increments, then failed after max_attempts.
  - **unit**:
    - register for an unknown type raises on enqueue.
    - Backoff for attempt 3 is greater than for attempt 1.
