# FORMS-11 — Form designer: palette, canvas and properties, live preview, lint as you go, save and publish

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: full spec written 2026-11-05 when the owner brought the designer into R1 (ADR 0043) -->

| Field | Value |
|---|---|
| Module | [`forms`](../../docs/blueprint/modules/forms/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-09, FORMS-03, FORMS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`FORMS-04.md`](FORMS-04.md) (the pages this extends: `apps/web/src/features/forms/`, `templateJson.ts`, `issues.ts`, `IssueList`, `TemplateDetail`) and [`FORMS-03.md`](FORMS-03.md) (`@aip/form-renderer`, its adapters and the dev fixture `apps/web/src/routes/__fixtures/form.tsx`)
3. The contract: [`packages/contracts/forms/form-template.schema.json`](../../packages/contracts/forms/form-template.schema.json) and [`packages/contracts/field-types/field-types.json`](../../packages/contracts/field-types/field-types.json); the API in `apps/api/aip/modules/forms/routes.py` and `schemas.py`
4. [`docs/blueprint/modules/forms/README.md`](../../docs/blueprint/modules/forms/README.md) and [`routes.md`](../../docs/blueprint/modules/forms/routes.md) ("Designer")
5. [`DESIGN-09.md`](DESIGN-09.md) (canvas, panels, chips, `Blade`) and [`DESIGN-04.md`](DESIGN-04.md) (`confirm()`, toasts, states)
6. ADRs: [0043](../../docs/adr/0043-form-designer-in-r1.md) (this task's scope and foundation), [0036](../../docs/adr/0036-r1-module-decisions.md), [0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md) (schemaVersion 2 section rules are kept as they are), [0018](../../docs/adr/0018-module-groups-and-navigation.md)

## Spec

Give template admins a visual designer at `/templates/$templateId/revisions/$rev/design` that builds a draft revision's sections and fields without writing JSON: a palette of the field types, a canvas to add, reorder and remove sections and fields (drag and drop or keyboard), a properties pane, a live preview through `@aip/form-renderer` at desktop and phone width, the server lint as you go, undo and redo, save and publish (tag: extend).

The designer edits the FORMS-01 contract and nothing else: what it saves is what the JSON upload would save, and the server lint is the check. Properties it cannot edit yet (`visibleIf`, `requiredIf`, `failWhen`, `rules`, `labelKey`, `helpKey`, `failMessageKey`, section `rules`) are kept unchanged and shown as "Logic set" chips; FORMS-12 adds their builders.

> **Out of scope:** the logic builder and test console (FORMS-12); calculated fields and repeating sections or grids
> (FORMS-07 and FORMS-08 add their own palette entries); print layout preview, report slot mapping, offline preview,
> the approval workflow, the section library inside the designer, the import assistant and the form settings page
> (BACKLOG, ADR 0043 point 5).

- **files**:
  - apps/api/aip/modules/forms/schemas.py (`RevisionReplace.expected_sync_version`)
  - apps/api/aip/modules/forms/service.py
  - apps/api/aip/modules/forms/tests/test_revision_replace_conflict.py
  - packages/api-client (regenerated)
  - apps/web/package.json (`@dnd-kit/core`, `@dnd-kit/sortable`, MIT)
  - apps/web/src/features/forms/designer/model.ts
  - apps/web/src/features/forms/designer/keys.ts
  - apps/web/src/features/forms/designer/history.ts
  - apps/web/src/features/forms/designer/Designer.tsx
  - apps/web/src/features/forms/designer/Palette.tsx
  - apps/web/src/features/forms/designer/Canvas.tsx
  - apps/web/src/features/forms/designer/PropertiesPane.tsx
  - apps/web/src/features/forms/designer/OptionsEditor.tsx
  - apps/web/src/features/forms/designer/PreviewPane.tsx
  - apps/web/src/features/forms/designer/LintPanel.tsx
  - apps/web/src/features/forms/designer/useLiveLint.ts
  - apps/web/src/features/forms/designer/designer.css
  - apps/web/src/features/forms/designer/__tests__/model.test.ts
  - apps/web/src/features/forms/designer/__tests__/keys.test.ts
  - apps/web/src/features/forms/designer/__tests__/Designer.test.tsx
  - apps/web/src/features/forms/TemplateDetail.tsx ("Open designer")
  - apps/web/src/features/forms/TemplateUploadDialog.tsx ("Start in designer")
  - apps/web/src/routes/_app/templates/$templateId.revisions.$rev.design.tsx
  - apps/web/src/router.ts
  - config/terms/en-AU/forms.json (a self-contained `forms.designer.*` block)
  - e2e/web/form-designer.spec.ts
  - e2e/playwright.config.ts (add the spec to the skeleton lane)
- **steps**:
  - 1. API: `RevisionReplace` takes an optional `expectedSyncVersion` (the template's `syncVersion`, as publish does). A mismatch → 409 `VERSION_CONFLICT`; a replace bumps the template's `sync_version` if it does not already. Regenerate `@aip/api-client`. No migration.
  - 2. `model.ts`: pure, immutable operations on a `FormSchema` (`@aip/form-renderer` types), each returning a new schema: `addSection(at)`, `addField(type, sectionKey, at)` (a type's defaults: `options` with one option for `dropdown`/`multi_select`, `unit` for `measurement`), `moveSection(key, to)`, `moveField(key, toSection, to)`, `removeSection(key)`, `removeField(key)`, `updateSection(key, patch)`, `updateField(key, patch)`, `changeFieldType(key, type)` (drops `options`, `unit` and `validations` the new type does not take; keeps logic) and `renameKey(old, new)` (rewrites every `{"var": old}` and `{"var": "old.…"}` in `visibleIf`, `requiredIf`, `failWhen`, field and section `rules`). A removal returns the keys still referenced by logic so the UI can warn. Unknown properties are kept.
  - 3. `keys.ts`: `keyFromLabel(label, taken)` → a contract key (`^[a-z][a-z0-9_]{0,62}$`; lower-case, non-alphanumerics to `_`, leading digit prefixed `f_`, de-duplicated with `_2`, `_3` across sections, fields and section rules, which share one namespace). A key follows its label until the user edits the key.
  - 4. `history.ts`: undo and redo over schema snapshots (at most 50; typing in one input within 1 s is one step). Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z.
  - 5. Route `/templates/$templateId/revisions/$rev/design` (`$rev` is the revision number). Load the template (`useFormsTemplatesGet`) and the revision by its id from the template's revision list (`useFormsRevisionsGet`). Not found, another tenant's id or an unknown `rev` → DESIGN-04's not-found state. Needs `form.view`; a draft is editable only with `form.manage`; a published or superseded revision, or a user without `form.manage`, opens read-only (no palette, inputs disabled, no drag) with "Edit as new draft" (`form.manage`, when no draft is open: `POST /templates/{id}/revisions` with that schema, then open the new draft's designer).
  - 6. Layout (DESIGN-09 canvas and panels): a toolbar (back to the template, code and name, revision chip, saved/unsaved state, Undo, Redo, view switch Design | Preview | JSON, Save draft, Publish), then three panes: `Palette` (the 12 field types from `@aip/contracts/field-types`, labelled `item_types.field_type.*`, plus "Section"), `Canvas`, and `PropertiesPane`. The lint panel sits under the canvas. At widths under 1024 px the palette and properties become `Blade`s opened from the toolbar.
  - 7. `Palette`: clicking a type adds it after the selected field (or at the end of the selected section, or of the last section) and selects it; dragging a type onto the canvas drops it at that position. `Canvas`: sections as panels (label, key in mono, field count) holding field rows (type icon, label, key in mono, "Required" and "Logic set" chips, lint issue count). Click or Enter selects; sections and fields reorder by drag (`@dnd-kit/sortable`, keyboard sensor on) and by Alt+ArrowUp / Alt+ArrowDown, and a field's "Move to section" menu moves it across sections. Delete (key or button) removes after `confirm()` when the item has fields or is referenced by logic (the message names the referencing keys). A section with no fields shows "Add a field" (the contract needs at least one field per section and one section).
  - 8. `PropertiesPane`: for a section, label and key; for a field, label, key, type (a `<select>` through `changeFieldType`), required, and by type: `OptionsEditor` for `dropdown`/`multi_select` (add, remove, reorder, value from label through `keyFromLabel`, values unique), unit for `measurement` (a `<select>` of the units the lint accepts), `min`/`max` for `number`/`decimal`/`measurement`, `minLength`/`maxLength` for `text`, `minItems`/`maxItems` for `multi_select` and `photo`. Logic properties show as read-only chips with their JSON behind a `<details>`. Editing a key runs `renameKey` and shows an inline error for an invalid or taken key without applying it.
  - 9. `PreviewPane` (view Preview): `FormRenderer` in editable mode on the unsaved schema, with local answers, the FORMS-03 fixture's in-memory adapters and a Desktop | Phone width switch (phone = a 375 px frame). "Reset answers" clears them. The JSON view shows the schema in FORMS-04's `JsonInput`; Apply parses it with `parseTemplateJson` and replaces the model as one undo step, or shows the parse error.
  - 10. `useLiveLint`: 800 ms after the last change, `POST /forms/lint` with the schema (a newer change cancels an older call). `LintPanel` reuses `issues.ts` and `IssueList` text; clicking an issue selects the section or field its path points to. Issue counts show on canvas rows. "No issues" is announced in a `role="status"`.
  - 11. Save draft (and Ctrl/Cmd+S): `PUT /forms/revisions/{id}` with `{schema, expectedSyncVersion}`. 200 → saved state, new `syncVersion`; 409 `VERSION_CONFLICT` → an error toast with "Reload" (keeps the local schema in the JSON view so nothing is lost); 422 `TEMPLATE_INVALID` → the issues in the lint panel. Leaving with unsaved changes asks first (router blocker and `beforeunload`).
  - 12. Publish (`form.publish`): disabled while there are unsaved changes or lint issues (the reason is shown); `confirm()` → `POST /forms/revisions/{id}/publish {expectedSyncVersion}` → success toast and the template detail page. 422 `TEMPLATE_INVALID` → the lint panel.
  - 13. Entry points: `TemplateDetail` shows "Open designer" on the open draft (`form.manage`) and "View in designer" on any revision in the history; `TemplateUploadDialog` gets "Start in designer", which creates the template with a starter schema (`schemaVersion: 2`, one section `section_1` "Section 1" holding one `text` field `field_1` "Field 1") and opens its v1 designer.
  - 14. All text from `forms.designer.*` (plus the existing `forms.*`, `forms.lint.*` and `item_types.field_type.*` keys) in `config/terms/en-AU/forms.json`.
- **acceptance**:
  - A template admin with `form.manage` and `form.publish` can, without writing JSON, start a template in the designer, add two sections, add a measurement field with a unit and a minimum, a dropdown with three options and a required boolean, reorder fields with the keyboard and by drag, preview it at phone width, see and fix a lint issue, save, and publish v1; the published schema passes `POST /forms/lint` and opens in INSPECTIONS-04 exactly as previewed.
  - A template uploaded as JSON with `visibleIf` and section `rules` opens in the designer, can be edited, and saves with that logic unchanged.
  - A user with only `form.view`, and anyone on a published revision, sees the designer read-only.
  - Two editors on one draft: the second save gets the conflict toast, not a silent overwrite.
  - Another tenant's template shows the not-found state; no serious or critical axe violations in any view; every call goes through the generated `@aip/api-client`.
- **tests**:
  - **unit** (Vitest + Testing Library, API mocked with MSW in front of the generated client):
    - `keyFromLabel("Surface Prep. (ISO 8501)", [])` → `surface_prep_iso_8501`; `"2nd coat"` → `f_2nd_coat`; `"Remarks"` with `remarks` taken → `remarks_2`; a 100-character label → 63 characters or fewer and valid.
    - `addField("dropdown", "prep", 1)` → a field at index 1 with one option; `addField("measurement", …)` has a `unit`; `moveField("dft_avg", "final", 0)` moves it across sections; `moveSection` reorders; `changeFieldType` from `dropdown` to `text` drops `options` and keeps `visibleIf`; `renameKey("surface_prepared", "surface_ready")` rewrites `{"var":"surface_prepared"}` in another field's `visibleIf` and in a section rule's `expr`; `removeField` of a referenced field returns the referencing keys; unknown properties survive every operation; no operation mutates its input.
    - History: three edits, undo twice, redo once → the second state; typing five characters within 1 s → one undo step.
    - `Designer` with a draft: clicking "Measurement" in the palette adds and selects a field; editing its label updates the key; Alt+ArrowDown moves it down; Delete on a referenced field asks first and names the referencing key; the preview shows the field and a required error after touching it; the phone switch renders a 375 px frame; the JSON view applies pasted JSON as one undo step and rejects invalid JSON with the line and column.
    - Lint: a change triggers one `POST /forms/lint` after 800 ms (fake timers), not one per keystroke; an issue at `["sections",0,"fields",1,"unit"]` selects that field when clicked and shows a count on its row.
    - Save sends `PUT` with `schema` and `expectedSyncVersion`; a mocked 409 shows the conflict toast with Reload; Publish is disabled while unsaved or while lint has issues, and after save with no issues sends `expectedSyncVersion` after confirm.
    - Read-only: with `["form.view"]`, or on a published revision, there is no palette, inputs are disabled and "Edit as new draft" shows only with `form.manage`.
    - axe (serious and critical) on Design, Preview and JSON views and on the read-only designer → 0 violations.
  - **integration** (`apps/api/aip/modules/forms/tests/test_revision_replace_conflict.py`, real Postgres via Testcontainers):
    - Replace a draft with the current `expectedSyncVersion` → 200 and a higher `syncVersion`; again with the old value → 409 `VERSION_CONFLICT` and the schema unchanged; without `expectedSyncVersion` → 200 (FORMS-04's upload keeps working); tenant B replacing tenant A's draft → 404.
  - **e2e** (`e2e/web/form-designer.spec.ts`, skeleton lane on the compose stack, `@skeleton`, `loginAs` with `tenantUsers()`, codes suffixed with `runId()`; not `@staging`, as FORMS-04):
    - Main journey as the `kaefer-demo` admin (A): `/templates` → Upload template → Start in designer (code `e2e-dsg-<run>`) → add a section "Final", add a Measurement "DFT average" with unit `um` and minimum 250, a Dropdown "Blast standard" with options Sa 2, Sa 2.5 and Sa 3, a required Boolean "Surface prepared" → move "Surface prepared" up with Alt+ArrowUp → Preview at phone width shows the three fields; entering 200 shows the minimum error → Save → lint shows no issues → Publish v1 → the template page shows v1 Published, and its outline lists the fields in the designed order.
    - Cross-tenant: the `tenant-b` user (B) opens A's designer URL → the not-found state.
    - Axe (`@axe-core/playwright`, serious and critical) on the designer in Design and Preview views and on B's not-found page → 0 violations.
