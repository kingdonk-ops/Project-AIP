# Design system & app shell (`design`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
The shared visual language and the constant frame every screen sits in. It is the Foundations & architecture module (suggested phase P0) and builds on the existing AIP Scope Portal design. Design tokens, a shadcn/ui based component library and a constant app shell (header, nav rail, scope bar) make every module look and behave the same. Labels always come from the terminology dictionary and are never hard-coded.

What it does
Provides IBM Plex Sans/Mono, a single tenant-themeable accent, dense desktop tables and large touch targets on mobile. It supplies the standard screen patterns other modules assemble (register, record detail, split-pane, blade, KPI strip, document viewer, execution screen, My Work home, dashboard). It guarantees accessibility and consistent feedback (dialogs, toasts, empty, loading and error states), including offline and sync-conflict variants. It offers a desktop office mode and a distinct field mode.

Features
- Tokens: colour, type scale, spacing, radii; status colours always paired with an icon or label.
- IBM Plex Sans for UI, IBM Plex Mono for tags and identifiers (established AIP convention).
- Accent as a single tenant-themeable token (teal #0f766e default in AIP; Kaefer red #da291c in the login brand).
- App shell: 56px header with project switcher, search, sync status, user; 56px nav rail; content varies per screen.
- Scope bar: tenant / organisation / project / asset-subtree pickers filtering every list and dashboard; the selected asset scope shows as a visible chip that clears with one click.
- Collapsible asset tree panel on register screens with open-item counts per node; selecting a node sets the asset scope.
- Register table standard: dense table, sticky header, column chooser, inline status chips, multi-select bulk actions, filter bar, quick-filter row (status, assignee, asset, date), optional split-pane preview, permission-respecting CSV export.
- Saved views with sharing (personal, team, project), default per role and URL-addressable filters so links in reports reopen the same view (accepted).
- Record detail: header with ID, title, asset breadcrumb and status; workflow bar showing current step and next allowed actions; tabs Details, Linked Records (traceability graph), Documents, History; persistent right rail with comments, approvals, attachments; superseding entries shown, never silent edits.
- Other patterns: split-pane tree + detail, slide-over blade, KPI strip (e.g. open NCRs, ITP completion %, overdue items, expiring certificates, PPC), configurable tile grid where each tile is a saved view, with a 'restricted' state instead of blank.
- Home: My Work prioritised queue with inline primary actions (Approve, Open, Sign), right column for expiring credentials and calibrations and a week calendar.
- Document and drawing viewer: three panes, markup toolbar (cloud, arrow, text, dimension, stamp), stamps and signatures showing who, when and document hash; 3D/IFC tab later.
- Inspection/ITP execution: step list with hold, witness and review points, eligibility banner for signer credentials, calibration and material expiry, signatory chips with auth strength.
- Command palette for jump-to asset, record and action, with recent items (accepted).
- Field mode: simplified shell with large next-action card, one-hand navigation and glove-safe controls (accepted).
- Compact density default with comfortable toggle; high-contrast outdoor theme for sun glare.
- WCAG 2.2 AA, 48px touch targets on mobile, every input reachable by its label.
- Real dialogs instead of window.confirm/prompt; animated non-blocking save toasts.
- Empty-state, loading and error patterns with offline and sync-conflict variants (accepted).
- Terminology lint in CI that fails on hard-coded user-facing strings (accepted).
- Automated accessibility and visual regression checks on the shared component library (accepted).
- Notifications: view shared, role default changed, saved view filter no longer valid, theme changed, sync conflict needs attention.

Interactions
- Terminology dictionary & localisation: all labels pulled from the dictionary.
- Dashboards & KPI reporting: KPI strip and tile styles, over a single permission-aware read model.
- Offline field app & sync: mobile shell, field mode and sync chip.
- Asset hierarchy & registers: tree + detail split view.
- Documents: viewer pattern and saved views.
- Comments/notifications platform service: right rail and My Work.

Data
- Theme tokens per tenant (accent, density, contrast theme, logo, login brand, field mode default).
- Per-project UI settings: field mode enablement, nav items and order per role/market.
- Saved views: owner, scope (personal, team, project), role default, filter definition addressable by URL.
- Recent items per user for the command palette (hard-deleted on user deactivation along with prefs).
- Column and density preferences per user.
- All tables carry tenant_id with RLS; view visibility is checked through the access policy service.
- Configuration, not code: accent, density, contrast, role default views, nav rail, KPI tile definitions, default columns, field mode enablement.

Pages
- Component library / style reference (/settings/design/style-reference).
- Tenant theme (/settings/design/theme) with live preview.
- Saved views management.
- App shell (header, nav rail, scope bar).
- Home: My Work (/).
- Reference layouts: register, record detail, split-pane, blade, dashboard, document viewer, ITP execution, field mode.

Decisions and notes
- AIP specs: design/scope-portal-inspection-scopes.md (v1 split view) and scope-portal-v2-unified-grid.md (KPI strip, WBS grid, 420px blade) are the pixel specs.
- Phase 1: shared tokens and the shadcn/ui library are built before screens.
- Architecture advice to use one read model, one comments service and one reporting module applies to what the shell consumes.
- Owner accepted all six scout suggestions: command palette with recent items; saved views; field mode; terminology lint in CI; accessibility and visual regression checks; empty, loading and error patterns.

Open questions
- Is v1 or v2 the Scopes screen?
- Status vocabularies differ between the two docs; which is canonical?
- Access-method vocabularies differ; which is canonical?
- Should Approve and Raise NCR mutate state in the Scopes screen?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
