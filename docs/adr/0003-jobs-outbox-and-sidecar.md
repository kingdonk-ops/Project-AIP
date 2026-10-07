# ADR 0003: BullMQ for jobs, Postgres outbox for events, HTTP contract for the sidecar

- **Status:** accepted (supersedes "Redis queue (arq or Celery)"; matches the brief's BullMQ)
- **Date:** 2026-10-07
- **Affects:** ops, arch; ARCH-05..07, OPS-01..03, TENANCY-02, STACK-02, STACK-05

## Decision

- **Queue: BullMQ on Redis**, consumed by `apps/worker`. Postgres `jobs` tables (OPS-01) hold the
  state of record. BullMQ is only the transport.
- **Queues per job class** (`pdf`, `import`, `notify`, `outbox`, ...), **not per tenant**. Fairness comes from
  per-tenant concurrency and rate caps. Every payload carries `tenant_id`, and handlers re-enter `withTenant`.
- **Domain events:** transactional outbox `domain_events`, written in the same transaction as the change.
  The dispatcher polls with `FOR UPDATE SKIP LOCKED` and enqueues with `jobId = event_id` (idempotent).
  Retries and dead letters are recorded in Postgres. This closes the open question in `modules/arch/README.md`.
- **Sidecar:** `services/sidecar` (Python, uv, FastAPI) uses an async job-id HTTP API, called only
  from BullMQ jobs. JSON Schemas are generated from `packages/contracts`, with contract tests in CI. It runs
  with no egress, non-root, on a read-only filesystem.
- Gotenberg and sidecar work run in separate worker pools.

## Consequences

OPS-02 becomes "BullMQ runner and handler registry". No arq, no Celery.
