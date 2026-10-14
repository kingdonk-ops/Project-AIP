# DESIGN-09 — Canvas and panels, tinted status chips, input icons, button hierarchy

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-08 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/reviews/10-ui-modernization-guide.md`](../../docs/reviews/10-ui-modernization-guide.md) (sections 2.1 and 2.2 of the table, the ADR conflicts and the contrast table)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`packages/ui`), [0014](../../docs/adr/0014-ofl-fonts-allowed.md)
4. `packages/ui/src/tokens/tokens.css` and `tokens.ts`, `packages/ui/src/components/components.css`, `status-chip.tsx`, `input.tsx`, `button.tsx`

## Spec

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
    keep the current solid chips. The icon + label requirement stays.
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
