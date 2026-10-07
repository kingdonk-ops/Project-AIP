# DATABASE-04 — Base repository helpers: concurrency, ltree, soft delete, JSONB validation
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (Python backend), [0002](../../docs/adr/0002-data-access-and-migrations.md) (SQLAlchemy Core, `text()` for ltree, tenant-bound connection), [0004](../../docs/adr/0004-repository-layout.md) (`aip/platform/db`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Provide shared SQLAlchemy Core helpers so module repositories never hand-write optimistic concurrency, ltree moves, soft delete, JSONB attribute validation or idempotent create. Every helper takes the tenant-bound `AsyncConnection` from `with_tenant` and never opens its own.

- **depends on**:
  - DATABASE-02
- **files**:
  - apps/api/aip/platform/db/concurrency.py
  - apps/api/aip/platform/db/ltree.py
  - apps/api/aip/platform/db/soft_delete.py
  - apps/api/aip/platform/db/jsonb_schema.py
  - apps/api/aip/platform/db/idempotency.py
  - apps/api/aip/platform/db/errors.py (add `ConflictError`, `CycleError`, `NotFoundError`)
  - apps/api/aip/platform/http/errors.py (FastAPI exception handlers: `ConflictError` → 409, `NotFoundError` → 404)
  - apps/api/tests/platform/db/test_helpers.py
- **steps**:
  - 1. `concurrency.update_with_version(conn, table, id, expected_version, patch)`: one `UPDATE ... SET ..., sync_version = sync_version + 1 WHERE id = :id AND sync_version = :expected AND deleted_at IS NULL RETURNING *`. On zero rows, re-select the row and raise `ConflictError(current=row)`; the HTTP handler returns 409 with `{"code": "VERSION_CONFLICT", "current": {...}}`.
  - 2. `ltree.descendants(conn, table, path)`, `ancestors(conn, table, path)` and `move_subtree(conn, table, from_path, to_parent_path)` using `text()` with `<@`/`@>` and a single `UPDATE ... SET path = :new || subpath(path, nlevel(:old) - 1) WHERE path <@ :old`. Raise `CycleError` when `to_parent_path` equals or is a descendant of `from_path`, before any SQL runs.
  - 3. `soft_delete.soft_delete(conn, table, id)` and `restore(conn, table, id)`; `active(table)` returns a `select()` with `deleted_at IS NULL` that repositories use as their default query base.
  - 4. `jsonb_schema.validate_attributes(type_schema: dict, value: dict) -> list[AttributeError]` using the `jsonschema` library (Draft 2020-12) against the per-type JSON Schema stored in the database; each error carries a JSON path (for example `$.wall_loss_mm`) and a terminology key, not an English label. Pydantic is used for request bodies; stored per-type schemas are validated here.
  - 5. `idempotency.create_idempotent(conn, table, values)` for tables with `client_generated_id uuid` and a unique index `(tenant_id, client_generated_id)`: `INSERT ... ON CONFLICT (tenant_id, client_generated_id) DO NOTHING RETURNING *`, falling back to selecting the existing row. Add the column and index to `db/templates/tenant_table.sql.tpl` as an optional block `{{#sync}}` (with `sync_version integer NOT NULL DEFAULT 1`).
- **acceptance**:
  - A stale version returns 409 with the current record in the body.
  - Moving a node under itself or its own descendant is rejected with `CycleError` and no rows change.
  - A repeated create with the same `client_generated_id` returns the original row, not a duplicate.
  - Default queries never return soft-deleted rows.
- **tests**:
  - **e2e**:
    - Playwright, once an edit form exists (assets, or the `_template` module fixture page): edit one record in two browser contexts and save the second. Expected: the conflict dialog shows a field diff with Merge, Reload and Cancel.
  - **integration** (pytest + testcontainers-python, as `aip_app` inside `with_tenant`; fixture table `helper_probe` rendered from the tenant template with `path ltree`, `attributes jsonb` and the sync block):
    - Move node `a.b` (with 3 descendants) under `a.c`. Expected: all 4 paths now start with `a.c.b` and `descendants('a.c.b')` count is 3.
    - Two concurrent `update_with_version` calls with expected version 1 (two `with_tenant` transactions started together). Expected: one succeeds, one raises `ConflictError` (409 through a fixture route).
    - Soft delete a row, then GET it through a fixture route. Expected: 404. Restore it. Expected: 200.
    - `create_idempotent` twice with the same `client_generated_id`. Expected: same `id`, 1 row; the same id in tenant B creates a separate row.
  - **unit**:
    - `update_with_version` with expected 3 against stored 4 raises `ConflictError` with `current["sync_version"] == 4` (connection fake returning 0 rows then the current row).
    - `move_subtree(conn, t, "a.b", "a.b.c")` raises `CycleError` without executing SQL.
    - `validate_attributes({"type":"object","properties":{"wall_loss_mm":{"type":"number"}}}, {"wall_loss_mm":"x"})` returns one error with path `$.wall_loss_mm`.
