# DESIGN-07 — Keycloak login theme uses the design tokens and IBM Plex

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-01, IDENTITY-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md) (the "Accent" bullet)
3. ADRs: [0014](../../docs/adr/0014-ofl-fonts-allowed.md) (OFL fonts), [0005](../../docs/adr/0005-identity-architecture.md) (Keycloak themed pages)
4. `infra/keycloak/themes/aip/login/` and `packages/ui/src/tokens/tokens.css`

## Spec

Found in a design review on 2026-10-14. `infra/keycloak/themes/aip/login/resources/css/aip.css` still holds the
placeholder values written before DESIGN-01 merged (blue `#0b5cad`, the Inter font), and its own comment asks for it to
follow the `packages/ui` tokens. Users move from the app's teal and IBM Plex sign-in page straight to Keycloak's
password and MFA pages, so the jump is visible. Bring the theme in line with the tokens.

- **files**:
  - infra/keycloak/themes/aip/login/resources/css/aip.css
  - infra/keycloak/themes/aip/login/resources/fonts/ (IBM Plex Sans 400/500/600 woff2 and the OFL licence text)
  - infra/keycloak/themes/aip/login/theme.properties (only if the font stylesheet needs registering)
  - tools/ (a small check script, or a test under apps/api/tests, see step 3)
  - infra/ Dockerfile for the demo Keycloak image (only if the new font files need copying in; see OPS-11 fix PR #65)
- **steps**:
  - 1. Set the theme's custom properties from the DESIGN-01 tokens: brand `--accent` `#0f766e`, hover a darker step,
    surface `--surface-muted`, text `--foreground`, border and focus ring. Keep PatternFly's variables pointing at them.
  - 2. Self-host IBM Plex Sans in the theme (copy the woff2 files from `@fontsource/ibm-plex-sans`, keep the OFL
    licence file beside them) and drop Inter. No request may go to Google Fonts or any other external host, so the
    strict CSP stays possible.
  - 3. Add a drift check: a test that reads `tokens.css` and `aip.css` and fails if the shared colour values differ.
    Wire it into an existing CI job; do not add a new job.
  - 4. Per-tenant accent (Kaefer `#da291c`) is out of scope: the tenant is not known on Keycloak's pages until DESIGN-05
    or later decides how to pass it. Note this in the PR.
- **acceptance**:
  - Keycloak's password, OTP and passkey pages use the teal accent and IBM Plex Sans, with no external font request.
  - The drift check fails when a shared colour changes in only one of the two files.
  - The Keycloak flow tests and `tools/keycloak_messages.py --check` still pass; licence checks pass (OFL-1.1 is allowed).
- **tests**:
  - **unit**:
    - Drift check: equal colours pass; a changed accent in `tokens.css` alone fails.
  - **e2e**:
    - The password sign-in journey (TESTING-09) stays green; on the Keycloak page, the computed `font-family` starts
      with "IBM Plex Sans" and the primary button background is the accent.
