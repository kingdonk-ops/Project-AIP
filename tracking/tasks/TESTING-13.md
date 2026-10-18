# TESTING-13 — Stack proves the worker and the workflow transition journeys

<!-- hand-edited: merged APPROVALS-07 (Part B) per board slim 2026-10-18 -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | APPROVALS-02, AUDIT-02, TESTING-09 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. ADRs: 0030
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

Part B (was APPROVALS-07) also reads:

- [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
- ADRs: [0035](../../docs/adr/0035-transition-service-implementation.md) (why these journeys were
   carried forward), [0034](../../docs/adr/0034-invites-and-step-up-implementation.md)
- `tracking/tasks/APPROVALS-02.md`, the two **e2e** blocks

> Part A (was TESTING-13) and Part B (was APPROVALS-07) both extend the compose stack's `e2e-skeleton` lane after TESTING-09 (fixture seed, journeys, outbox and audit assertions), so they are one change to the same lane.

## Part A — Stack proves the worker (was TESTING-13)

### Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M10**. The worker healthcheck is `python -c "import aip"` (`infra/docker-compose.yml:399-403`,
same in Coolify). `tools/smoke.py` and `walking-skeleton.spec.ts` never check that `project.created` is published or
audited. The CI e2e log tail omits `worker` (`ci.yml:466`). A crash-looping worker, a wrong
`DATABASE_AUDIT_WRITER_URL` or a dispatcher that never drains all ship green.

### Spec

CI and the demo fail when the worker or outbox is not working.

- **files**:
  - infra/docker-compose.yml
  - infra/coolify/docker-compose.coolify.yml
  - apps/api/aip/worker.py
  - tools/smoke.py
  - e2e/web/walking-skeleton.spec.ts
  - .github/workflows/ci.yml
- **steps**:
  - 1. Make the worker healthcheck real (a heartbeat the worker writes and the check reads).
  - 2. After the skeleton e2e, assert the `project.created` event has `published_at` set and an `audit_log` row exists.
  - 3. Add an outbox-lag smoke check.
  - 4. Include `worker` in the CI e2e log tail.
- **acceptance**:
  - A worker that cannot reach the audit writer is unhealthy.
  - The skeleton lane fails if the outbox does not drain.
- **tests**:
  - **integration**:
    - worker with a bad audit-writer URL → healthcheck fails
  - **e2e**:
    - create a project in the skeleton → event published and audited within the timeout

## Part B — Workflow transition API journeys on the compose stack (merged from APPROVALS-07, carried forward from APPROVALS-02)

### Spec

Run APPROVALS-02's two Playwright API journeys against a whole deployment (the compose stack in CI
lane `e2e-skeleton`, the Coolify demo after a deploy). APPROVALS-02 proved the same HTTP flows
in-process. They could not run deployed yet, because no record type exists whose workflow,
permissions and fixture users a stack can seed (ADR 0035 §9).

- **files**:
  - a dev/test-only seed (refuses `AIP_ENV=production`) that publishes a `demo` workflow in
    `kaefer-demo` with real catalogue permissions, or that uses APPROVALS-05's inspection preset
    if it has landed, and grants them to the submitter fixture user
  - a dev/test-only guard facts provider for that record type, with a fixture switch for
    `allPhotosClean`
  - `e2e/web/approvals-transition.spec.ts`
- **steps**:
  - 1. Add the seed and run it in the compose stack's fixture step.
  - 2. Add the journeys to the skeleton projects (`@skeleton`; `@staging` too if the demo can
       run the seed).
- **acceptance**:
  - Both journeys are green in CI lane `e2e-skeleton`.
- **tests**:
  - **e2e**:
    - Sign in as the `kaefer-demo` submitter. `POST /api/v1/approvals/instances`, transition
      `submit`, then `GET /history`: 1 entry, a 64-hex `entryHash`, and `chainValid: true`. The
      same GET as a `tenant-b` user → 404.
    - The guarded flow: `approve` is refused with 422 `GUARD_FAILED`. After the fixture flips
      `allPhotosClean`, `approve` (with a fresh aal 2 sign-in, or after a step-up) → 200, and
      `GET /history` shows `chainValid: true`.
