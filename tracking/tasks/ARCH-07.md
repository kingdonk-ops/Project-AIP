# ARCH-07 — Outbox dispatcher, retries and dead-letter

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-06 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Deliver events to subscribers reliably from the worker.

- **depends on**:
  - ARCH-06
- **files**:
  - apps/worker/src/dispatcher.ts
  - apps/worker/src/dispatcher.spec.ts
  - apps/api/src/platform/events/subscribers.ts
  - apps/api/src/platform/events/dead-letter.controller.ts
- **steps**:
  - 1. Poll with SELECT ... FOR UPDATE SKIP LOCKED over unpublished, non-dead-lettered rows, with configurable batch size and interval.
  - 2. Run each subscriber inside runWithContext for the event's tenant. Subscribers must be idempotent, keyed on event id.
  - 3. On success set published_at. On failure increment attempts and last_error, with exponential backoff. At the max attempts set dead_lettered_at.
  - 4. Add dead-letter endpoints: list, retry (clears dead_lettered_at and attempts) and discard with a mandatory reason.
  - 5. Emit an alert event when the dead-letter count exceeds the threshold setting.
- **acceptance**:
  - Two dispatchers running at once never process the same event twice.
  - A failing subscriber does not block other events.
  - Retry from the dead-letter queue redelivers once.
- **tests**:
  - **e2e**:
    - Break the timeline subscriber and sign off an inspection. Expected: after retries the event appears in /admin/platform/events/dead-letter. Fix the subscriber and click Retry. Expected: the event leaves the queue and the timeline shows the entry.
  - **integration**:
    - Insert 100 events and start 2 dispatchers. Expected: each event's subscriber is invoked exactly once (100 total).
    - The subscriber throws on event X. Expected: X attempts=1 and last_error is set, and the other 99 are published.
    - Retry a dead-lettered event whose subscriber now succeeds. Expected: published_at is set.
  - **unit**:
    - Backoff for attempts 1, 2 and 3 with base 2s returns 2s, 4s and 8s.
    - Attempt 5 with max 5 marks the event dead-lettered.
