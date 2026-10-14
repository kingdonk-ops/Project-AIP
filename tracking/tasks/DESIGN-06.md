# DESIGN-06 — Nav rail sections follow the ADR 0018 job-area menu

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/adr/0018-module-groups-and-navigation.md`](../../docs/adr/0018-module-groups-and-navigation.md)
3. [`docs/architecture/module-groups-and-navigation.md`](../../docs/architecture/module-groups-and-navigation.md) (the "Menu" block and the "Where every module surfaces" table)
4. `apps/web/src/features/shell/nav-registry.ts`, `NavRail.tsx` and `config/terms/en-AU/shell.json`

## Spec

Found in a design review on 2026-10-14. The nav rail still groups items by the original site-hierarchy sections
(`work`, `assets`, `quality`, `insight` from `docs/blueprint/03-site-hierarchy.md`). ADR 0018 (accepted 2026-10-10)
replaced those with the job-area menu, and the latest accepted ADR wins. Switch the rail's sections to the ADR groups
now, while only two modules (projects, audit) register items, so later module UI tasks register into the right groups.

- **files**:
  - apps/web/src/features/shell/nav-registry.ts
  - apps/web/src/features/shell/NavRail.tsx (only if the section rendering needs it)
  - apps/web/src/features/projects/nav.ts
  - apps/web/src/features/shell/__tests__/
  - config/terms/en-AU/shell.json
  - docs/blueprint/03-site-hierarchy.md (a pointer to ADR 0018 at the top; no other edits)
- **steps**:
  - 1. Replace `NAV_SECTIONS` with the ADR 0018 groups, in this order: `work-assets` (Work and assets), `quality`
    (Quality and compliance), `field` (Field and execution), `documents` (Documents and transmittals), `insight`
    (Insight), `settings` (Settings, permission-gated). Home stays the first item, above the groups or in its own
    unlabelled group; pick one and note it in the PR.
  - 2. Replace the `shell.nav.section.*` terminology keys to match, and delete the old keys no code uses.
  - 3. Move the existing registrations: Projects goes to `work-assets` for now (its final home, the scope-bar project
    switcher plus Settings > Organisation and projects, arrives with PROJECTS-03); any later item follows the
    "Where every module surfaces" table (for example Audit under `settings`).
  - 4. Make the type system enforce rule 2 of ADR 0018: `registerNavItem` accepts only the declared sections, so a
    module cannot add a top-level group. Add a JSDoc line on `NavSection` pointing at ADR 0018.
  - 5. Add a one-line note at the top of `03-site-hierarchy.md` saying ADR 0018 supersedes its nav sections.
- **acceptance**:
  - The rail shows groups in ADR 0018 order, with each group's accessible name from the new terminology keys.
  - Empty groups are still hidden, and items are still filtered by permission.
  - No label is hard-coded; the terminology lint passes.
- **tests**:
  - **unit**:
    - `visibleNavGroups` returns groups in ADR 0018 order and drops empty ones.
    - An item registered with an undeclared section fails typecheck (a `// @ts-expect-error` test).
  - **e2e**:
    - Existing shell journeys stay green on desktop Chromium, mobile Chrome and iPad WebKit; the axe check passes.
