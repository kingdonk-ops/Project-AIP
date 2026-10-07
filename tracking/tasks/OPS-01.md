# OPS-01 — Job records tables and service
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-08 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0002](../../docs/adr/0002-data-access-and-migrations.md) (Alembic raw SQL, tenant template, `with_tenant`, UUIDv7), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Procrastinate is the transport; this table is the user-visible job record), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Persist user-visible job state and its event history in tenant-scoped Postgres tables with idempotent creation. Procrastinate (OPS-02) owns queue transport; `jobs` is the business record the Jobs API (OPS-03) reads.

- **files**:
  - apps/api/migrations/versions/<rev>_ops_jobs.py
  - apps/api/aip/modules/ops/__init__.py (exports `api` only)
  - apps/api/aip/modules/ops/tables.py
  - apps/api/aip/modules/ops/schemas.py
  - apps/api/aip/modules/ops/repository.py
  - apps/api/aip/modules/ops/service.py
  - apps/api/aip/modules/ops/api.py
  - apps/api/aip/modules/ops/manifest.toml
  - apps/api/aip/modules/ops/tests/test_job_service.py
- **steps**:
  - 1. Revision (raw SQL from `db/templates/tenant_table.sql.tpl`): `jobs` (id, tenant_id, job_type, status `queued|running|succeeded|failed|cancelled`, idempotency_key NULL, correlation_id uuid, attempts int, payload jsonb, result_ref text NULL, error text NULL, requested_by, procrastinate_job_id bigint NULL, timestamps) with the unique partial index `(tenant_id, job_type, idempotency_key) WHERE idempotency_key IS NOT NULL`; `job_events` from `db/templates/append_only_table.sql.tpl` if present, else tenant template plus `REVOKE UPDATE, DELETE` (id, tenant_id, job_id, seq int, from_status, to_status, detail jsonb, occurred_at; unique `(job_id, seq)`). FORCE RLS on both. Grant `aip_jobs` SELECT and UPDATE on `jobs` status/result columns and INSERT on `job_events`.
  - 2. Declare both tables in `tables.py` (SQLAlchemy Core `Table`) and Pydantic models `JobView`, `JobStatus` (`StrEnum`) in `schemas.py`.
  - 3. `create_job(conn, *, job_type, payload, idempotency_key=None, correlation_id=None) -> JobView`: `INSERT ... ON CONFLICT ... DO NOTHING RETURNING *`, falling back to the existing row on a duplicate key.
  - 4. `transition(conn, job_id, new_status, *, detail=None)` enforcing `queued → running → succeeded|failed|cancelled` and `queued → cancelled`; terminal states are final; uses `SELECT ... FOR UPDATE`.
  - 5. Write a `job_events` row for each transition (including the initial `queued`) with `seq` incremented per job.
  - 6. Generate a UUIDv7 `correlation_id` when none is supplied (or take it from the ARCH-04 request context if present).
- **acceptance**:
  - The same idempotency key in the same tenant gives the same job id.
  - Terminal jobs cannot change state.
  - Events are strictly ordered by `seq` per job.
- **tests**:
  - **e2e**:
    - None; the API is covered in OPS-03.
  - **integration** (pytest + testcontainers-python, as `aip_app` inside `with_tenant`):
    - `create_job` twice with key `k1`. Expected: 1 row, same id.
    - Same key in tenant B. Expected: a separate job.
    - `queued → running → succeeded`. Expected: 3 `job_events` with seq 1, 2, 3 and statuses queued, running, succeeded.
    - As `aip_app`, `UPDATE job_events SET detail='{}'`. Expected: permission denied.
  - **unit**:
    - `transition` validation `succeeded → running` raises `InvalidTransition`.
    - `create_job(..., correlation_id=None)` produces a UUID version 7 correlation id.
