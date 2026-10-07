# DESIGN-05 — Tenant accent theme + visual regression

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md) (the "Accent" bullet and the Data section: theme tokens per tenant)
3. ADRs: 0002 (migration, RLS), 0004 (layout, Playwright)

## Spec

Let each tenant set one accent colour and a default density, stored with RLS and applied server-side so there is no flash of the wrong colour. Accents that fail WCAG contrast are rejected. Add Playwright visual-regression baselines for the shell and the register in the default theme and the Kaefer theme.

- **files**:
  - db/migrations/<timestamp>_tenant_theme.sql
  - apps/api/src/modules/design/ (module.ts, api.ts, service.ts, controller.ts, schemas.ts, permissions.ts, manifest.json, tests/)
  - apps/web/src/app/layout.tsx (wiring only: apply the theme on `<html>`)
  - e2e/web/visual/shell-theme.spec.ts
  - e2e/web/visual/__screenshots__/
- **steps**:
  - 1. Scaffold `apps/api/src/modules/design` with `tools/new-module.ts design`.
  - 2. Write a migration for `tenant_theme`: tenant_id (PK, FK tenants), accent char(7), density (`compact|comfortable`), contrast (`standard|high`), updated_by, created_at and updated_at. Use FORCE RLS with the ADR 0002 policy. One row per tenant; a missing row means platform defaults.
  - 3. Add GET `/api/v1/design/theme` (any authenticated user) returning `{accent, accentForeground, density, contrast}` with defaults filled in (`#0f766e`, `compact`, `standard`). Add PUT `/api/v1/design/theme`, guarded by `design.theme.manage`. Validate with `isAccessibleAccent` from `packages/ui` (DESIGN-01). A failing accent returns 422 `ACCENT_CONTRAST` with the measured ratio. `accentForeground` is computed (white or near-black, whichever contrasts more). Emit `design.theme.changed`.
  - 4. In the root layout, fetch the theme server-side with the session cookie and set `style="--accent:…;--accent-foreground:…"`, `data-density` and `data-contrast` on `<html>` in the first byte. The login page uses the default theme, because the tenant is unknown there. Cache per tenant for 60s, and invalidate on PUT in the same process.
  - 5. Add a Playwright visual project with fixed viewport 1440×900, `prefers-reduced-motion`, the fonts awaited (`document.fonts.ready`), and a frozen clock and fixed seeded data. Take screenshots of the shell plus `/projects` for the default theme and for the Kaefer accent `#da291c`, plus the high-contrast variant. Compare with `toHaveScreenshot({maxDiffPixelRatio: 0.01})`. Generate the baselines in the CI Linux container only, never on a laptop, and document the update command (`pnpm e2e:visual --update-snapshots` in the container).
- **acceptance**:
  - The Kaefer admin sets `#da291c`, and every user in that tenant sees red accents on the next page load. Tenant B is unaffected.
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
