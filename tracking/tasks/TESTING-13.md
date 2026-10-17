# TESTING-13 — Stack proves the worker

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | AUDIT-02, TESTING-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. ADRs: 0030
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M10**. The worker healthcheck is `python -c "import aip"` (`infra/docker-compose.yml:399-403`,
same in Coolify). `tools/smoke.py` and `walking-skeleton.spec.ts` never check that `project.created` is published or
audited. The CI e2e log tail omits `worker` (`ci.yml:466`). A crash-looping worker, a wrong
`DATABASE_AUDIT_WRITER_URL` or a dispatcher that never drains all ship green.

## Spec

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
