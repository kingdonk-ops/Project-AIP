# TESTING-03 — Isolation tests for Redis, queues, S3 prefixes and search

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TESTING-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Prove that caches, queues, object storage and search never cross tenants.

- **depends on**:
  - TESTING-01
- **files**:
  - backend/tests/tenancy/test_isolation_infra.py
  - backend/tests/conftest_infra.py
- **steps**:
  - 1. Add Redis and MinIO Testcontainers.
  - 2. Test the cache key builder: every key must start with t:{tenant_id}:.
  - 3. Enqueue a job as tenant A and assert the queue name and payload carry tenant A only.
  - 4. Write an S3 object as A and assert that a B-scoped storage client gets AccessDenied or NotFound for A's key, including keys with ../ traversal.
  - 5. Query FTS and pgvector as B and assert A's rows are never returned.
  - 6. Mark tests that depend on unbuilt modules xfail(strict=True) with a reason.
- **acceptance**:
  - Each of the four surfaces has at least one cross-tenant negative test.
  - Failures are tagged critical for notification.
- **tests**:
  - **e2e**:
    - API call as a B user to /documents/{A's id} returns 404.
  - **integration**:
    - Set a cache value as A; B reading the same logical key gets a miss.
    - Put s3://bucket/tenants/A/doc.pdf; a B client requesting tenants/A/doc.pdf is denied; tenants/B/../A/doc.pdf is also denied.
    - Insert a document embedding for A; B's nearest-neighbour search returns an empty list.
  - **unit**:
    - cache_key('abc','x') returns 't:abc:x'.
    - cache_key with an empty tenant raises ValueError.
