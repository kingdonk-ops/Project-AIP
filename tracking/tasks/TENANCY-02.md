# TENANCY-02 — Tenant-scoped key builders for Redis, queues, S3 and search

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Prevent workers and caches from becoming a cross-tenant leak path.

- **depends on**:
  - TENANCY-01
  - ARCH-04
- **files**:
  - apps/api/src/modules/tenancy/keys.ts
  - apps/api/src/modules/tenancy/keys.spec.ts
  - tools/ci/check-raw-keys.ts
- **steps**:
  - 1. Implement redisKey(tenantId, ...parts), queueName(tenantId, name), s3Key(tenantId, ...parts), searchIndex(tenantId, name) and embeddingNamespace(tenantId).
  - 2. Reject empty tenant ids and parts containing ':' or '..'.
  - 3. Replace direct Redis and S3 key construction in existing code with the builders.
  - 4. Add a lint check that flags raw redis.get('...') string literals and raw S3 key strings outside keys.ts.
  - 5. Make BullMQ job payloads carry tenantId and make the worker wrap each job in runWithContext.
- **acceptance**:
  - No cache, queue, S3 or search call builds a key without a tenant prefix.
  - A job without tenantId is rejected.
  - The lint check fails on a raw key.
- **tests**:
  - **e2e**:
    - Upload a file as tenant A and request its URL as tenant B. Expected: 404 or 403 and no bytes returned.
  - **integration**:
    - Write a cache value as A and read the same logical key as B. Expected: a miss.
    - Enqueue a job without tenantId. Expected: rejected and moved to failed with reason 'missing tenant'.
    - Put an object for tenant A, then attempt get with B's builder. Expected: 404.
  - **unit**:
    - redisKey('t1','asset','42') returns 'tenant:t1:asset:42'.
    - s3Key('t1','..','x') throws.
    - redisKey('', 'x') throws.
