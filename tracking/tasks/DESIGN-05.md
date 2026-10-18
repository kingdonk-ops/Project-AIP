# DESIGN-05 — Tenant colours and user display preferences (colours, density, side panel or full page) + visual regression

<!-- hand-edited: merged DESIGN-13 (Part B) per board slim 2026-10-18 -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited 2026-10-14: owner asked for company colours, preset palettes and a user colour choice (docs/reviews/10) -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | L |
| Depends on | DESIGN-03, DESIGN-04, DESIGN-09, ACCESS-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md) (the "Accent" bullet and the Data section: theme tokens per tenant)
3. ADRs: 0002 (migration, RLS), 0004 (layout, Playwright)

Part B (was DESIGN-13) also reads:

- [`docs/blueprint/modules/design/routes.md`](../../docs/blueprint/modules/design/routes.md) ("My display preferences `/settings/design/preferences`")
- [`docs/blueprint/modules/design/data-model.md`](../../docs/blueprint/modules/design/data-model.md) (`user_ui_pref`)
- ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (migration, RLS), [0004](../../docs/adr/0004-repository-layout.md)
- `packages/ui/src/patterns/RecordDetail.tsx` (DESIGN-04), `Blade.tsx` and `WorkQueue.tsx` (DESIGN-09), `packages/ui/src/register/RegisterTable.tsx`

> Part A (was DESIGN-05) and Part B (was DESIGN-13) depended on each other: the root layout applies the user's colour choice from Part B, and Part B offers Part A's presets. Both live in the `design` module under `/settings/design/*`, so they are one task.

## Part A — Tenant colours (company or preset), user colour choice switch + visual regression (was DESIGN-05)

### Spec

Let each tenant admin match the app to their company colours, either by picking one of the preset palettes or by entering their own brand colours, plus a default density, stored with RLS and applied server-side so there is no flash of the wrong colour. Accents that fail WCAG contrast are rejected. Add Playwright visual-regression baselines for the shell and the register in the default theme and the Kaefer theme.

- **files**:
  - db/migrations/<timestamp>_tenant_theme.sql
  - apps/api/src/modules/design/ (module.ts, api.ts, service.ts, controller.ts, schemas.ts, permissions.ts, manifest.json, tests/)
  - apps/web/src/app/layout.tsx (wiring only: apply the theme on `<html>`)
  - e2e/web/visual/shell-theme.spec.ts
  - e2e/web/visual/__screenshots__/
- **steps**:
  - 1. Scaffold `apps/api/src/modules/design` with `tools/new-module.ts design`.
  - 2. Write a migration for `tenant_theme`: tenant_id (PK, FK tenants), preset (text, nullable: a preset id or null
    for custom), accent char(7), header_bg char(7) nullable (null means the default white header), density
    (`compact|comfortable`), contrast (`standard|high`), allow_user_colours (bool, default true), updated_by,
    created_at and updated_at. Use FORCE RLS with the ADR 0002 policy. One row per tenant; a missing row means
    platform defaults.
  - 2a. **Presets.** Ship the palettes as data in `packages/ui/src/tokens/presets.ts` (id, terminology label key,
    accent, header_bg), each checked by a unit test: accent at least 4.5:1 against white and the canvas, and
    header text at least 4.5:1 on header_bg. Starting set (all measured against white): Teal `#0f766e` (default,
    5.47:1), Blue `#1d4ed8` (6.70), Navy `#1e3a8a` (10.36), Indigo `#4338ca` (7.90), Purple `#7e22ce` (6.98),
    Slate `#334155` (10.35), Green `#15803d` (5.02), Orange `#c2410c` (5.18), Red `#b91c1c` (6.47), Kaefer red
    `#da291c` (4.87). Each preset has a light header variant (white header, accent highlights) and a solid header
    variant (header_bg = accent, white text).
  - 3. Add GET `/api/v1/design/theme` (any authenticated user) returning `{preset, accent, accentForeground, headerBg, headerForeground, density, contrast, allowUserColours, presets}` with defaults filled in (`#0f766e`, `compact`, `standard`). Add PUT `/api/v1/design/theme`, guarded by `design.theme.manage`. Validate the accent and header colour with `isAccessibleAccent` from `packages/ui` (DESIGN-01). A failing accent returns 422 `ACCENT_CONTRAST` with the measured ratio. `accentForeground` is computed (white or near-black, whichever contrasts more). Emit `design.theme.changed`.
  - 4. In the root layout, fetch the theme server-side (and the user's colour choice from Part B when the tenant allows it; the user's choice wins) with the session cookie and set `style="--accent:…;--accent-foreground:…"`, `data-density` and `data-contrast` on `<html>` in the first byte. The login page uses the default theme, because the tenant is unknown there. Cache per tenant for 60s, and invalidate on PUT in the same process.
  - 4a. **Tenant theme page** `/settings/design/theme` (tenant admin, `design.theme.manage`): a grid of preset
    swatches with names, a "Custom company colours" option with hex inputs and a colour picker for accent and
    header, a live preview of the header, a primary button, a link, a selected row and a focus ring, the measured
    contrast shown next to each custom colour, a "Let users choose their own colours" switch, and Save / Reset to
    default. A failing colour shows the measured ratio inline and Save stays disabled.
  - 5. Add a Playwright visual project with fixed viewport 1440×900, `prefers-reduced-motion`, the fonts awaited (`document.fonts.ready`), and a frozen clock and fixed seeded data. Take screenshots of the shell plus `/projects` for the default theme and for the Kaefer accent `#da291c`, plus the high-contrast variant. Compare with `toHaveScreenshot({maxDiffPixelRatio: 0.01})`. Generate the baselines in the CI Linux container only, never on a laptop, and document the update command (`pnpm e2e:visual --update-snapshots` in the container).
