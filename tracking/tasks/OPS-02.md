# OPS-02 — Procrastinate worker and handler registry
<!-- hand-edited: arq replaced by Procrastinate per ADR 0003 -->

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
3. ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Procrastinate, atomic enqueue, queues per job class, per-tenant concurrency cap, no Redis for durable work), [0001](../../docs/adr/0001-greenfield-python-backend.md), [0002](../../docs/adr/0002-data-access-and-migrations.md) (`aip_jobs` role, `with_tenant`), [0004](../../docs/adr/0004-repository-layout.md) (`aip/worker.py`, `aip/platform/jobs`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Run jobs through Procrastinate (Postgres-backed, asyncio) with timeouts, memory checks, retries and per-tenant fairness, keeping user-visible state in the OPS-01 `jobs` table. Jobs are enqueued in the same `with_tenant` transaction as the domain change.

- **depends on**:
  - OPS-01
- **files**:
  - apps/api/aip/platform/jobs/app.py (Procrastinate `App` and connector; queue names)
  - apps/api/migrations/versions/<rev>_procrastinate_schema.py (applies Procrastinate's schema SQL as `aip_owner`; grants to `aip_jobs`)
  - apps/api/aip/modules/ops/registry.py
  - apps/api/aip/modules/ops/runner.py
  - apps/api/aip/modules/ops/api.py (export `register`, `enqueue`)
  - apps/api/aip/worker.py (entrypoint: imports every module's `jobs.py`, runs the worker for `--queues`)
  - apps/api/aip/modules/ops/tests/test_runner.py
- **steps**:
  - 1. `register(job_type, handler, *, queue="default", timeout_s, max_attempts, max_per_tenant=2)` stores a `JobSpec` and declares a Procrastinate task named `job_type` with `RetryStrategy(max_attempts=max_attempts, exponential_wait=...)`. Queues are per job class only: `default`, `pdf`, `scan`, `import`, `outbox`. `enqueue` of an unregistered type raises `UnknownJobType`.
  - 2. `enqueue(conn, job_type, payload, *, idempotency_key=None)` runs inside the caller's `with_tenant` transaction: it calls OPS-01 `create_job`, then defers the Procrastinate job on the same connection/transaction (call Procrastinate's defer SQL function through the tenant-bound connection, or a connector bound to that transaction), so a rollback leaves neither row. The payload is `{"job_id", "tenant_id", ...}`; `tenant_id` is mandatory (TENANCY-02 `tenant_guard`, if merged).
  - 3. The runner wrapper loads the `jobs` row, skips if status is already terminal (idempotent redelivery), transitions to `running`, enters `with_tenant(payload.tenant_id)` and the request context, runs the handler under `asyncio.timeout(timeout_s)`, then writes `succeeded` with `result_ref` or `failed` with the error text (`timeout` on `TimeoutError`). It increments `attempts` on each try and only marks `failed` after `max_attempts`.
  - 4. Per-tenant fairness: a concurrency cap of `max_per_tenant` running jobs per `(tenant_id, job_type)`, enforced at take time via a Procrastinate `lock` built with `job_lock(tenant_id, job_type, slot)` (TENANCY-02; if not merged, use format `tenant:<id>:job:<type>:<slot>` and flag it in the PR). Gotenberg and sandbox work use their own queues and worker processes.
  - 5. Memory: the ECS task/compose service sets the hard limit; the wrapper also reads RSS (`resource.getrusage(RUSAGE_SELF).ru_maxrss`) after each job and logs a warning above 80% of `WORKER_MEMORY_LIMIT_MB`, exiting the worker gracefully above 95% so the orchestrator restarts it.
  - 6. `aip/worker.py` (`uv run python -m aip.worker --queues default,outbox`) connects as `aip_jobs`, and handles SIGTERM by finishing in-flight jobs. Add a `worker` service to `infra/docker-compose.yml` if STACK-05 has not.
- **acceptance**:
  - A handler over its timeout is marked `failed` with error `timeout`.
  - Redelivery does not re-run a succeeded job.
  - A handler only ever sees its own tenant's rows (it runs inside `with_tenant(payload.tenant_id)`).
  - A rolled-back transaction leaves no `jobs` row and no Procrastinate job.
  - No job state or queue lives in Redis.
- **tests**:
  - **e2e**:
    - Through the API (compose stack), trigger a fixture `export` job. Expected: it completes with a `result_ref` and status `succeeded`.
  - **integration** (pytest + testcontainers-python, real Postgres with the Procrastinate schema; worker run in-process with `run_worker_async(wait=False)`):
    - Handler sleeps 5 s with timeout 1 s. Expected: status `failed`, error contains `timeout`.
    - Deliver the same Procrastinate job for an already `succeeded` job id twice. Expected: the handler is called once.
    - Handler raising an exception with `max_attempts=3`. Expected: `attempts` reaches 3, then status `failed`.
    - `enqueue` inside `with_tenant(A)` and then raise before commit. Expected: 0 rows in `jobs` and in `procrastinate_jobs`.
    - Enqueue 5 jobs for tenant A and 1 for tenant B with `max_per_tenant=2` and worker concurrency 3. Expected: B's job starts before A's third job finishes.
  - **unit**:
    - `enqueue` for an unregistered type raises `UnknownJobType`.
    - The retry wait for attempt 3 is greater than for attempt 1.
