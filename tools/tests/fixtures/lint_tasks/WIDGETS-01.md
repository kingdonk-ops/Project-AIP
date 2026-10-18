# WIDGETS-01 — Widgets table, CRUD API and register page

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`widgets`](../../docs/blueprint/modules/widgets/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)

## Spec

Store widgets per tenant and list them in a register (tag: extend).

- **files**:
  - apps/api/migrations/versions/<timestamp>_widgets_table.py
  - apps/api/aip/modules/widgets/tables.py
  - apps/api/aip/modules/widgets/routes.py
  - apps/api/aip/modules/widgets/tests/test_widgets_db.py
  - apps/web/src/features/widgets/WidgetsRegister.tsx
  - e2e/web/widgets.spec.ts
- **steps**:
  - 1. Migration: create `widgets` from `db/templates/tenant_table.sql.tpl` with `name text NOT NULL`.
  - 2. `GET /api/v1/widgets` and `POST /api/v1/widgets` behind `widget.view` and `widget.create`.
- **acceptance**:
  - A tenant sees only its own widgets.
- **tests**:
  - **unit**:
    - `name` of 300 characters → 422.
  - **integration**:
    - As `tenant-b`, `SELECT count(*) FROM widgets` after `kaefer-demo` created one → 0, and the `widgets` row is
      invisible. `REVOKE ... FROM aip_app` is not needed.
  - **e2e**:
    - Create a widget on `/widgets` → it appears in the register; `tenant-b` opening its URL → 404.
