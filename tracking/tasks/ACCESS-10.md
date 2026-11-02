# ACCESS-10 — Operator console page for the default role template

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ACCESS-09, OPS-12 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md)
3. ADRs: 0017 (operator console on its own origin), 0042

## Spec

Give the platform operator a page to edit the default role template that ACCESS-09's API serves. Split from
ACCESS-09: the operator console (OPS-12) does not exist yet, and ADR 0017 keeps operator pages off the tenant app.

- **files**:
  - the operator console app from OPS-12 (`/platform/default-roles`)
  - e2e/ (operator journey)
- **steps**:
  - 1. Grid of modules × the 11 system roles; each cell a level picker, with the shipped level shown and overridden
    cells marked. Labels through terminology keys (`access.role.<code>.name`, level keys).
  - 2. Save collects the changed cells and a required reason into one `PATCH /api/v1/platform/default-roles`; show
    the 422 guardrail codes against their cells.
  - 3. History panel (`GET /history`, filter by module or role).
  - 4. "Push to tenants" (`POST /sync`): all active tenants or chosen ones; show each tenant's `updated`, `pending`
    and `excess`.
- **acceptance**:
  - The operator can change, reset and push cells and read the history without the API docs.
- **tests**:
  - **unit**:
    - Changed-cell diffing sends only moved cells.
  - **integration**:
    - none beyond ACCESS-09.
  - **e2e**:
    - Operator changes a cell with a reason, pushes to tenant A, sees `updated`; a tenant admin cannot reach the
      page; axe check.
