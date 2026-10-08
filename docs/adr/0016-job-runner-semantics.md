# ADR 0016: Job runner semantics on Procrastinate (queue schema, locks, tries, privileges)

- **Status:** accepted (builds on ADR 0003; no owner decision reversed)
- **Date:** 2026-10-08
- **Affects:** ops; OPS-02, OPS-03, TENANCY-02, UPLOADS-02, AUDIT-03

## Context

ADR 0003 chose Procrastinate with atomic enqueue, queues per job class and a per-tenant concurrency
cap "checked when a job is taken (a custom lock)". OPS-02 had to turn that into concrete rules:
where the queue tables live and who may touch them, how the cap is enforced, and what "attempts"
means. The task text still said arq; it is translated per ADR 0001 and 0003.

## Decision

- **Queue schema.** Procrastinate's `schema.sql` (MIT, 3.10.x) is applied unchanged except for its
  leading plpgsql `DO` block (the migration lint forbids `DO` outside the baseline; the owner
  approved removing it). A fail-closed `SELECT 1 / count(*) ... 'plpgsql'` statement replaces it. A
  test pins the removed text and the equality of the migration copy with the installed library, so
  upgrading Procrastinate needs a new reviewed migration. The `procrastinate_*` tables live in
  `public`, owned by `aip_owner`, and are infrastructure, not tenant tables: they hold ids only (no
  payloads) and have no `tenant_id`/RLS. `aip-db check-schema` ignores them.
- **Privileges.** `aip_jobs` has full access to the queue tables. `aip_app` may only `INSERT` (plus
  `SELECT` of the `id` column and the id sequences), which is what `procrastinate_defer_jobs_v1`
  needs, so a compromised API session cannot read other tenants' job identifiers or alter the queue.
- **Atomic enqueue.** `enqueue` calls `procrastinate_defer_jobs_v1` on the caller's `with_tenant`
  connection. Procrastinate's `Task.defer` (a second connection) is never used by the API.
- **Fairness.** A Procrastinate lock allows one running job per lock string. A job gets lock
  `tenant:<id>:job:<type>:<slot>` where `slot = (tenant's job count for the type - 1) % max_per_tenant`,
  so a tenant runs at most `max_per_tenant` jobs of a type at once while other tenants' jobs (other
  locks) are unaffected. (TENANCY-02's `job_lock` replaces the local helper once merged.)
- **Tries.** `max_attempts` is the total number of tries (1 = no retry), unlike Procrastinate's
  `RetryStrategy.max_attempts`, which counts retries. `JobRetryStrategy` adapts it; backoff is
  `retry_backoff_s ** try`. A job stays `running` between tries (the OPS-01 state machine has no
  `running -> queued`); each try appends a `running -> running` event. `jobs.attempts` is the
  authority: a job found with more tries than allowed (worker crashes) is failed, not run.
- **Handlers.** Called as `handler(conn, job) -> result_ref | None` inside `with_tenant(job.tenant_id)`
  on the `aip_jobs` engine; the `succeeded` status commits in the same transaction as the handler's
  writes. Handlers must be idempotent (external effects are not rolled back).
- **Worker connections.** The Procrastinate pool (psycopg) and the `aip_jobs` SQLAlchemy engine both
  use `DATABASE_JOBS_URL`. The psycopg pool is created in `aip.platform.jobs.app`, because
  Procrastinate owns that connection; the engine boundary test still holds (no raw driver
  connect calls).
- **Licences.** Procrastinate is MIT, but it requires `psycopg` and `psycopg-pool` (LGPL-3.0-only),
  which the policy only lets through in sandbox image SBOMs. Per ADR 0011 (free licences are fine),
  `config/licence-policy.json` gets two named `exceptions` (expiring 2027-04-06) for these two
  packages, imported unmodified, not vendored or patched. `allow`/`deny` and the general LGPL rule
  are unchanged. The owner is asked to confirm them in `tracking/OPEN-QUESTIONS.md`.

## Consequences

Later job types only call `ops.register(...)` in their module's `jobs.py`. OPS-03 (jobs API) reads
`jobs`/`job_events`, not the queue. Moving transport to SQS (the ADR 0003 tripwire) replaces
`aip.platform.jobs.app` and `enqueue` but not handlers or the `jobs` record.
