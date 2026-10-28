# DESIGN-17 — ProjectAIP master brand: favicon, app icon and co-branded lockups (A header, C portal footer)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-14 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`DESIGN-14.md`](DESIGN-14.md), `apps/web/src/features/shell/Header.tsx`, `shell.css`, `packages/ui/src/tokens/tokens.css`

## Spec

Owner brand files (2026-10-28, "Master brand — ProjectAIP" and "Client portal lockups"): the master brand is a green
(`#6bb23f`) rounded tile with white "AIP" (app icon at 112/64/40 px, favicon is the tile with "A" only) and the
wordmark "project" + green "AIP". Tenant-facing UIs use co-branded lockups: **A (badge)**, the client's name in their
own colour followed by the green AIP tag, at the top of the tenant app and the client portal; **C (endorsed)**,
"<Client> | [AIP] Powered by projectAIP", at the bottom of the client portal. Lockup B (icon first) is not used.

- **files**:
  - packages/ui/src/components/brand.tsx, brand.test.tsx, components.css, index.ts
  - packages/ui/src/tokens/tokens.css, tokens.ts (`--brand-green`, `--brand-on-green`, `--brand-ink`, `--tenant-brand`)
  - apps/web/public/favicon.svg, aip-icon.svg; apps/web/index.html
  - apps/web/src/features/shell/Header.tsx, shell.css, __tests__/Header.test.tsx
  - e2e/web/shell.spec.ts
  - tracking/tasks/PORTAL-03.md (portal header A + footer C)
- **steps**:
  - 1. `AipMark` draws the letters as SVG paths (no font dependency; a logotype, so not scored for text contrast) in
    three shapes: `icon`, `tag`, `letter` (favicon), plus a tile-less `plain` tone for the wordmark.
  - 2. `BadgeLockup` (A) and `EndorsedLockup` (C) take every word from the caller (terminology keys). The client's
    name uses `--tenant-brand`, which defaults to `--foreground` until DESIGN-05 sets the tenant colour.
  - 3. The web header lockup (DESIGN-14) becomes lockup A; the accessible name stays "<Company> AIP, home".
  - 4. `apps/web` links `/favicon.svg`. PORTAL-03 uses A in its header and C in its footer.
- **acceptance**:
  - The header reads "<Company> [AIP]" with the green tag; truncation, tooltip and narrow-screen rules from DESIGN-14
    still hold; axe passes.
  - The browser tab shows the green "A" favicon.
- **tests**:
  - **unit**:
    - `AipMark` is decorative, uses the brand tokens and contains no text; tag, letter and plain variants render.
    - `BadgeLockup` and `EndorsedLockup` read "<Company> AIP" / "Powered by projectAIP" and pass axe.
    - Header test: the lockup has the AIP tag with "AIP" for assistive tech.
  - **e2e**:
    - Brand lockup test sees the tag; `/favicon.svg` is linked and served as `image/svg+xml`.
