# TESTING-14 — Close review-13 test-proof gaps: real cross-tenant release flags, item-types axe at 390 px

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | DESIGN-15, ITEMTYPES-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. [`docs/reviews/13-merged-pr-review-2026-11-03.md`](../../docs/reviews/13-merged-pr-review-2026-11-03.md) (M4, M7)
4. ADRs: 0027

## Spec

Replace mocked or missing proofs with real ones (tag: harden). Never weaken, skip or quarantine an existing test.

- **files**:
  - e2e/web/release-flags-live.spec.ts (new, skeleton lane) and the header of e2e/web/release-flags.spec.ts
  - e2e/web/item-types.spec.ts, e2e/playwright.config.ts
- **steps**:
  - 1. **Release flags cross-tenant (M4).** Add a live-lane spec, like `assets-live.spec.ts` and listed in
    `SKELETON`, that switches a flag as tenant A's admin through the real API and reads tenant B's flags through the
    real API, asserting B is unchanged; reset the flag afterwards. Keep the mocked spec for UI states only and say so
    in its header.
  - 2. **Item types at 390 px (M7).** Run the item-types axe checks at a 390 px viewport as well as desktop (a second
    skeleton project or `page.setViewportSize`), asserting zero violations of any impact as the ITEMTYPES-03
    acceptance says; fix any violation found.
- **acceptance**:
  - Breaking tenant isolation on the flags API fails an e2e test.
  - The item-types pages have no axe violations at desktop and 390 px.
- **tests**:
  - **e2e**:
    - live: A switches a flag → B's flag unchanged (real API)
    - item-types pages at 390 px → 0 axe violations
