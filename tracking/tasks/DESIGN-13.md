# DESIGN-13 — My display preferences page, with a choice of side panel or full page for record details

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-04, DESIGN-05, DESIGN-11, ACCESS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/routes.md`](../../docs/blueprint/modules/design/routes.md) ("My display preferences `/settings/design/preferences`")
3. [`docs/blueprint/modules/design/data-model.md`](../../docs/blueprint/modules/design/data-model.md) (`user_ui_pref`)
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (migration, RLS), [0004](../../docs/adr/0004-repository-layout.md)
5. `packages/ui/src/patterns/RecordDetail.tsx` (DESIGN-04), `Blade.tsx` and `WorkQueue.tsx` (DESIGN-11), `packages/ui/src/register/RegisterTable.tsx`

## Spec

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
    the DESIGN-05 presets, shown as swatches with a live preview. The section is hidden, and any stored choice is
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
