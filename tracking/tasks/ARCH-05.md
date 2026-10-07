# ARCH-05 — domain_events outbox table and writer

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-04, DATABASE-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Write domain events in the same transaction as the state change, with append-only grants.

- **depends on**:
  - ARCH-04
  - DATABASE-02
- **files**:
  - migrations/versions/0100_domain_events.sql
  - apps/api/src/platform/events/outbox.ts
  - apps/api/src/platform/events/outbox.spec.ts
- **steps**:
  - 1. Write the raw-SQL Alembic migration from migrations/templates/new_table.sql.tpl with the specified columns, FORCE RLS and tenant_id policy.
  - 2. Add the indexes: partial (tenant_id, occurred_at) WHERE published_at IS NULL AND dead_lettered_at IS NULL, plus aggregate, asset and event_name indexes.
  - 3. Grant the app role INSERT and SELECT only. Create a dispatcher role with UPDATE limited to published_at, attempts, dead_lettered_at and last_error.
  - 4. Implement emit(tx, eventName, version, aggregate, payload) that validates the payload via the registry (ARCH-06) and inserts using the caller's transaction.
  - 5. Fill tenant_id, project_id, actor_id and occurred_at from the request context.
- **acceptance**:
  - Rolling back the business transaction leaves no event row.
  - The app role cannot UPDATE payload.
  - A cross-tenant SELECT returns 0 rows.
- **tests**:
  - **e2e**:
    - Sign off an inspection via the API. Expected: exactly one inspection.signed_off row exists with the correct asset_id and actor_id.
  - **integration**:
    - Testcontainers: begin transaction, create inspection, emit inspection.signed_off, roll back. Expected: 0 rows in domain_events.
    - As the app role, run UPDATE domain_events SET payload='{}'. Expected: permission denied.
    - Insert events for tenants A and B, set app.tenant_id=A. Expected: SELECT count equals A's events only.
  - **unit**:
    - emit with a payload failing the schema throws EventValidationError and does not call insert.
    - emit fills tenant_id from the context.
