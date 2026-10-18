# DESIGN-12 — Home / My Work page (`/`) with work-item providers

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 (lands with R1) |
| Size | M |
| Depends on | APPROVALS-06, AUDIT-04, DESIGN-05, DESIGN-09, PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/reviews/10-ui-modernization-guide.md`](../../docs/reviews/10-ui-modernization-guide.md) (rows 4 and 5, and "Data the Home page needs")
3. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md) ("Home: My Work") and its `routes.md` entry for `/`
4. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md), [0018](../../docs/adr/0018-module-groups-and-navigation.md)
5. The approvals inbox API (APPROVALS-06) and the activity API (AUDIT-04)

## Spec

From the owner's UI modernization guide. Replace the placeholder home with the My Work page: saved views, a KPI
strip, the work queue and a side column, opening items in a blade. P0 has two real sources, approvals waiting on me
and recent activity in my scope; R1 modules add theirs (ITPs and inspections, NCRs, RFIs, punch items, expiring
calibrations and certificates) through a provider interface, so this page never imports a domain module.
PLAN-R1 must add one "register a My Work provider" step to each R1 module task that owns work items.

- **files**:
  - apps/api/aip/modules/design/ (or a `work` read-model module if PLAN-R1 decides so; record it in an ADR):
    `GET /api/v1/my-work` and `GET /api/v1/my-work/summary`, a `WorkItemProvider` protocol and the approvals provider
  - apps/web/src/features/home/ (page, views, side column)
  - config/terms/en-AU/home.json
  - tests next to each, and e2e/ home spec
- **steps**:
  - 1. `WorkItemProvider` returns `{id, code, kind, title, snippet, assetPath?, dueAt?, status, actions[]}` for the
    current actor and scope, permission-filtered and RLS-bound; `actions` are only those the policy service allows.
    The endpoint merges providers, sorts overdue first then by due date, and pages by cursor.
  - 2. Saved views on the toolbar: All my work, Overdue only, Awaiting my sign-off, plus one per registered kind.
    View and search are URL state. Fast search matches code, title and asset tag. A "Create" button opens a menu
    of the create actions providers declare (none in P0 beyond what approvals offers; hide the button if empty).
  - 3. KPI strip (DESIGN-11): Overdue, Due today, Awaiting my sign-off, Expiring certificates/calibrations. A tile
    with no provider yet shows the restricted/unavailable state, not zero.
  - 4. Layout: 8/4 split at 1280px and up, single column below. Main column: KPI strip, filter tabs, WorkQueue.
    Side column: "Expiring calibrations" (empty state until the equipment provider exists) and "Recent activity"
    from AUDIT-04.
  - 5. Row click goes through `useOpenRecord` (DESIGN-05 Part B), so it opens the Blade or the full page per the user's preference, with the item's summary from its provider and its quick actions (Approve/Reject in
    P0). Reassign/escalate and type-specific create dialogs belong to R1 module tasks.
  - 6. Home is the first nav item (DESIGN-06).
- **acceptance**:
  - A user with two pending approval steps sees both on `/`, the "Awaiting my sign-off" tile shows 2, and approving
    one from the blade removes it and decrements the tile.
  - Tenant B's user sees none of tenant A's items, and `/api/v1/my-work` never returns another tenant's row.
  - Tiles with no provider show the unavailable state; the page has no hard-coded labels.
- **tests**:
  - **unit**:
    - Merge order: overdue items first, then by `dueAt`, items without `dueAt` last.
    - A provider that raises is logged and skipped; the others still return (the page shows a partial-data notice).
  - **integration** (Testcontainers):
    - As alice in kaefer-demo with two pending steps: `GET /api/v1/my-work` returns 2; as bob in tenant-b: 0.
    - `summary` counts match the list for each tile.
  - **e2e**:
    - Desktop Chromium: open `/`, filter by the "Awaiting my sign-off" tile, open an item, approve, see the toast and
      the count drop. Cross-tenant check as bob. axe on desktop, mobile Chrome and iPad WebKit.
