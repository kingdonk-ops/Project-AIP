# DESIGN-11 — Blade (slide-out detail), KPI strip and work-queue patterns

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-04, DESIGN-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/reviews/10-ui-modernization-guide.md`](../../docs/reviews/10-ui-modernization-guide.md) (rows 4 and 5.1)
3. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md) ("slide-over blade", "KPI strip", "Home: My Work")
4. `packages/ui/src/patterns/RecordDetail.tsx` and `packages/ui/src/feedback/` from DESIGN-04

## Spec

Three shared patterns the Home page (DESIGN-12) and later R1 registers assemble. Fixture-driven in `packages/ui`;
no backend. All text arrives as term keys or props.

- **files**:
  - packages/ui/src/patterns/Blade.tsx and Blade.test.tsx
  - packages/ui/src/patterns/KpiStrip.tsx and KpiStrip.test.tsx
  - packages/ui/src/patterns/WorkQueue.tsx and WorkQueue.test.tsx
  - packages/ui/src/patterns/patterns.css
  - packages/ui/src/index.ts
- **steps**:
  - 1. **Blade.** A right-hand slide-over (420px desktop, full width under 768px) on the Radix Dialog primitive:
    modal focus trap, Escape and the close button close it and return focus to the row that opened it. Slots:
    header (ID in mono, title, breadcrumb, StatusChip, permalink), optional banner (e.g. SLA escalation, using the
    status tones), body (scrolls), sticky action bar. The open record is URL-addressable (`?open=<id>`) so the
    permalink and Back work. No slide animation under `prefers-reduced-motion`.
  - 2. **KpiStrip.** A row of up to four compact metric tiles (`{labelKey, value, tone?, icon, hint?, onSelect?}`).
    A tile with `onSelect` is a toggle button (`aria-pressed`) used to filter the queue below it; a tile the user
    may not see renders a "restricted" state, never a blank or zero (blueprint rule). Danger tone uses the status
    colour on the number and icon, not a red fill.
  - 3. **WorkQueue.** A dense list on `RegisterTable` columns conventions: ID (mono), title with snippet, asset path,
    due tag (relative, with an explicit "overdue by Nh" in the danger tone and icon), StatusChip, and up to three
    inline quick actions passed in by the caller. Optional filter tabs (`role=tablist`) above it. Clicking a row (or
    Enter on it) calls `onOpen(id)`, which the caller wires to the Blade.
  - 4. Story-like fixtures in tests only (no Storybook): a queue of 8 mixed items, a strip of 4 tiles, an open blade.
- **acceptance**:
  - Keyboard only: Tab to a queue row, Enter opens the blade, focus is inside it, Escape closes it and focus is back
    on the row; the URL gained and lost `?open=`.
  - A KPI tile toggles the queue filter and announces its pressed state.
  - Overdue never relies on colour: icon and text are always present.
- **tests**:
  - **unit**:
    - Blade opens with `?open=ITP-0042`, traps focus, Escape closes and restores focus to the trigger.
    - KpiStrip tile with `restricted: true` renders the restricted term and no number.
    - WorkQueue item due 3h ago renders the "overdue by 3h" term and the danger icon; rows have accessible names.
    - vitest-axe on all three patterns (blade open) reports 0 violations.
  - **e2e**:
    - Covered through DESIGN-12's Home journey; no fixture page in apps/web.
