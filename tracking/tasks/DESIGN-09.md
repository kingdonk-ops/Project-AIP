# DESIGN-09 — Modernized surfaces: canvas/panels/chips + blade, KPI strip, work-queue

<!-- hand-edited: merged DESIGN-11 (Part B) per board re-draw 2026-10-17 -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-04, DESIGN-08 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/reviews/10-ui-modernization-guide.md`](../../docs/reviews/10-ui-modernization-guide.md) (sections 2.1 and 2.2 of the table, rows 4 and 5.1, the ADR conflicts and the contrast table)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`packages/ui`), [0014](../../docs/adr/0014-ofl-fonts-allowed.md)
4. `packages/ui/src/tokens/tokens.css` and `tokens.ts`, `packages/ui/src/components/components.css`, `status-chip.tsx`, `input.tsx`, `button.tsx`; and `packages/ui/src/patterns/RecordDetail.tsx` and `packages/ui/src/feedback/` from DESIGN-04

> Part A (was DESIGN-09) modernises the canvas, panels, status chips and inputs via tokens and shared components;
> Part B (was DESIGN-11) adds the Blade, KPI strip and WorkQueue patterns the Home page (DESIGN-12) assembles.
> Part B depended on DESIGN-09, so they are one task. Fixture-driven in `packages/ui`; no backend.

## Part A — canvas and panels, tinted status chips, input icons, button hierarchy (was DESIGN-09)

From the owner's UI modernization guide (2026-10-14). Content currently floats on a white page and status chips are
solid saturated blocks. Give the app an off-white canvas with white bordered panels, soften status chips to tinted
fills, and add a leading-icon slot to inputs. Change tokens and shared components only; pages pick it up for free.
It runs after DESIGN-08 (both touch `components.css` and `RegisterTable`) and before DESIGN-05, so the visual
baselines are taken once on the new look.

- **files**:
  - packages/ui/src/tokens/tokens.css and tokens.ts
  - packages/ui/src/components/components.css
  - packages/ui/src/components/status-chip.tsx (only if markup changes)
  - packages/ui/src/components/input.tsx
  - packages/ui/src/components/panel.tsx (new) and panel.test.tsx
  - packages/ui/src/register/RegisterTable.tsx (render inside `Panel`)
  - packages/ui/src/index.ts
  - apps/web/src/features/shell/shell.css (canvas background on the content area)
  - matching `*.test.tsx`
- **steps**:
  - 1. **Tokens.** Add `--canvas` (`--neutral-50`) and `--border-subtle` (`--neutral-200`) and use `--canvas` for the
    page/content background; `--surface` stays white for panels, header and rail. Add one tint per status tone:
    `--status-success-subtle #ecfdf5`, `--status-warning-subtle #fffbeb`, `--status-danger-subtle #fef2f2`,
    `--status-info-subtle #eff6ff`, `--status-neutral-subtle #f5f5f5`. Mirror them in `tokens.ts`. Under
    `[data-contrast="high"]` set `--canvas` to white and leave the `-subtle` tokens unused (see step 3).
  - 2. **Panel.** Add `Panel` (`<section>` with optional heading slot and actions slot): white surface, 1px
    `--border-subtle`, `--radius-lg`, no shadow. `RegisterTable` renders its filter bar and table inside one Panel.
    Panel borders are decorative; control borders (inputs, checkboxes, selects) stay on `--border-strong` for 3:1.
  - 3. **Status chips.** `StatusChip` uses the tint as background and the full-strength tone as text and icon, with
    a 1px border in the tone at low opacity (or none; pick one and note it in the PR). Under `[data-contrast="high"]`
    keep the current solid chips (owner confirmed 2026-10-14). The icon + label requirement stays.
  - 4. **Inputs.** `Input` takes an optional `icon?: IconName` that renders a 14px leading icon inside the 32px
    (`--control-h`) field, decorative (`aria-hidden`), with padding so text never sits under it. The FilterBar search
    uses `icon="search"`.
  - 5. **Accent discipline.** Write the rule at the top of `components.css`: the accent is for primary actions, focus,
    selection and links, never a surface fill. Fix any existing accent surface fill you find.
- **acceptance**:
  - `/projects` shows an off-white canvas with the register inside a white bordered panel at 1440px and 390px.
  - Every status chip renders a tinted background with tone-coloured text and icon; in high contrast the chips are
    solid as before.
  - The FilterBar search shows a leading search icon and keeps a 32px height.
  - axe passes on all three Playwright projects; no hex values outside `tokens.css`/`tokens.ts`.
- **tests**:
  - **unit**:
    - Each tone: computed contrast of `--status-<tone>` on `--status-<tone>-subtle` is at least 4.5:1 (read the
      values from `tokens.ts`).
    - `StatusChip` under `[data-contrast="high"]` uses the solid background class.
    - `Input icon="search"` renders an `aria-hidden` icon and the input keeps its accessible name from its label.
    - `Panel` renders a `section` with its heading as the accessible name.
    - vitest-axe on Panel, Input with icon and every StatusChip tone reports 0 violations.
  - **e2e**:
    - Desktop Chromium: `/projects` register sits inside an element with a 1px border and the body background is the
      canvas colour; axe passes. Existing shell and projects journeys stay green on all three projects.

## Part B — blade (slide-out detail), KPI strip and work-queue patterns (merged from DESIGN-11)

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
