# SECURITY-03 — Control catalogue service, baseline seed and admin router

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | SECURITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Manage controls and evidence with status derived from evidence, and an admin-only API.

- **depends on**:
  - SECURITY-02
- **files**:
  - backend/app/modules/security/controls.py
  - backend/app/modules/security/router.py
  - backend/app/modules/security/baseline_controls.json
  - backend/tests/security/test_controls.py
- **steps**:
  - 1. Seed about 25 baseline controls with soc2, iso27001, ism and app mappings in JSON.
  - 2. Implement import_baseline(tenant) as an idempotent upsert on control_key.
  - 3. Implement add_evidence(control, type, hash) and a status rule: proven only if evidence_source is set and there is evidence within its schedule window; otherwise implemented or specified.
  - 4. Add endpoints GET/POST /security/controls, POST /security/controls/{id}/evidence and GET /security/matrix.
  - 5. Guard routes with security:admin in the catalogue.
  - 6. Add a CSV matrix export.
- **acceptance**:
  - Baseline import is idempotent.
  - A control without evidence cannot be set to proven.
  - Non-admin gets 403.
- **tests**:
  - **e2e**:
    - Security lead opens /security/controls, adds evidence, and the KPI on /security/compliance moves from specified to proven.
  - **integration**:
    - POST import twice: 25 controls, not 50.
    - Add evidence, then GET control: status proven.
    - Tenant admin without security:admin: GET /security/controls returns 403.
  - **unit**:
    - Status rule: evidence 10 days old with a 90-day schedule gives proven; 120 days old gives implemented.
