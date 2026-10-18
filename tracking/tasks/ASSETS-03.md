# ASSETS-03 — Asset tree and register page (/assets) with generated create and edit form

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`assets`](../../docs/blueprint/modules/assets/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ACCESS-07, ASSETS-02, DESIGN-03, ITEMTYPES-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`ASSETS-01.md`](ASSETS-01.md) and [`ASSETS-02.md`](ASSETS-02.md) (the API this page uses), [`DESIGN-03.md`](DESIGN-03.md) (the register standard), [`PROJECTS-06.md`](PROJECTS-06.md) "As built" (the register pattern to copy), [`ITEMTYPES-03.md`](ITEMTYPES-03.md) (the field preview to reuse)
3. [`docs/blueprint/modules/assets/routes.md`](../../docs/blueprint/modules/assets/routes.md) (`/assets` and `/assets/new` only) and [`ui-layout.md`](../../docs/blueprint/modules/assets/ui-layout.md)
4. ADRs: [0018](../../docs/adr/0018-module-groups-and-navigation.md) (nav section), [0025](../../docs/adr/0025-time-and-timezones.md) (local time only at presentation), [0033](../../docs/adr/0033-register-csv-exports.md) (register CSV exports)

## Spec

Build the `/assets` page: a keyboard-accessible tree panel that narrows a `RegisterTable` of assets to a subtree, a create and edit form generated from the asset's item-type version with a parent picker and a live Tag Number check, a move dialog, and the register's CSV export (tag: extend).

Out of scope: drag-and-drop reparenting and sibling reorder (ASSETS-04, which also adds bulk add), the asset detail page (ASSETS-05; until it lands, opening a row goes to the edit form), the top scope-bar asset picker (ASSETS-07), open-item counts and status, criticality and location fields (later rows), import (DATAIO-02) and label sheets (not R1).

- **files**:
  - apps/api/aip/modules/assets/routes.py
  - apps/api/aip/modules/assets/service.py
  - apps/api/aip/modules/assets/tests/test_assets_export_db.py
  - apps/web/src/features/assets/nav.ts
  - apps/web/src/features/assets/terms.ts
  - apps/web/src/features/assets/search.ts
  - apps/web/src/features/assets/columns.tsx
  - apps/web/src/features/assets/AssetsPage.tsx
  - apps/web/src/features/assets/AssetTree.tsx
  - apps/web/src/features/assets/AssetsRegister.tsx
  - apps/web/src/features/assets/AssetForm.tsx
  - apps/web/src/features/assets/AttributeFields.tsx
  - apps/web/src/features/assets/ParentPicker.tsx
  - apps/web/src/features/assets/MoveAssetDialog.tsx
  - apps/web/src/features/assets/assets.css
  - apps/web/src/features/assets/__tests__/helpers.tsx
  - apps/web/src/features/assets/__tests__/tree.test.tsx
  - apps/web/src/features/assets/__tests__/register.test.tsx
  - apps/web/src/features/assets/__tests__/form.test.tsx
  - apps/web/src/routes/_app/assets/index.tsx
  - apps/web/src/routes/_app/assets/new.tsx
  - apps/web/src/routes/_app/assets/edit.tsx
  - apps/web/src/router.ts
  - config/terms/en-AU/assets.json
  - packages/api-client/openapi.json
  - packages/api-client/src/generated/
  - e2e/web/assets.spec.ts
  - e2e/web/assets-live.spec.ts
  - e2e/playwright.config.ts
