# DESIGN-16 — Mobile nav drawer behaves as a modal: focus trap, inert page, scroll lock

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | DESIGN-08 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (Playwright projects)
4. [DESIGN-08](DESIGN-08.md): the drawer backdrop, Escape and backdrop-click close, focus return

## Spec

Found in the DESIGN-08 review (PR #115, non-blocking): under 768px the open nav drawer dims the page like a modal,
but keyboard users can Tab into the dimmed page and the page behind still scrolls. Make the drawer a modal.

- **files**:
  - apps/web/src/features/shell/AppShell.tsx
  - apps/web/src/features/shell/NavRail.tsx (only if the trap needs it)
  - apps/web/src/features/shell/shell.css
  - apps/web/src/features/shell/__tests__/shell.test.tsx
  - e2e/web/shell.spec.ts
- **steps**:
  - 1. **Focus trap.** While the drawer is open, Tab and Shift+Tab cycle through the menu button (the drawer's
    toggle, which stays visible above the backdrop) and the rail links, and never leave them. Escape inside another
    layer (account menu, a dialog) is left to that layer, as in DESIGN-08.
  - 2. **Inert page.** The dimmed page (`.shell__body`, and the skip link that targets it) gets `inert` while the drawer
    is open, so neither Tab nor a screen reader's virtual cursor reaches it.
  - 3. **Scroll lock.** The document does not scroll while the drawer is open; the rail scrolls on its own when its
    links are taller than the viewport.
- **acceptance**:
  - At 390px with the drawer open: Tab from the last rail link goes to the menu button, Shift+Tab from the menu button
    goes to the last rail link; no element in the page behind can take focus; the page does not scroll.
  - Closing the drawer (Escape, backdrop click, menu button, navigation) removes `inert` and the scroll lock.
  - axe passes on all three Playwright projects.
- **tests**:
  - **unit**:
    - Drawer open: Tab from the last rail link wraps to the menu button, Shift+Tab wraps back; `.shell__body` is
      inert and the document is scroll-locked; both are cleared on close.
  - **e2e**:
    - Mobile Chrome: open the drawer, Tab through more stops than the drawer has and focus never leaves the drawer;
      the content is inert and `window.scrollY` stays 0 after a wheel scroll over the backdrop; axe passes.