- **acceptance**:
  - The Kaefer admin sets `#da291c`, and every user in that tenant sees red accents on the next page load. Tenant B is unaffected.
  - The admin picks the Navy preset and every user sees navy accents; turning off "Let users choose their own colours" makes users' personal choices stop applying.
  - An inaccessible accent (for example `#ffd400`) is rejected with the measured ratio, and nothing is stored.
  - There is no flash of the default accent on load for themed tenants: the server HTML already carries the variable.
  - The visual suite runs in CI and fails on an unintended change to shell or register styling.
- **tests**:
  - **unit**:
    - The service with accent `#da291c` returns `accentForeground` `#ffffff`. With `#ffd400` it throws `AccentContrastError` with a ratio of about 1.4.
    - GET with no stored row returns the defaults `{accent:'#0f766e', density:'compact', contrast:'standard'}`.
  - **integration** (Testcontainers):
    - As kaefer-demo, PUT `{accent:'#da291c'}`. Expected: 200. As tenant-b, GET. Expected: `#0f766e`.
    - PUT without `design.theme.manage`. Expected: 403, with the row unchanged and no `design.theme.changed` event.
    - As aip_app with no tenant set, `SELECT count(*) FROM tenant_theme`. Expected: 0.
    - The server-rendered HTML of `/projects` for a kaefer-demo session contains `--accent:#da291c` in the `<html>` style attribute.
  - **e2e** (Playwright):
    - The visual project matches the baselines `shell-default.png`, `shell-kaefer.png` and `projects-register-kaefer.png`. Changing `--row-h` in tokens.css by 2px makes `projects-register-kaefer.png` fail.

## Part B — My display preferences page, with a choice of side panel or full page for record details (merged from DESIGN-13)

### Spec

Owner request (2026-10-14): let each user choose how records open when they click an asset, item or row in a
register, queue or tree:

- **Side panel** (default): the slide-out Blade on the right; the list stays visible.
- **Full page**: navigate to the record's own detail page (RecordDetail), with Back returning to the list,
  including its filters, scroll position and selected row.

The choice lives on the blueprint's "My display preferences" page, stored server-side so it follows the user across
devices, next to the density and contrast settings that page already plans. Both modes render the same record
content: a module writes its detail body once and both containers host it.

