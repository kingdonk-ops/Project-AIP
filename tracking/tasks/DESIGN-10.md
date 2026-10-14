# DESIGN-10 — Scope bar as a breadcrumb (tenant › organisation › project › asset)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-09, PROJECTS-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/reviews/10-ui-modernization-guide.md`](../../docs/reviews/10-ui-modernization-guide.md) (row 2.2.3)
3. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md) (the "Scope bar" bullet)
4. `apps/web/src/features/shell/ScopeBar.tsx`, `AppShell.tsx`, `config/terms/en-AU/shell.json`, and the project
   switcher PROJECTS-03 added to the header

## Spec

From the owner's UI modernization guide. The scope bar is a row of floating chips. Make it one full-width bar under
the header showing the scope as a breadcrumb, `Tenant › Organisation › Project › Asset`, where each level after the
tenant is shown only when set. The blueprint rule still holds: the asset scope is visible and clears with one click.

- **files**:
  - apps/web/src/features/shell/ScopeBar.tsx and shell.css
  - apps/web/src/features/shell/__tests__/ScopeBar.test.tsx
  - config/terms/en-AU/shell.json
  - e2e/ shell spec
- **steps**:
  - 1. Render the bar as `<nav aria-label={t("shell.scope.label")}>` with an ordered list; separators are
    decorative (`aria-hidden`); the last segment has `aria-current="location"`.
  - 2. Each segment shows its kind (muted, from terminology) and its name; project codes and asset tags in IBM Plex
    Mono. Organisation shows only once TENANCY-03 supplies it; leave the prop optional.
  - 3. Project and asset segments have a clear button (`aria-label` from terms, e.g. "Clear project scope") that
    widens the scope by one level. Clicking a parent segment does the same as clearing everything below it.
  - 4. The bar is 32px high, white, with a bottom hairline (`--border-subtle`), and truncates long names with the
    full name in a tooltip. At 390px it scrolls horizontally inside itself, never the page.
- **acceptance**:
  - With a project selected the bar reads "Tenant › Project" as one breadcrumb; clearing the project leaves only the
    tenant and the registers widen to tenant scope.
  - Screen readers hear a navigation landmark named by the scope label with the current level marked.
  - No hard-coded labels; axe passes on all three Playwright projects.
- **tests**:
  - **unit**:
    - Tenant only: one item, `aria-current="location"` on it, no clear buttons.
    - Tenant + project + asset: three items in order; clicking "clear asset" calls `onScopeChange` with the project
      scope; clicking the tenant segment clears both.
  - **e2e**:
    - Desktop Chromium: pick a project in the header switcher, the breadcrumb shows it, clear it, the projects
      register shows tenant scope. Mobile Chrome: no horizontal page scroll with long names.
