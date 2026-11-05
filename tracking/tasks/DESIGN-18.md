# DESIGN-18 — Every app page shows its content in panels on the canvas

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/DESIGN-09.md`](DESIGN-09.md) (Part A, step 2: Panel)
3. `packages/ui/src/components/panel.tsx`, `packages/ui/src/patterns/RecordDetail.tsx`, `packages/ui/src/components/components.css`

## Spec

DESIGN-09 gave the web app an off-white `--canvas` and a white bordered `Panel`, but only `RegisterTable` renders
inside one, so every page that is not a register shows its content straight on the canvas. Put those pages on
panels. Presentation only: no behaviour, route, label or API change. The login pages are out of scope (separate task).

- **files**:
  - packages/ui/src/patterns/RecordDetail.tsx and components.css (`aip-record__main` / `__rail`)
  - packages/ui/src/components/native-select.tsx and textarea.tsx (new), index.ts, matching tests
  - apps/web/src/routes/_app/index.tsx (Home placeholder)
  - apps/web/src/features/projects/ProjectCreateForm.tsx, assets/AssetForm.tsx, portal/InviteForm.tsx
  - apps/web/src/features/tenancy/PlanAndUsagePage.tsx, flags/FlagsPage.tsx, identity/ActiveSessionsPage.tsx,
    platform-events/EventDetailPage.tsx, assets/AssetsPage.tsx
  - apps/web/src/features/portal/PortalUserDetail.tsx, item_types/ContentTypeDetail.tsx, item_types/ItemTypeEditor.tsx
  - apps/web/src/features/forms/forms.css (drop the `#b42318` fallback)
  - e2e/web/panel.ts (new helper), project-detail.spec.ts, assets.spec.ts (canvas/panel assertion)
- **steps**:
  - 1. **RecordDetail.** The tab list and tab panel sit in one `Panel`; the rail is a column of `Panel`s, one per
    section (comments, approvals, attachments), replacing the muted rail box. This covers project, template,
    content-type, item-type and portal-user detail.
  - 2. **Forms.** Project create, asset create/edit and portal invite render their form inside a `Panel`; the page
    heading stays on the canvas above it.
  - 3. **Other pages.** Plan and usage (one Panel per section), release flags, active sessions, platform event
    detail (one Panel per version), the asset tree, and the Home placeholder.
  - 4. **Clean-ups.** The portal-user grants table uses `@aip/ui` `Table`. Add `NativeSelect` and `Textarea` to
    `@aip/ui` (native elements with the `.aip-input` look: `--border-strong`, `--control-h`, focus ring) and use
    them for the raw `<select>`/`<textarea>` in ContentTypeDetail, ItemTypeEditor, PortalUserDetail and
    ProjectCreateForm (and ProjectEditForm, the same field). `forms.css` uses `var(--status-danger)` with no hex
    fallback. The other dialogs' raw controls are DESIGN-20.
  - 5. **High contrast.** `--canvas` is white there, so `[data-contrast="high"] .aip-panel` takes `--border` (black);
    the `-subtle` tokens stay unset under high contrast, as DESIGN-09 requires.
- **acceptance**:
  - Every page under `apps/web/src/routes/_app/` shows its content in white bordered panels on the canvas, in light
    and high contrast.
  - axe passes on all three Playwright projects; no hex values outside `tokens.css`/`tokens.ts`.
- **tests**:
  - **unit**:
    - RecordDetail renders its tabs inside `.aip-panel` and each rail section as a labelled `.aip-panel` region.
    - `NativeSelect` and `Textarea` carry the `aip-input` class, take their accessible name from a `FormField`
      label, and vitest-axe reports 0 violations.
  - **e2e**:
    - Desktop Chromium: project detail shows the tab panel in an element with a 1px solid border and a white
      background on the canvas, in light and high contrast; the asset create form sits in the same kind of panel
      (the stub session has no `project.create`, so the project create form is covered by unit tests). Existing journeys stay green.
