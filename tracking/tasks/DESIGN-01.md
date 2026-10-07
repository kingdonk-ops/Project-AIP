# DESIGN-01 — Design tokens, ui package (Radix/shadcn), axe lint
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`packages/ui`, Vite apps, Vitest, Playwright, ESLint boundaries), [0001](../../docs/adr/0001-greenfield-python-backend.md) (TypeScript frontends, Python backend)

## Spec

Create `packages/ui`: design tokens with the accent as a single CSS variable, IBM Plex fonts, and a small set of Radix/shadcn-based primitives. Every component is checked by axe in unit tests and by jsx-a11y lint, so every later screen in the Vite apps (`apps/web`, `apps/field`, `apps/portal`) starts accessible. This task is frontend-only; nothing here touches `apps/api`.

- **files**:
  - packages/ui/package.json
  - packages/ui/src/tokens/tokens.css
  - packages/ui/src/tokens/tokens.ts
  - packages/ui/src/tokens/contrast.ts
  - packages/ui/tailwind-preset.ts
  - packages/ui/src/components/ (button, input, label, form-field, select, checkbox, combobox, dialog, dropdown-menu, tooltip, table, status-chip, badge, spinner, icon)
  - packages/ui/src/index.ts
  - packages/ui/eslint.config.mjs
  - packages/ui/vitest.config.ts
  - packages/ui/src/**/*.test.tsx
  - apps/web/src/routes/__fixtures/ui.tsx (dev-only fixture route for the e2e)
- **steps**:
  - 1. Create the package with an `exports` map, a TS project reference (extending `packages/config-ts`), React 19 as a peer dependency, Radix primitives, lucide-react, class-variance-authority and tailwind-merge. Build it as an ESM library with Vite library mode (or `tsc -b` plus copied CSS). Self-host fonts from `@fontsource/ibm-plex-sans` and `@fontsource/ibm-plex-mono` (400, 500, 600). Make no runtime request to Google Fonts, so a strict CSP stays possible.
  - 2. In tokens.css, define the CSS variables: neutral colour ramp, `--accent` (default `#0f766e`), `--accent-foreground`, status colours (success, warning, danger, info, neutral), type scale (12/13/14/16/20/24/30px), spacing on a 4px grid, radii (2/4/8px), and density variables (`--row-h` 32px compact and 40px comfortable). Add a `[data-contrast="high"]` outdoor theme and `[data-density="comfortable"]`. Mirror the values in tokens.ts for TS consumers. Expose them through the Tailwind preset; apps never hard-code hex values.
  - 3. In contrast.ts, write `contrastRatio(fg, bg)` (WCAG 2.x relative luminance) and `isAccessibleAccent(hex)`, which requires at least 4.5:1 against white text and the surface. DESIGN-05 reuses it.
  - 4. Copy the shadcn/ui components into `src/components` (do not depend on a shadcn runtime) and restyle them with the tokens. Touch targets are at least 32px in compact mode and 48px when `data-field` is set. Focus rings are always visible (`:focus-visible`, 2px accent). Components are plain client React (no server-component or Next.js-specific APIs such as `"use client"` directives or `next/*` imports).
  - 5. StatusChip takes `{tone, icon, label}` and always renders an icon plus visible text, never colour alone. It has no default label: the caller passes text from `t()`.
  - 6. Add an ESLint flat config extending `packages/config-eslint`, with `eslint-plugin-jsx-a11y` (recommended, as errors) and a `react/jsx-no-literals` rule for `packages/ui/src/components` (labels arrive as props). Wire `pnpm --filter @aip/ui lint` into the ARCH-03 CI job.
  - 7. Add Vitest (jsdom) with Testing Library and `vitest-axe`. Every exported component has one render test plus an axe test with no serious or critical violations. The test fails if a new export has no test (a test enumerates the `index.ts` exports against the test files).
- **acceptance**:
  - `pnpm --filter @aip/ui build test lint` passes on a clean checkout.
  - Changing `--accent` on `:root` restyles every accent use with no rebuild.
  - No component renders user-visible literal text. All of it arrives through props.
  - The package has no import from `apps/*` (the ESLint boundaries rule stays green).
- **tests**:
  - **unit**:
    - `contrastRatio('#0f766e','#ffffff')` returns 5.47 ±0.01. `contrastRatio('#da291c','#ffffff')` returns 4.87 ±0.01.
    - `isAccessibleAccent('#ffd400')` is false (about 1.4:1). `isAccessibleAccent('#0f766e')` is true.
    - `<StatusChip tone="danger" icon="alert" label="Rejected"/>` renders an svg with `aria-hidden="true"` and the text "Rejected".
    - `<Button>` with no accessible name fails the axe test. That fixture is expected to fail, which proves the gate works.
    - The Dialog opens, moves focus into the dialog, closes on Escape and returns focus to the trigger.
    - Every export in `index.ts` has a matching `*.test.tsx`; the enumeration test passes.
  - **integration**:
    - `pnpm -r build` with apps/web (Vite) importing `@aip/ui` and its `tokens.css`. Expected: 0 type errors (`tsc --noEmit`), and the built CSS in `apps/web/dist/assets/` contains `--accent:#0f766e`.
    - Add `<div onClick={...}>` with no role in a component and run lint. Expected: exit 1 with a jsx-a11y error.
  - **e2e**:
    - Playwright opens the dev-only fixture route `/__fixtures/ui` in apps/web (served by the Vite dev server; the route is not registered when `import.meta.env.PROD`) that renders all components. Expected: `@axe-core/playwright` reports 0 serious or critical violations, the computed `font-family` of the body starts with "IBM Plex Sans", and no request goes to `fonts.googleapis.com`.
