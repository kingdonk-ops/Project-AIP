# DESIGN-14 — Header brand lockup: company name followed by "AIP"

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | DESIGN-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. `apps/web/src/features/shell/Header.tsx`, `shell.css`, `session.ts`, `config/terms/en-AU/shell.json`

## Spec

Owner request (2026-10-14): the top-left corner shows the customer's company name followed by the word "AIP", for
example **Kaefer** AIP. The name is the tenant's display name, set when the tenant is provisioned and editable by the
tenant admin in tenant settings (TENANCY-05). Today the header shows the tenant name alone after an empty logo slot.

- **files**:
  - apps/web/src/features/shell/Header.tsx and shell.css
  - apps/web/src/features/shell/__tests__/Header.test.tsx
  - config/terms/en-AU/shell.json (`shell.brand.product` = "AIP"; `shell.brand.home` for the link's accessible name)
  - e2e/ shell spec
- **steps**:
  - 1. Render the lockup as one link to `/` (Home): optional tenant logo (the existing slot, empty until tenant
    branding has a logo), the tenant display name (semibold), then the product word from `shell.brand.product`
    (regular weight, muted). The link's accessible name reads "<Company> AIP, home".
  - 2. Truncate long company names with an ellipsis and show the full name in a tooltip; the product word never
    truncates. Under 768px, show the company name only if it fits beside the menu button, otherwise only "AIP".
  - 3. The product word is a terminology key so it can be renamed later without a code change; never hard-code it.
  - 4. Set the document title to `<page> · <Company> AIP`.
- **acceptance**:
  - Signed in as alice@kaefer.test, the top-left reads "Kaefer Demo AIP" (from the tenant's name) and links to Home;
    bob@acme.test sees his tenant's name.
  - A 60-character company name does not push the header controls off-screen at 1440px or 390px.
  - axe passes on all three Playwright projects; the terminology lint passes.
- **tests**:
  - **unit**:
    - Header with tenant name "Kaefer Demo" renders a home link named "Kaefer Demo AIP, home" (via terms).
    - A long name gets the truncation class and a tooltip with the full name.
  - **e2e**:
    - Desktop Chromium: both fixture tenants see their own name in the lockup; document title ends with "<Company> AIP".
