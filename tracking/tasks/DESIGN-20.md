# DESIGN-20 — Remaining raw selects, textareas and tables use the @aip/ui controls

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | DESIGN-18 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/DESIGN-18.md`](DESIGN-18.md) (step 4: `NativeSelect`, `Textarea`)

## Spec

DESIGN-18 added `NativeSelect` and `Textarea` to `@aip/ui` and moved the detail pages and forms onto them. The
dialogs and a few editors still hand-roll native controls with feature-local classes on `--border` (not the
`--border-strong` 3:1 control border). Move them onto the shared controls. Presentation only.

- **files** (found 2026-11-05):
  - apps/web/src/features/item_types/CategoryDialog.tsx, ContentTypeDialog.tsx, ItemTypeDialog.tsx, AttributeJsonEditor.tsx
  - apps/web/src/features/portal/GrantBuilder.tsx
  - apps/web/src/features/platform-events/DiscardDialog.tsx
  - apps/web/src/features/forms/RevisionCompare.tsx, TemplateUploadDialog.tsx, JsonInput.tsx; RevisionCompare,
    RevisionHistory and RevisionOutline use a raw `<table className="aip-table">` (switch to `Table`)
  - apps/web/src/features/assets/AttributeFields.tsx (select; the checkbox may move to `Checkbox` if behaviour allows)
  - the feature CSS classes these leave unused (`item-types-select`, `portal-admin__select`, `assets-form__select`, ...)
- **acceptance**:
  - No raw `<select>`, `<textarea>` or `<table>` in `apps/web/src/features` outside tests, except where a comment says why.
  - Existing unit and e2e tests stay green; axe passes.
- **tests**:
  - **unit**:
    - The touched dialogs' existing tests still find each control by its label.
