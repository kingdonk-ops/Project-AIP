# ADR 0003: Procrastinate (Postgres) for jobs; Postgres outbox; sandboxed Python workers

- **Status:** accepted; **owner to confirm**. The owner's decision text said "Redis queue (arq or Celery)". The stack review recommends a
  Postgres-backed queue so that jobs are enqueued in the same transaction as the data change.
- **Date:** 2026-10-07 (revised for the Python backend; the first version chose BullMQ)
- **Affects:** ops, arch; ARCH-05..07, OPS-01..03, TENANCY-02, STACK-02, STACK-05, UPLOADS-02, AUDIT-03

## Decision

- **Jobs: Procrastinate** (Postgres-backed, asyncio).
  - **Atomic enqueue:** jobs are enqueued inside the same `with_tenant` transaction as the domain change, so both commit or neither does.
  - **One state store:** job state lives in Postgres, so backups and point-in-time recovery cover it.
  - **Payloads:** every payload carries `tenant_id`, and handlers re-enter `with_tenant`.
- **Queues per job class** (`default`, `pdf`, `scan`, `import`, `outbox`), not per tenant.
  - Per-tenant fairness comes from a concurrency cap checked when a job is taken (a custom lock).
  - Gotenberg and sandbox work run in separate worker processes.
- **Domain events:** the transactional outbox table `domain_events` is the system of record for audit, timeline and replay.
  - A dispatcher job reads it with `FOR UPDATE SKIP LOCKED` and fans out to subscribers.
  - Retries and dead letters are recorded in Postgres.
- **Redis** is kept only for cache, rate limits, the session cache and SSE pub/sub. It is never used for durable work.
- **Sandboxed workers:** `apps/sandbox/` holds hardened Python images for IFC, OCR, PDF signing and image processing.
  - **Restrictions:** no network egress, non-root, read-only filesystem, CPU, memory and time caps.
  - **Invocation:** a Procrastinate job runs them as one-shot containers (ECS RunTask; `docker run` in dev), passing files by S3 key.
  - **Shared code:** they use the same Python codebase as the API.
- **Tripwire:** if queue load passes about 15% of database CPU, or about 200 jobs per second, move transport to SQS and keep the outbox.

## Consequences

OPS-02 becomes "Procrastinate worker and handler registry". There is no Redis durability or backup story to certify.
