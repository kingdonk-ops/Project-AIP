# ARCH-07 — Outbox dispatcher, retries and dead-letter
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-06 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md) (dispatcher settings)
3. ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Procrastinate, `outbox` queue, dispatcher job with SKIP LOCKED), [0002](../../docs/adr/0002-data-access-and-migrations.md) (`aip_jobs` role, `with_tenant`)

## Spec

Deliver outbox events to subscribers reliably from a Procrastinate job on the `outbox` queue, with backoff, dead-lettering and an operator retry/discard path.

- **depends on**:
  - ARCH-06
- **files**:
  - apps/api/migrations/versions/<YYYYMMDDHHMM>_outbox_dispatch.py (adds `next_attempt_at`, `discarded_at`, `discarded_by`, `discard_reason`; dead-letter functions)
  - apps/api/aip/platform/events/subscribers.py (`@subscriber(event_name, version)` registry)
  - apps/api/aip/platform/events/dispatcher.py (`dispatch_batch`, backoff)
  - apps/api/aip/platform/events/jobs.py (Procrastinate periodic task `dispatch_outbox`, queue `outbox`)
  - apps/api/aip/platform/events/dead_letter_routes.py
  - apps/api/tests/platform/events/test_dispatcher.py
  - apps/api/tests/platform/events/test_dead_letter_routes.py
- **steps**:
  - 1. Migration: `ALTER TABLE domain_events ADD COLUMN next_attempt_at timestamptz, discarded_at timestamptz, discarded_by uuid, discard_reason text`; extend the `aip_jobs` column grant to `next_attempt_at`; replace the partial index with one on `(next_attempt_at NULLS FIRST, occurred_at) WHERE published_at IS NULL AND dead_lettered_at IS NULL`. Add `SECURITY DEFINER` functions owned by `aip_owner`, `EXECUTE` to `aip_app`: `outbox_dead_letters(lim int, after uuid)` (id, tenant_id, event_name, event_version, attempts, last_error, dead_lettered_at; never payload), `outbox_retry(event_id uuid)` (clears `dead_lettered_at`, `attempts`, `next_attempt_at`) and `outbox_discard(event_id uuid, reason text, actor uuid)` (requires a non-empty reason).
  - 2. Subscribers register with `@subscriber("widget.created", 1)` in a module's `events.py`; each must also be listed under `subscribes` in that module's manifest (boot fails otherwise). Handlers are `async def handler(conn, event) -> None` and must be idempotent on `event.id`.
  - 3. `dispatch_batch(batch_size)` runs as `aip_jobs`: in one transaction, `SELECT ... FROM domain_events WHERE published_at IS NULL AND dead_lettered_at IS NULL AND discarded_at IS NULL AND (next_attempt_at IS NULL OR next_attempt_at <= now()) ORDER BY occurred_at LIMIT :n FOR UPDATE SKIP LOCKED`. For each row, run every subscriber inside `use_context` + `with_tenant(event.tenant_id)` on an `aip_app` connection. On success set `published_at`; on failure increment `attempts`, set `last_error` and `next_attempt_at = now() + backoff(attempts)`; at `max_attempts` set `dead_lettered_at`. One subscriber failure never stops other rows.
  - 4. Register `dispatch_outbox` on the Procrastinate `App` in `aip/platform/jobs/app.py` (if OPS-02 has not created it yet, create only the `App` object with Procrastinate's `PsycopgConnector` (psycopg 3; the API itself stays on asyncpg) from `DATABASE_JOBS_URL`, role `aip_jobs`), queue `outbox`, periodic every `dispatcher_poll_interval_s` (default 2 s), draining batches until one returns fewer than `batch_size` rows.
  - 5. Dead-letter endpoints, permission `platform.events.manage`: `GET /api/v1/admin/platform/events/dead-letter`, `POST .../dead-letter/{event_id}/retry`, `POST .../dead-letter/{event_id}/discard` with body `{"reason": str}` (min length 1; 422 otherwise). Both actions emit an audit event (`platform.outbox.retried` / `platform.outbox.discarded`).
  - 6. After each run, for each tenant whose dead-letter count exceeds `dead_letter_alert_threshold` (default 10), emit `platform.outbox.dead_letter_threshold_exceeded {count, threshold}` into that tenant's outbox at most once per hour, and log a structured warning.
- **acceptance**:
  - Two dispatchers running at once never deliver the same event twice.
  - A failing subscriber does not block other events.
  - Retry from the dead-letter queue redelivers once.
  - Discard without a reason is rejected.
- **tests**:
  - **unit**:
    - `backoff(1)`, `backoff(2)`, `backoff(3)` with base 2 s return 2 s, 4 s and 8 s.
    - Failure at attempt 5 with `max_attempts=5` returns the "dead-letter" outcome.
  - **integration** (testcontainers-python):
    - Insert 100 `widget.created` events across 2 tenants and run two `dispatch_batch` loops concurrently with `asyncio.gather` on separate connections. Expected: the counting subscriber is invoked exactly once per event (100 total) and all 100 have `published_at`.
    - The subscriber raises on event X. Expected: X has `attempts=1`, `last_error` set and `next_attempt_at` ≈ now + 2 s; the other 99 are published.
    - Dead-letter event X, make the subscriber succeed, call `outbox_retry(X)` and run one batch. Expected: `published_at` set and the subscriber called once.
    - Run `dispatch_outbox` via Procrastinate's `InMemoryConnector`. Expected: the task is registered on queue `outbox` and drains a seeded batch.
  - **e2e**:
    - On the compose stack with the fixture `widgets` module and `FIXTURE_SUBSCRIBER_FAIL=1`: create a widget; after retries `GET /api/v1/admin/platform/events/dead-letter` lists the event. Restart with the flag off and `POST .../retry`. Expected: the event leaves the dead-letter list and the fixture subscriber's table has the entry.
