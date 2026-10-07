# SECURITY-02 — Security schema with RLS and append-only grants

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Create the seven security tables with RLS, soft delete and revoked UPDATE/DELETE on append-only tables.

- **files**:
  - backend/app/modules/security/models.py
  - backend/migrations/versions/xxxx_security_tables.py
  - backend/tests/security/test_security_schema.py
- **steps**:
  - 1. Write the raw SQL migration for control_records, evidence_items, access_reviews, restore_test_records, data_map_entries, breach_incidents and provenance_entries.
  - 2. Use uuid keys and tenant_id; indexes: unique (tenant_id, control_key) and (tenant_id, status).
  - 3. Enable and FORCE RLS with a tenant policy.
  - 4. REVOKE UPDATE, DELETE on evidence_items, restore_test_records and provenance_entries FROM aip_app.
  - 5. Add SQLAlchemy models.
  - 6. Write the downgrade.
- **acceptance**:
  - The schema guard passes for all new tables.
  - UPDATE on an append-only table by the app role raises InsufficientPrivilege.
- **tests**:
  - **e2e**:
    - None; covered by the up-down-up migration job.
  - **integration**:
    - As aip_app, UPDATE evidence_items raises permission denied.
    - DELETE restore_test_records raises permission denied.
    - Duplicate (tenant, control_key) raises a unique violation.
    - Tenant B cannot read tenant A's control_records.
  - **unit**:
    - Model status check constraint rejects 'done' and accepts 'specified', 'implemented', 'proven'.
