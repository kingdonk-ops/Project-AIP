# SECURITY-02 — Security schema with RLS and append-only grants
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0002](../../docs/adr/0002-data-access-and-migrations.md) (forward-only Alembic raw SQL from templates, FORCE RLS, `aip_app`; TESTING-05 replaces up-down-up), [0004](../../docs/adr/0004-repository-layout.md) (module layout)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Create the seven security tables with FORCE RLS, soft delete on mutable tables, and UPDATE/DELETE revoked from the app roles on the append-only tables.

- **files**:
  - apps/api/migrations/versions/<rev>_security_tables.py
  - apps/api/aip/modules/security/__init__.py (exports `api` only)
  - apps/api/aip/modules/security/tables.py
  - apps/api/aip/modules/security/schemas.py
  - apps/api/aip/modules/security/manifest.toml
  - apps/api/aip/modules/security/tests/test_security_schema.py
- **steps**:
  - 1. Write the raw-SQL Alembic revision for `control_records`, `evidence_items`, `access_reviews`, `restore_test_records`, `data_map_entries`, `breach_incidents` and `provenance_entries`, rendering mutable tables from `db/templates/tenant_table.sql.tpl` and append-only tables (`evidence_items`, `restore_test_records`, `provenance_entries`) from `db/templates/append_only_table.sql.tpl` (or the tenant template without `deleted_at` if DATABASE-05 has not merged).
  - 2. Use UUIDv7 keys (generated in the app) and `tenant_id`; indexes: unique `(tenant_id, control_key)` on `control_records` (partial `WHERE deleted_at IS NULL`) and `(tenant_id, status)`. `control_records.status` has a CHECK constraint `status IN ('specified','implemented','proven')`; `framework_mappings` is jsonb.
  - 3. Enable and FORCE RLS on all seven with the NULLIF tenant policy (USING and WITH CHECK).
  - 4. `REVOKE UPDATE, DELETE, TRUNCATE ON evidence_items, restore_test_records, provenance_entries FROM aip_app, aip_jobs`.
  - 5. Declare the seven SQLAlchemy Core `Table` objects in `tables.py` and Pydantic models in `schemas.py`, including `ControlStatus = Literal["specified", "implemented", "proven"]`.
  - 6. Forward-only: `downgrade()` raises `NotImplementedError("forward-only, ADR 0002")`; reversals ship as a new revision.
- **acceptance**:
  - The TESTING-02 schema guard passes for all seven tables.
  - UPDATE or DELETE on an append-only table by `aip_app` raises `InsufficientPrivilegeError` (SQLSTATE 42501).
  - `tables.py` matches the migrated schema (the CI declared-vs-migrated comparison passes).
- **tests**:
  - **e2e**:
    - None; covered by TESTING-05 (apply all revisions to an empty database and to the previous release's snapshot, then diff).
  - **integration** (pytest + testcontainers-python, as `aip_app` inside `with_tenant`):
    - `UPDATE evidence_items SET ...`. Expected: permission denied.
    - `DELETE FROM restore_test_records`. Expected: permission denied.
    - Two `control_records` with the same `(tenant, control_key)`. Expected: unique violation (SQLSTATE 23505).
    - Insert a `control_records` row as tenant A; select as tenant B. Expected: 0 rows.
    - Insert `control_records.status = 'done'`. Expected: check violation (SQLSTATE 23514).
  - **unit**:
    - The Pydantic `ControlRecordCreate` model rejects status `'done'` and accepts `'specified'`, `'implemented'` and `'proven'`.
