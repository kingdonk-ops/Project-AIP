# DESIGN-19 — Sign-in surfaces follow DESIGN-09: web login Panel on the canvas, Keycloak theme tokens

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-07, DESIGN-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/DESIGN-09.md`](DESIGN-09.md) (Part A and its delivery notes) and [`DESIGN-07.md`](DESIGN-07.md)
3. ADRs: [0005](../../docs/adr/0005-identity-architecture.md) (Keycloak themed pages), [0014](../../docs/adr/0014-ofl-fonts-allowed.md)
4. `apps/web/src/features/shell/LoginPage.tsx`, `shell.css`; `infra/keycloak/themes/aip/login/`;
   `tools/tests/test_login_theme.py`

## Spec

Found 2026-11-05 when the owner asked whether the login page matches DESIGN-09: it does not. DESIGN-09 (PR #237)
changed the tokens, shared components and the shell canvas, but neither the web sign-in page (last changed in
DESIGN-02) nor the Keycloak theme (DESIGN-07) picked the new look up, so the first two screens a user sees still have
the old flat look. Bring both in line.

- **files**:
  - apps/web/src/features/shell/LoginPage.tsx and `shell.css` (`.shell-login*`)
  - apps/web/src/features/shell/__tests__/shell.test.tsx
  - infra/keycloak/themes/aip/login/resources/css/aip.css (theme.properties only if a stylesheet needs registering)
  - tools/tests/test_login_theme.py
  - e2e/web/login.spec.ts, e2e/web/walking-skeleton.spec.ts
- **steps**:
  - 1. **Web login.** Put the heading and form in one `@aip/ui` `Panel` (white, 1px `--border-subtle`, `--radius-lg`,
    no shadow) on the `--canvas` page, named by its `h1`. The notice becomes a tinted strip: `--status-info` on
    `--status-info-subtle` (invited, signed out, expired) or `--status-danger` on `--status-danger-subtle` (failure),
    with its icon. Under `[data-contrast="high"]` the tint is dropped for white with a 2px outline in the tone, like
    the Blade banner. The email field takes a decorative leading icon (`Input icon=…`), as DESIGN-09 step 4 allows.
  - 2. **Keycloak theme.** Map `--canvas`, `--surface`, `--border-subtle`, `--border-strong`, every `--status-*` and
    `--status-*-subtle`, and the radii into `aip.css` the way DESIGN-07 maps `--accent`. The page is the canvas, the
    card (`.pf-v5-c-login__main`) a white panel with the hairline and no shadow, alerts tinted, form controls on
    `--border-strong`. Keycloak cannot see the app's contrast setting, so the high-contrast token values apply under
    `@media (prefers-contrast: more)`.
  - 3. **Drift check.** Extend `test_login_theme.py` to every new mapping and to the `prefers-contrast: more` values
    against `[data-contrast="high"]`, and fail if the accent fills anything but the primary button.
- **acceptance**:
  - `/login` shows the form in a white bordered panel on the off-white canvas, at 1440px and 390px; a failure shows a
    tinted danger notice with its icon; in high contrast the canvas is white and the notice outlined.
  - The Keycloak sign-in page shows the canvas, the white hairline card and the teal primary button; under
    `prefers-contrast: more` the canvas is white and the button the high-contrast accent.
  - axe passes on `/login` on all three Playwright projects in both contrasts, and on the Keycloak page.
  - The drift check fails when any shared value changes on one side only.
- **tests**:
  - **unit**:
    - The login form is inside a `section.aip-panel` named "Sign in"; the email input has an `aria-hidden` icon.
    - Signed-out and expired render an info notice, `error=failed` a danger alert, each with an `aria-hidden` icon;
      vitest-axe reports 0 violations.
    - Drift check: a changed `--canvas` or `--status-danger-subtle` in `tokens.css` alone, or a changed high-contrast
      canvas in `aip.css` alone, is reported.
  - **e2e**:
    - `login.spec.ts` (all three projects): panel border and background, canvas, notice colours in default and high
      contrast, 32px input with icon, axe.
    - `walking-skeleton.spec.ts` (`@skeleton @staging`): the Keycloak page's canvas, card hairline and accent, then
      the same under `prefers-contrast: more`, and axe.
