# TENANCY-02 — Tenant-scoped key builders for Redis cache, S3, search and Procrastinate jobs
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | TENANCY-01, ARCH-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Procrastinate queues per job class; payloads carry `tenant_id`; Redis is cache/rate-limit/session/pubsub only), [0004](../../docs/adr/0004-repository-layout.md) (`aip/platform` never imports modules), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md) (prefixes are the second isolation layer behind the per-tenant KMS key)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Prevent caches, object storage, search and background jobs from becoming a cross-tenant leak path. Queues are per job class, not per tenant (ADR 0003), so job isolation means a mandatory `tenant_id` in every payload, tenant-prefixed lock names, and handlers that re-enter `with_tenant`.

- **depends on**:
  - TENANCY-01
  - ARCH-04
- **files**:
  - apps/api/aip/platform/tenant_keys.py (in `platform`, because `platform/files` and `platform/jobs` use it and `platform` may not import `modules`)
  - apps/api/aip/platform/jobs/tenant_guard.py
  - apps/api/tests/platform/test_tenant_keys.py
  - tools/ci/check_raw_keys.py
  - tools/ci/tests/test_check_raw_keys.py
- **steps**:
  - 1. Implement `redis_key(tenant_id, *parts)` (cache, rate-limit and session-cache keys only), `pubsub_channel(tenant_id, name)`, `s3_key(tenant_id, *parts)` (prefix `tenants/<tenant_id>/`), `search_index(tenant_id, name)`, `embedding_namespace(tenant_id)`, and `job_lock(tenant_id, job_type, *parts)` / `job_queueing_lock(...)` for Procrastinate `lock` and `queueing_lock` values.
  - 2. Reject empty or non-uuid tenant ids and any part that is empty or contains `:`, `/`, `..` or whitespace, raising `TenantKeyError`.
  - 3. Replace any direct Redis, S3, search or job-lock key construction already on main with the builders (list the call sites changed in the PR; greenfield, so there may be none).
  - 4. `tools/ci/check_raw_keys.py` walks `apps/api/aip` with Python `ast` and flags: string literals or f-strings passed as the first argument to Redis client methods (`get`, `set`, `delete`, `incr`, `expire`, `publish`, …), literal `Key=`/`Prefix=` arguments to boto3 S3 calls, and literal `lock=`/`queueing_lock=` in `.configure(...)` / `.defer_async(...)`, outside `tenant_keys.py`. Exit 1 with `file:line: raw key`. Wire it into the CI lint job.
  - 5. `tenant_guard.py`: a `TenantJobPayload` Pydantic base model with required `tenant_id: UUID`, `defer_for_tenant(task, tenant_id, **kwargs)` that sets `tenant_id` and the tenant lock and raises `MissingTenantError` when absent, and `tenant_task` — a wrapper for Procrastinate task functions that validates the payload, fails the job with reason `missing tenant` when `tenant_id` is absent or invalid, and runs the handler inside `with_tenant(tenant_id)` plus the ARCH-04 request context. OPS-02's registry wraps every handler with it; if OPS-02 merged first, plug into its wrapper instead of adding a second one.
- **acceptance**:
  - No cache, S3, search or job-lock call builds a key without a tenant prefix (the CI check passes on main).
  - A job without `tenant_id` is rejected at defer time, and fails with `missing tenant` if it reaches a worker.
  - The CI check fails on a raw key literal.
- **tests**:
  - **e2e**:
    - Upload a file as tenant `kaefer-demo` and request its URL as `tenant-b` (once UPLOADS-01 is on main; until then covered by the S3 integration test). Expected: 404 or 403 and no bytes returned.
  - **integration** (pytest + testcontainers-python: Redis, Postgres with Procrastinate schema applied, LocalStack S3):
    - Write a cache value as A with `redis_key(A, "asset", "42")` and read the same logical key as B. Expected: a miss.
    - Defer a `tenant_task` job via Procrastinate directly with no `tenant_id`, then run the worker once (`run_worker_async(wait=False)`). Expected: the job ends `failed` and the log record carries reason `missing tenant`; the handler body never runs.
    - Put an object at `s3_key(A, "docs", "x.pdf")`, then attempt `get_object` at `s3_key(B, "docs", "x.pdf")`. Expected: 404 (`NoSuchKey`).
    - A `tenant_task` handler that runs `SELECT count(*) FROM rls_probe` for a tenant-B payload sees only B's rows.
  - **unit**:
    - `redis_key("00000000-0000-7000-8000-000000000001", "asset", "42")` returns `"tenant:00000000-0000-7000-8000-000000000001:asset:42"`.
    - `s3_key(t1, "..", "x")` raises `TenantKeyError`.
    - `redis_key("", "x")` raises `TenantKeyError`.
    - `check_raw_keys` on a fixture file containing `redis.get("user:1")` reports 1 finding; on `redis.get(redis_key(t, "user", "1"))` reports 0.
