# DESIGN-08 — Shell and register polish: mobile drawer backdrop, table overflow, login width, link buttons

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-03, PROJECTS-06 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`packages/ui`, Playwright projects)
4. `apps/web/src/features/shell/shell.css`, `packages/ui/src/components/components.css`, `packages/ui/src/register/RegisterTable.tsx`

## Spec

Found in a design review on 2026-10-14 (screenshots of `/projects` and `/login` at 1440×860 and 390×780). Four small
visual defects; fix them in the shared shell and `@aip/ui`, not per page. It depends on PROJECTS-06 so the projects
page is already on `RegisterTable` when the overflow fix lands.

- **files**:
  - apps/web/src/features/shell/shell.css
  - apps/web/src/features/shell/AppShell.tsx and NavRail.tsx (backdrop and close behaviour)
  - apps/web/src/features/shell/LoginPage.tsx (only if the width fix needs markup)
  - packages/ui/src/components/button.tsx and components.css
  - packages/ui/src/register/RegisterTable.tsx (and its CSS)
  - matching tests under `__tests__/` and `packages/ui/src/**/*.test.tsx`
  - e2e/ shell spec
- **steps**:
  - 1. **Mobile nav drawer.** Under 768px, the open rail sits over the page with no backdrop. Add a backdrop that dims
    the content and closes the drawer on click; Escape closes it and returns focus to the menu button; the drawer
    closes on navigation (already does). Respect `prefers-reduced-motion` if you animate it.
  - 2. **Register overflow.** At 390px the projects table runs off the right edge of the page. Wrap the
    `RegisterTable` table in its own horizontal scroll container (`overflow-x: auto`, keyboard focusable with an
    accessible name), so the page itself never scrolls sideways and the sticky header still works.
  - 3. **Login width.** On `/login`, the email input is wider than the Continue button. Make the input, hint and button
    share one width.
  - 4. **Link styled as a button.** "Create project" is a link with the primary button look but keeps the link
    underline. Make `Button` with `asChild` (or a `buttonVariants` class) render anchors without underline, with the
    same hover and focus ring as a button.
- **acceptance**:
  - At 390px: the drawer has a backdrop; clicking it or pressing Escape closes the drawer and focus returns to the
    menu button; `document.documentElement.scrollWidth` equals the viewport width on `/projects`.
  - On `/login`, the input and button have the same rendered width.
  - "Create project" shows no underline and has the 2px accent focus ring.
  - axe passes on all three Playwright projects.
- **tests**:
  - **unit**:
    - NavRail/AppShell: Escape and backdrop click close the drawer and restore focus to the menu button.
    - Button `asChild` with an anchor computes `text-decoration: none` and keeps the button classes.
  - **e2e**:
    - Mobile Chrome: open the menu, see the backdrop, close with Escape; `/projects` has no horizontal page scroll.
    - Desktop Chromium: `/login` input and button widths match.
