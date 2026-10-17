# OPS-17 — Job handlers can write domain tables and emit events

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | ARCH-05, OPS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0016, 0030
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **H3**. Handlers run inside `with_tenant(tenant_id, engine=get_jobs_engine())`
(`modules/ops/runner.py`), so as `aip_jobs`. `aip_jobs` has no grants on tenant tables (the table template grants it
nothing). The review saw only SELECT plus column UPDATE on `domain_events`; since then OPS-03 (PR #100, ADR 0030
amendment) granted `aip_jobs` INSERT on `domain_events`, so emitting now works and the tenant-table grants are the gap
left. The only handlers today (Keycloak session revocation, `ops.send_email`) touch no tenant table, so nothing breaks yet. UPLOADS-02 updates `upload_sessions` and emits `upload.completed`/`upload.rejected` inside its job, which
would retry until it dead-letters. No runner test has a handler that writes a tenant table.

## Spec

A job handler can write tenant tables and emit domain events, so UPLOADS-02, AUDIT-03, imports and PDF jobs do not fail with `permission denied`.

- **files**:
  - docs/adr/0016-job-runner-semantics.md (amendment)
  - apps/api/aip/modules/ops/runner.py
  - apps/api/aip/modules/ops/tests/
  - db/ migrations or templates (only for option b)
- **steps**:
  - 1. Amend ADR 0016 choosing between: (a) run the handler transaction on the `aip_app` engine (RLS still applies through `with_tenant`) and keep `aip_jobs` for queue and status bookkeeping; (b) grant `aip_jobs` the `aip_app` table set (it already has INSERT on `domain_events`). The review recommends (a): simpler, least privilege.
  - 2. Implement the choice in the runner.
  - 3. Add a runner test whose handler writes a tenant table and emits an event, run as the real roles.
- **acceptance**:
  - A handler that inserts into a tenant table and emits an event succeeds, and the event reaches the outbox.
  - RLS still binds the handler to the job's tenant.
  - `aip_jobs` gains no privilege the ADR does not name.
- **tests**:
  - **integration**:
    - handler writes a `widgets` row and emits `widget.created` v1 → job succeeds, row and outbox event exist
    - the same handler for tenant A → no row visible in tenant B
