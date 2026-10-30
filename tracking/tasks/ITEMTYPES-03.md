# ITEMTYPES-03 — Content types and item types admin pages with JSON attribute editor and field preview

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`item_types`](../../docs/blueprint/modules/item_types/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-04, ITEMTYPES-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`ITEMTYPES-01.md`](ITEMTYPES-01.md) and [`ITEMTYPES-02.md`](ITEMTYPES-02.md) (the API these pages call)
3. [`docs/blueprint/modules/item_types/routes.md`](../../docs/blueprint/modules/item_types/routes.md) ("Content types", "Content type detail", "Item type editor"; the other pages are not this task)
4. [`DESIGN-03.md`](DESIGN-03.md) (register standard), [`DESIGN-04.md`](DESIGN-04.md) (RecordDetail, `confirm()`, toasts, states) and [`PROJECTS-06.md`](PROJECTS-06.md) (a register built on `RegisterTable`)
5. ADRs: [0018](../../docs/adr/0018-module-groups-and-navigation.md) (nav groups), [0025](../../docs/adr/0025-time-and-timezones.md) (local time only at presentation), [0036](../../docs/adr/0036-r1-module-decisions.md)

## Spec

Give tenant admins pages under `/admin/content-types` to manage content types, item categories and item types, and to edit an item type's draft attribute list as JSON beside a read-only field preview, then publish it (tag: extend).

