# ARCH-05 — domain_events outbox table and writer
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-04, DATABASE-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md) (the `domain_events` column list under "Data")
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (Alembic raw SQL, `with_tenant`, roles), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox is the system of record), [0004](../../docs/adr/0004-repository-layout.md)

## Spec

Write domain events in the same `with_tenant` transaction as the state change, with append-only grants for `aip_app` and publish-column-only grants for `aip_jobs`.

- **depends on**:
  - ARCH-04
  - DATABASE-02
- **files**:
  - apps/api/migrations/versions/<YYYYMMDDHHMM>_domain_events.py (Alembic revision; raw SQL via `op.execute`, `downgrade()` raises)
  - apps/api/aip/platform/events/tables.py (SQLAlchemy Core `Table` for `domain_events`)
  - apps/api/aip/platform/events/outbox.py
  - apps/api/aip/platform/events/lookup.py (`EventSchemaLookup` protocol + dict-backed implementation; ARCH-06 supplies the real registry)
  - apps/api/tests/platform/events/test_outbox.py
  - apps/api/tests/platform/events/fixtures.py (fixture event `widget.created` v1 with Pydantic payload `{widget_id: UUID, name: str}`)
- **steps**:
  - 1. Write the revision from DATABASE-02's tenant-table template in `db/templates/`, without soft-delete columns (append-only table). Columns: `id uuid PK` (UUIDv7 from the app), `tenant_id uuid not null`, `project_id uuid null`, `asset_id uuid null`, `event_name text`, `event_version int`, `aggregate_type text`, `aggregate_id uuid`, `payload jsonb`, `actor_id uuid null` (null for system events), `occurred_at timestamptz`, `published_at timestamptz null`, `attempts int default 0`, `dead_lettered_at timestamptz null`, `last_error text null`. `ENABLE` and `FORCE ROW LEVEL SECURITY`.
  - 2. Policy for `aip_app`: `USING` and `WITH CHECK` `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`. Separate policy for `aip_jobs` (`FOR SELECT, UPDATE TO aip_jobs USING (true)`) so the dispatcher can claim rows across tenants; it is limited by the column grant below.
  - 3. Indexes: partial `(tenant_id, occurred_at) WHERE published_at IS NULL AND dead_lettered_at IS NULL`; `(aggregate_type, aggregate_id)`; `(asset_id)`; `(event_name, occurred_at)`.
  - 4. Grants: `aip_app` `INSERT, SELECT` only. `aip_jobs` `SELECT` and `UPDATE (published_at, attempts, dead_lettered_at, last_error)` only. `aip_readonly` `SELECT`.
  - 5. Implement `async def emit(conn: AsyncConnection, event_name: str, version: int, aggregate: Aggregate, payload: Mapping[str, Any], *, asset_id: UUID | None = None) -> UUID`. It validates the payload with the Pydantic model returned by the injected `EventSchemaLookup` (raising `EventValidationError` listing the bad fields, before any SQL runs), fills `tenant_id`, `project_id` and `actor_id` from `get_context()` and `occurred_at` from the clock, and inserts using the caller's tenant-bound connection (never opening its own).
- **acceptance**:
  - Rolling back the business transaction leaves no event row.
  - `aip_app` cannot UPDATE `payload` or DELETE rows; `aip_jobs` can update only the four publish columns.
  - A cross-tenant SELECT under `with_tenant` returns 0 rows of the other tenant.
  - With `app.tenant_id` unset, SELECT returns 0 rows and INSERT fails (fail-closed).
- **tests**:
  - **unit**:
    - `emit(conn, "widget.created", 1, agg, {"name": 5})` raises `EventValidationError` naming `widget_id` and `name`, and the fake connection records no `execute` call.
    - `emit` inside `use_context(RequestContext(tenant_id=T1, actor_id=U1, ...))` builds an insert whose `tenant_id` is `T1` and `actor_id` is `U1`.
  - **integration** (testcontainers-python, `pgvector/pgvector:pg16`, migrations applied as `aip_owner`, tests connect as `aip_app`):
    - In `with_tenant(A)`: insert a fixture `widgets` row, `emit("widget.created", ...)`, then raise to roll back. Expected: 0 rows in `domain_events` (checked as `aip_owner`).
    - As `aip_app` in `with_tenant(A)`: `UPDATE domain_events SET payload='{}'`. Expected: `InsufficientPrivilegeError`.
    - As `aip_jobs`: `UPDATE domain_events SET payload='{}'`. Expected: permission denied; `UPDATE ... SET published_at=now()` succeeds.
    - Insert 3 events for tenant A and 2 for tenant B. In `with_tenant(A)`, `SELECT count(*)`. Expected: 3.
    - With no tenant set, `SELECT count(*)` as `aip_app`. Expected: 0.
  - **e2e**:
    - With the fixture module `widgets` mounted (`AIP_ENV=test`), `POST /api/v1/_fixtures/widgets {"name": "w1"}` as the `tenant-a` fixture user. Expected: exactly one `widget.created` row exists with that widget's id as `aggregate_id` and the fixture user as `actor_id`.
