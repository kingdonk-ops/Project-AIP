# ASSETS-08 — Ancestor names on asset list rows

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`assets`](../../docs/blueprint/modules/assets/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | ASSETS-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`ASSETS-03.md`](ASSETS-03.md) (the register and parent picker that use the breadcrumbs)
3. [`docs/blueprint/modules/assets/README.md`](../../docs/blueprint/modules/assets/README.md)

## Spec

Found while building ASSETS-03 (tag: extend): the `/assets` register's Parent column and the parent
picker show breadcrumbs (`Site A > Unit 1`), but `GET /api/v1/assets` returns only ids, so the web
app fetches `GET /api/v1/assets/{id}` once per distinct parent on the page (`useCrumbs` in
`apps/web/src/features/assets/data.ts`). Return the names with the list instead.

- **files**:
  - apps/api/aip/modules/assets/repository.py
  - apps/api/aip/modules/assets/schemas.py
  - apps/api/aip/modules/assets/service.py
  - apps/api/aip/modules/assets/tests/test_assets_db.py
  - packages/api-client/openapi.json
  - packages/api-client/src/generated/
  - apps/web/src/features/assets/data.ts
  - apps/web/src/features/assets/AssetsRegister.tsx
  - apps/web/src/features/assets/ParentPicker.tsx
- **steps**:
  - 1. Add `ancestorNames: list[str]` (root first, the asset itself excluded) to `AssetOut` on list
    responses, computed in the list query the way the CSV export computes `path`
    (`repository._PATH_NAMES_EXPR`), so one query serves a page.
  - 2. Regenerate the client; build the register's Parent column and the picker's option labels from
    `ancestorNames` and remove `useCrumbs`' per-parent fetches (keep `GET /assets/{id}` only for the
    `under` scope chip and the selected parent).
- **acceptance**:
  - Opening `/assets` with 50 rows under 20 parents makes one list request and no per-parent requests.
  - Breadcrumbs read the same as before.
- **tests**:
  - **unit**:
    - The register renders `Site A > Unit 1` from `ancestorNames` with no `GET /assets/{id}` handler registered.
  - **integration**:
    - `GET /api/v1/assets?under=<Site A>` → each item's `ancestorNames` is its live ancestors, root first; another tenant sees none.
  - **e2e**:
    - The ASSETS-03 stub-lane journey still passes.