All pages live under `/admin/content-types` (the blueprint's separate `/admin/item-types/:id` and `/admin/categories` pages are folded in as nested routes and tabs). The field preview is a read-only list of the attributes, **not** the FORMS-03 form renderer. Out of scope here: the attributes registry, status sets, starter packs, the versions diff and migration preview, the per-content-type register (ASSETS-06), and a visual attribute designer (ADR 0007: no designer in R1).

- **files**:
  - apps/web/src/features/item_types/nav.ts
  - apps/web/src/features/item_types/api.ts
  - apps/web/src/features/item_types/fieldTypes.ts
  - apps/web/src/features/item_types/attributes.ts
  - apps/web/src/features/item_types/ContentTypesRegister.tsx
  - apps/web/src/features/item_types/ContentTypeDialog.tsx
  - apps/web/src/features/item_types/ContentTypeDetail.tsx
  - apps/web/src/features/item_types/CategoryDialog.tsx
  - apps/web/src/features/item_types/ItemTypeDialog.tsx
  - apps/web/src/features/item_types/ItemTypeEditor.tsx
  - apps/web/src/features/item_types/AttributeJsonEditor.tsx
  - apps/web/src/features/item_types/FieldPreview.tsx
  - apps/web/src/features/item_types/item-types.css
  - apps/web/src/features/item_types/__tests__/attributes.test.ts
  - apps/web/src/features/item_types/__tests__/FieldPreview.test.tsx
  - apps/web/src/features/item_types/__tests__/ItemTypeEditor.test.tsx
  - apps/web/src/features/item_types/__tests__/ContentTypesRegister.test.tsx
  - apps/web/src/routes/_app/admin/content-types/index.tsx
  - apps/web/src/routes/_app/admin/content-types/$contentTypeId/index.tsx
  - apps/web/src/routes/_app/admin/content-types/$contentTypeId/item-types/$itemTypeId.tsx
  - apps/web/src/router.ts
  - apps/web/package.json (add `@aip/contracts` as a workspace dependency)
  - config/terms/en-AU/item_types.json
  - e2e/web/item-types.spec.ts
  - e2e/playwright.config.ts (add the spec to the skeleton lane)
- **steps**:
  - 1. `api.ts`: thin hooks over the generated `@aip/api-client` operations (`item_types_*`, `item_types_versions_*`); mutations invalidate the affected list and detail query keys. No hand-written fetch.
  - 2. `fieldTypes.ts` reads `@aip/contracts/field-types` (the ITEMTYPES-01 JSON). Labels come from each entry's `termKey`; the attribute picker and the preview offer only entries whose `usableIn` contains `attribute`.
  - 3. `nav.ts`: `registerNavItem({id: "content-types", section: "settings", to: "/admin/content-types", icon: "folder", termKey: "item_types.nav.title", permission: "item_type.manage"})` (ADR 0018: an entry in an existing group). The pages themselves need `item_type.view`; edit controls render only with `item_type.edit` / `item_type.manage`, Publish only with `item_type.publish`. The server still checks every call.
  - 4. `/admin/content-types` (`ContentTypesRegister`): `RegisterTable` from `@aip/ui` with columns name, key (mono), icon, sort order, in navigation, item types (`itemTypeCount`); quick filter "In navigation"; search on name or key. The API returns the whole list (≤ 50), so `useQuery` is an adapter that filters and sorts the fetched array in memory; the query state lives in the URL (`decodeRegisterQuery` / `encodeRegisterQuery`, as PROJECTS-06). Actions with `item_type.manage`:
    - Create opens `ContentTypeDialog` (key, name, icon from `iconNames`, show in navigation); 409 `CONTENT_TYPE_KEY_TAKEN` shows on the key field.
    - Move up / Move down per row call `PUT /content-types/order` with the new id order (keyboard reachable buttons, no drag).
    - Show / hide in navigation toggles `showInNav` with `syncVersion`.
    - Delete uses `confirm({tone: "danger", requireText: key})`; 409 `CONTENT_TYPE_IN_USE` shows an error toast with the category count.
    - Enter or click on a row opens the detail page; the empty state offers Create.
  - 5. `/admin/content-types/$contentTypeId` (`ContentTypeDetail` on `RecordDetail`): breadcrumb Content types › name, tabs `details|categories|item-types` in the URL (`?tab=`).
    - Details: the definition form (name, icon, show in navigation; key read-only), saved with `syncVersion`; 409 `VERSION_CONFLICT` shows DESIGN-04's "changed by someone else" state with Reload.
    - Categories: a table (name, key, applicable for, item types) with Add / Edit (`CategoryDialog`, applicable for Any / Item / Module as term keys) and Delete (409 `CATEGORY_IN_USE` → error toast).
    - Item types: a table (name, key, category, published version or "Not published", draft yes/no) with Add (`ItemTypeDialog`: category, key, name, description, is component, allows components); a row opens the editor.
    - Another tenant's id or a missing one renders DESIGN-04's `ErrorState` for 404.
  - 6. `/admin/content-types/$contentTypeId/item-types/$itemTypeId` (`ItemTypeEditor` on `RecordDetail`): tabs `details|schema|versions`; status chip "Published v{n}" or "Not published".
    - Details: the item-type definition form, as in step 5.
    - Schema: two panes, stacked below 768 px. Left, `AttributeJsonEditor`: a labelled monospace `<textarea>` holding the draft's `attributes` array, pretty-printed with 2 spaces. Buttons: Create draft (when none, copies the published version), Format, Save draft, Discard draft (`confirm`, danger), Publish (`confirm` with the change summary field). Without a draft the editor shows the published attributes read-only. Right, `FieldPreview` of the current editor text when it parses, otherwise of the last valid text, with the parse error shown above it.
    - Client checks in `attributes.ts` before any request: JSON parse errors with line and column; the value must be an array of objects; `fieldType` must be a known attribute field type; duplicate `key`. They are hints only: the server's 422 `ATTRIBUTES_INVALID` `issues` are listed under the editor, each `{path, code}` shown with its term key (`item_types.issue.<code>`) and the path in mono; selecting an issue moves the caret to that attribute in the text.
    - Unsaved edits: leaving the tab or page with changed text asks through `confirm()`.
    - Versions: the list from `GET .../versions` (version, status chip, published at in the viewer's local time, published by, change summary); choosing one shows its `FieldPreview` read-only.
  - 7. `FieldPreview`: an ordered, read-only list, one row per attribute: label, key (mono), field-type label, a "Required" chip, and for `measurement` the unit symbol and range ("0–100 mm"), for `decimal`/`number` the range, for `dropdown`/`multi_select` the option labels. Unknown field types render a warning row instead of failing. No inputs.
  - 8. Register the three routes in `apps/web/src/router.ts` under `appRoute`. All text comes from term keys in `config/terms/en-AU/item_types.json` (page titles, column headers, buttons, `applicable_for` values, issue codes, empty states).
- **acceptance**:
  - A tenant admin can, without the API docs, create a content type, a category and an item type, write a draft attribute list as JSON, see it previewed, fix a server-reported issue, and publish version 1.
  - A user with only `item_type.view` sees the pages read-only: no Create, Save, Delete or Publish controls.
  - Tabs and register filters survive a reload and a copied URL; every page has no axe violations at desktop and 390 px widths.
  - The preview never renders form inputs and never imports the form renderer package.
- **tests**:
  - **unit** (Vitest + Testing Library, API mocked at the client):
    - `parseAttributes('[{"key":"a","label":"A","fieldType":"text"}]')` → `{ok: true, attributes: [1 item], hints: []}`.
    - `parseAttributes('[{"key":"a",}]')` → `{ok: false, error: {line: 1, column: n}}` with `n` ≥ 1 (taken from the `JSON.parse` error, 1-based), and no hints.
    - `parseAttributes('{"key":"a"}')` → hint `item_types.hint.not_an_array`; two items with key `a` → hint `item_types.hint.duplicate_key` at index 1; `fieldType: "photo"` → hint `item_types.hint.field_type_not_allowed`.
    - `FieldPreview` with `[{"key":"wall_thickness","label":"Wall thickness","fieldType":"measurement","required":true,"config":{"unit":"mm","min":0,"max":100}}, {"key":"material","label":"Material","fieldType":"dropdown","config":{"options":[{"value":"cs","label":"Carbon steel"},{"value":"ss","label":"Stainless"}]}}]` → 2 list items in that order; the first shows "Wall thickness", "wall_thickness", "Measurement", "Required", "0–100 mm"; the second shows "Carbon steel" and "Stainless"; `container.querySelectorAll("input, select, textarea")` → 0. A `fieldType: "gps"` item → a warning row with `item_types.preview.unknown_field_type`.
    - `ItemTypeEditor` with a mocked 422 `{"code":"ATTRIBUTES_INVALID","issues":[{"path":"attributes[0].config","code":"ATTRIBUTE_CONFIG_INVALID"}]}` on Save draft → the issue list shows the `item_types.issue.attribute_config_invalid` text and `attributes[0].config`; the text is kept.
    - `ItemTypeEditor` with permissions `["item_type.view"]` → no Save draft, Create draft or Publish buttons; with `item_type.edit` but not `item_type.publish` → Save draft but no Publish.
    - `ContentTypesRegister` with 3 fetched content types and filter "In navigation" (2 match) → 2 rows; Move down on the first row calls `PUT /content-types/order` with ids `[b, a, c]`.
    - vitest-axe on the register, the detail page (each tab), the editor with a draft and with the issue list → 0 violations.
  - **integration**:
    - None beyond ITEMTYPES-01 and -02: this task adds no server code. `pnpm --filter @aip/web typecheck` and lint pass with the regenerated client.
  - **e2e** (`e2e/web/item-types.spec.ts`, Playwright skeleton lane on the compose stack: `loginAs` with `tenantUsers()`, keys suffixed with `runId()`; skipped on the `staging` project because published item types cannot be deleted and would fill the demo tenant):
    - Main journey as the `kaefer-demo` admin (A): open `/admin/content-types` from the Settings nav → Create content type `e2e_<run>` → it appears in the register → open it → Categories tab → add `piping_<run>` (Item) → Item types tab → add `pipe_spool_<run>` → open the editor → Schema → Create draft → paste the two-attribute list from the unit test but with `"unit":"in"` → Save draft → the issue list shows `attributes[0].config` → change the unit to `mm` → Save draft → the preview lists "Wall thickness" and "Material" → Publish with summary "first" → the status chip reads "Published v1" and the Versions tab lists v1 with today's date.
    - Cross-tenant: the `tenant-b` user (B) opens A's `/admin/content-types/<id>/item-types/<id>` URL → the not-found state, and B's in-page `fetch("/api/v1/item-types/<id>")` → 404; B's `/admin/content-types` register does not list `e2e_<run>`.
    - Axe (`@axe-core/playwright`) on the register, the content-type detail and the editor (Schema tab with the issue list showing) → 0 violations.

## Delivery notes (2026-10-30)

- **No API gaps.** The generated client already had every operation, including `PUT /content-types/order`, so it was not regenerated and no server code was added. Draft saves are `PATCH .../versions/{id}` in the API (the spec says "Save draft"; the method is the client's).
- **Publish dialog, not `confirm()`.** DESIGN-04's `confirm()` has no input field, so Publish opens a small dialog with the "Change summary" field. Discard, delete and leave-with-unsaved-text still use `confirm()`.
- **Publish needs a saved draft.** Publish is disabled while the editor text differs from the saved draft (a note says so), because the API publishes the stored draft, not the text.
- **Permissions as the API enforces them.** Content-type create, edit, reorder, show/hide and delete need `item_type.manage`; categories, item types and drafts need `item_type.edit`; Publish needs `item_type.publish`; the nav item needs `item_type.manage`.
- **Parse position.** V8 omits the position for some JSON errors (`{"key": }`), so `attributes.ts` falls back to a small scanner (`syntaxErrorOffset`) to report the line and column.
- **Pydantic 422s.** A body that fails the request model (e.g. an attribute without `fieldType`) is listed in the issue list as `item_types.issue.attribute_shape_invalid` with its `attributes[i].<field>` path, so the caret can still jump to it.
- **Field-type hint.** The editor lists the field types usable as attributes (from `@aip/contracts/field-types`) under the text area, so an admin can write the JSON without the API docs; there is no separate attribute picker (ADR 0007: no designer in R1).
- **e2e not run locally**: it needs the compose stack and Keycloak; it runs in CI lane `e2e-skeleton` (added to `SKELETON` in `e2e/playwright.config.ts`), tagged `@skeleton` only and skipped on `staging`.