- **steps**:
  - 1. API: `GET /api/v1/assets/export.csv` (`assets_export`, `asset.view`), declared before `/{asset_id}`. Same filters
    and sort as the list (`parentId`, `under`, `q`, `tagNumber`, `itemTypeId`, `sort`); counts first and answers 422
    `EXPORT_TOO_LARGE` above 10,000 rows, then streams `aip.platform.http.csv.csv_header` + keyset batches of
    `csv_row`, exactly like `projects_export`. Columns are the API's field names (ADR 0033): `internalTag`,
    `tagNumber`, `name`, `parentId`, `path` (ancestor names joined with ` > `), `itemTypeId`, `itemTypeVersionId`,
    `updatedAt` (UTC ISO 8601). Regenerate the OpenAPI client.
  - 2. Routes (code-based TanStack routes, registered in `apps/web/src/router.ts`):
    - `/assets` → `AssetsPage`; search is the canonical register query (`decodeRegisterQuery` / `encodeRegisterQuery`
      with `ASSETS_SPEC`) plus `under` (an asset id) and `created` (the internal tag just created).
    - `/assets/new` → `AssetForm` in create mode; optional `parentId` search param preselects the parent.
    - `/assets/$assetId/edit` (file `edit.tsx`) → `AssetForm` in edit mode.
    - `nav.ts`: `registerNavItem({id: "assets", section: "work-assets", to: "/assets", termKey: "assets.nav.title", permission: "asset.view"})`
      with an icon from `iconNames`.
  - 3. `AssetTree.tsx` (WAI-ARIA tree pattern): `role="tree"` with `treeitem`s carrying `aria-level`, `aria-setsize`,
    `aria-posinset` and `aria-expanded` (only when `childCount > 0`). Children load lazily with
    `GET /api/v1/assets?parentId=<id>|root&sort=position` (the generated `useAssetsList` hook), 200 per page with a
    "Show more" item. Keys: Up/Down move, Right expands or enters, Left collapses or goes to the parent, Home/End,
    Enter selects. One roving `tabIndex`. Selecting a node sets `under=<id>` in the URL; the page shows a scope chip
    "Within: <name>" whose clear button removes `under` in one click. Expanded node ids persist per tab in
    `sessionStorage` (wrapped in try/catch). On narrow screens (< 768 px) the tree is a drawer opened from a
    "Browse tree" button.
  - 4. `AssetsRegister.tsx`: `RegisterTable` (`@aip/ui`) with `id="assets"`, columns `name`, `tagNumber`,
    `internalTag`, `itemType` (name from the item types list of ITEMTYPES-01/03, via the generated client), `parent`
    (breadcrumb of the row's parent) and `updated` (local time per ADR 0025). Filters: item type (multi-select) and
    the free-text search (`q`). Sortable: `name`, `tagNumber`, `updated`. `exportHref` points at step 1 with the same
    query. `onOpenRow` → `/assets/<id>/edit` (ASSETS-05 repoints it to the detail page). Row actions, each shown only
    with its permission: Edit (`asset.update`), Add child (`asset.create`, opens `/assets/new?parentId=<id>`), Move
    (`asset.move`). A "Create asset" button needs `asset.create`; with `under` set it preselects that parent. Empty
    state with the create call to action, as in projects.
  - 5. `AssetForm.tsx` (create and edit; `FormField`, `Input`, `Combobox` from `@aip/ui`):
    - Name (required, ≤ 200), Tag Number (optional, ≤ 64), parent (`ParentPicker`, create only; moving is step 6),
      item type (combobox of published item types; changing it in edit mode warns that attributes are re-validated
      against that type's current version).
    - Tag Number check: 300 ms after typing stops, `GET /api/v1/assets?tagNumber=<value>&limit=1`; a hit other than
      this asset shows `assets.form.tag_number_taken` ("Already used by {name} ({internalTag})") inline. The server's
      409 `TAG_NUMBER_IN_USE` is still authoritative and is shown on the same field.
    - Attributes: rendered from the pinned version (edit) or the type's published version (create), using the field
      renderer ITEMTYPES-03 built for its field preview if it is exported from a package; otherwise
      `AttributeFields.tsx` renders the field-type keys from `packages/contracts/field-types/field-types.json`:
      `text`, `number`, `decimal`, `date`, `dropdown`, `multi_select`, `measurement`, `boolean`. `photo`,
      `signature`, `asset_ref` and `user_ref` show a read-only "edit on the asset page" note (uploads and reference
      pickers come with ASSETS-05 / ITEMTYPES-04). Labels come from the field definitions, never hard-coded.
    - Save → `POST` or `PATCH` with `syncVersion`; 422 `ATTRIBUTES_INVALID` maps each `errors[].path` to its field;
      409 `VERSION_CONFLICT` shows a reload prompt. After create, go to `/assets?under=<parent>&created=<internalTag>`
      with a confirmation; "Save and add another" keeps the parent and item type and clears the rest.
  - 6. `MoveAssetDialog.tsx` (`Dialog` from `@aip/ui`): `ParentPicker` plus a "Move to top level" option; submits
    `POST /api/v1/assets/{id}/move {syncVersion, parentId}`. 422 `PATH_CYCLE` → `assets.error.PATH_CYCLE`
    ("An asset cannot be moved under itself or one of its own children"); 422 `ASSET_TREE_TOO_DEEP` and 409 are
    shown in the dialog. On success the tree reloads the old and new parents.
  - 7. `ParentPicker.tsx`: a `Combobox` searching `GET /api/v1/assets?q=` (limit 20) showing each option as its
    breadcrumb (`Site A > Unit 1 > P-101`); in the move dialog the moving asset and its subtree are excluded
    (`GET /api/v1/assets?under=<id>` ids filtered out; the server still refuses cycles).
  - 8. Terms: every visible string is a key in `config/terms/en-AU/assets.json` (`assets.register.*`,
    `assets.tree.*`, `assets.form.*`, `assets.move.*`, `assets.error.<code>`), mapped for `RegisterTable` in
    `terms.ts` the way `features/projects` maps its terms.
  - 9. e2e lanes: `e2e/web/assets.spec.ts` runs in the stub lane (dev server, list API answered by `page.route`);
    `e2e/web/assets-live.spec.ts` needs a real session, so add it to the `SKELETON` list in `e2e/playwright.config.ts`.
- **acceptance**:
  - `/assets` shows the tree and the register; selecting a node narrows the register to that subtree and the URL alone reproduces the view (tree selection, filters, sort, columns).
  - The tree is operable with the keyboard only and passes axe with no serious or critical violations, on desktop and mobile widths.
  - Create and edit forms are generated from the item-type version; server validation errors land on their fields.
  - Actions a user lacks permission for are not shown; the server still refuses them.
  - The CSV export holds the same rows as the register for the same query and the caller's permissions.
- **tests**:
  - **unit**:
    - Vitest `tree.test.tsx`: a tree with `Site A (childCount 2)` → ArrowRight expands and requests `parentId=<Site A>`; ArrowDown moves focus to the first child; ArrowLeft returns to `Site A`; the focused item is the only one with `tabIndex=0`; `aria-setsize` = 2 on the children.
    - `register.test.tsx`: `validateAssetsSearch({under: "<id>", sort: "-name", junk: "x"})` → `{under: "<id>", sort: "-name"}`; a user without `asset.move` sees no Move action; the export link carries `under` and `sort`.
    - `form.test.tsx`: a version with `diameter_mm` (number, required) and `service` (dropdown) renders a number input and a select with the definition's labels; a 422 `{errors:[{path:"attributes.diameter_mm",code:"required"}]}` shows the error under that field; the Tag Number check with a hit on another asset shows "Already used by P-101 (AT-…)".
  - **integration**:
    - pytest + testcontainers-python on `kaefer-demo` and `tenant-b`: with 7 assets under `Site A` and 3 elsewhere, `GET /api/v1/assets/export.csv?under=<Site A>` → 1 header row + 7 data rows, `path` like `Site A > Unit 1`; a name starting with `=` is neutralised as in the shared CSV vectors; 10,001 seeded assets → 422 `EXPORT_TOO_LARGE`; without `asset.view` → 403; as `tenant-b` → header only.
  - **e2e**:
    - Stub lane (`assets.spec.ts`, desktop-chromium, mobile-chrome, ipad-webkit): open `/assets`, expand `Site A` with the keyboard, select `Unit 1` → the register lists its 2 children and the chip shows "Within: Unit 1"; clear the chip → all rows; sort Name descending and copy the URL into a new page → same view; axe on the page and on the open move dialog → no serious or critical violations.
    - Live lane (`assets-live.spec.ts`, real sessions from `e2e/fixtures/login.ts` and `e2e/fixtures/tenants.ts`): a `kaefer-demo` admin creates `E2E-<runId> Site` and a child with Tag Number `E2E-<runId>-P1` through `/assets/new`, sees the child under the site in the tree, and a second create with the same Tag Number shows the "already used" message; a `tenant-b` admin opening `/assets/<child id>/edit` sees the not-found page and `GET /api/v1/assets/<child id>` from that page answers 404; the creator then deletes both assets so the demo does not fill up.