- **files**:
  - apps/api/migrations/versions/<rev>_user_ui_pref.py (`user_ui_pref` per the data model, plus
    `detail_open_mode text not null default 'panel'` with a check `in ('panel','page')`, and `colour_preset text`
    nullable, null meaning "use my company's colours")
  - apps/api/aip/modules/design/ (module scaffold via `tools/new_module.py design` if not present; `GET/PUT
    /api/v1/design/preferences` for the current user only; tests)
  - packages/ui/src/patterns/open-record.tsx (new: `OpenRecordProvider`, `useOpenRecord()`) and its test
  - packages/ui/src/patterns/Blade.tsx (an "Open full page" action in the header)
  - packages/ui/src/register/RegisterTable.tsx and packages/ui/src/patterns/WorkQueue.tsx (row open goes through
    `useOpenRecord`)
  - apps/web/src/features/design-prefs/ (the `/settings/design/preferences` page and a query hook)
  - config/terms/en-AU/design.json
  - e2e/ preferences spec
- **steps**:
  - 1. **Table.** `user_ui_pref`: id, tenant_id, user_id, density, contrast_theme, column_prefs (jsonb),
    detail_open_mode, sync_version, timestamps, deleted_at; unique `(tenant_id, user_id)`; `FORCE ROW LEVEL SECURITY`
    with the ADR 0002 policy and an extra predicate so a user reads and writes only their own row.
  - 2. **API.** `GET /api/v1/design/preferences` returns stored values or defaults (`compact`, `standard`, `panel`).
    `PUT` validates with Pydantic, bumps `sync_version`, and needs no permission beyond being signed in. A user can
    never address another user's row (no user id in the path).
  - 3. **Open-record hook.** `useOpenRecord()` returns `open({type, id, href})`. In `panel` mode it sets `?open=<id>`
    and the Blade shows the record; in `page` mode it navigates to `href`. Under 768px it always uses the full page,
    because the panel would be full-screen anyway. Ctrl/Cmd-click and middle-click always open `href` in a new tab;
    rows stay real links so this works without script.
  - 4. **Shared content.** A record type registers one `DetailBody` component; the Blade and the RecordDetail page
    both render it, so the two modes never drift. The Blade header gains "Open full page" (to `href`).
  - 5. **Preferences page.** `/settings/design/preferences`, single-column form per routes.md: density, contrast
    theme, "Open records in" (radio: Side panel, Full page, each with a one-line description), reset columns, clear
    recents (disabled until recent items exist), and **Colours**: "Use my company's colours" (default) or one of
    the Part A presets, shown as swatches with a live preview. The section is hidden, and any stored choice is
    ignored, when the tenant admin has turned off "Let users choose their own colours". Users pick presets only, no
    free hex, so every choice is already contrast-checked. Save shows a success toast (DESIGN-04). Reachable from the user menu
    in the header. Density and contrast apply immediately via `data-density`/`data-contrast` on `<html>`.
  - 6. Load the preferences once in the session context so the first click already uses the saved mode.
- **acceptance**:
  - A user who picks "Full page" and clicks a project row lands on its detail page; Back returns to the register
    with the same filters and the row focused. Switching back to "Side panel" opens the Blade instead.
  - A user who picks the Purple preset sees purple accents; other users in the tenant keep the company colours.
  - The choice persists across sign-out and on another browser.
  - Another user, and another tenant, cannot read or change the preference (RLS and API).
  - Every label comes from terminology keys; axe passes on the preferences page and with the Blade open.
- **tests**:
  - **unit**:
    - `useOpenRecord` in `panel` mode sets `?open=P-0001`; in `page` mode navigates to `/projects/P-0001`; at 390px
      it navigates even in `panel` mode; Ctrl-click opens a new tab in both modes.
    - Preferences form: changing the radio and saving calls `PUT` with `detail_open_mode: "page"`.
  - **integration** (Testcontainers):
    - GET with no row returns the defaults; PUT then GET round-trips; `sync_version` increments.
    - Alice's PUT never changes another kaefer-demo user's row; as aip_app with no tenant set,
      `SELECT count(*) FROM user_ui_pref` returns 0; tenant-b sees none of kaefer-demo's rows.
  - **e2e**:
    - Desktop Chromium: set "Full page", click a project row, see the detail page, go Back to the same filtered list;
      set "Side panel", click the row, the Blade opens. Mobile Chrome: either setting opens the full page. Cross-tenant
      check as bob. axe on all three projects.
