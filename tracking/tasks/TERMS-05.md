# TERMS-05 — Terms admin API and permissions

<!-- hand-edited: permission codes use dots (ACCESS-01) -->

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TERMS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Expose dictionary, override, pack and locale endpoints with catalogue permissions.

- **depends on**:
  - TERMS-04
- **files**:
  - backend/app/modules/terms/router.py
  - backend/app/modules/terms/permissions.py
  - backend/tests/terms/test_router.py
- **steps**:
  - 1. Add GET /terms/keys with search, filters and effective text.
  - 2. PUT/DELETE /terms/overrides with level validation (market pack, tenant, client, project only if allowed by settings).
  - 3. Pack endpoints: import, dry-run, apply, rollback, export.
  - 4. GET/PUT /terms/locale-settings.
  - 5. Register permissions terms.view and terms.admin in the catalogue.
  - 6. Write an audit log entry for each change.
- **acceptance**:
  - A non-admin cannot override.
  - An override at a disallowed level returns 422.
  - Each override is audited with before and after.
- **tests**:
  - **e2e**:
    - Admin searches 'Hold point', overrides it, previews it on the email surface and saves.
  - **integration**:
    - Viewer PUT override returns 403.
    - Admin PUT override returns 200 and GET shows the effective text.
    - The audit_log has a row with old and new text.
    - Search 'punch' with an alias to 'defect' returns the defect keys.
  - **unit**:
    - Level validator rejects 'platform' from a tenant request.
