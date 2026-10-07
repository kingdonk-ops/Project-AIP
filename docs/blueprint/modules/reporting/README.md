# Dashboards & KPI reporting (`reporting`)

- **Group:** Reporting, search & AI
- **Phase:** P3

What it is
Dashboards, KPI tiles and reports for projects and portfolios, built on one permission-aware read model. It is the single reporting module: separate dashboard, dashboards, bi_dashboards and project_intelligence variants are dropped in favour of this one read model. It is targeted at inspection and asset condition (ITP completion, NCR trends, CUI findings, handover readiness by asset) rather than generic cost and schedule reporting, where incumbents such as Procore Analytics, ACC Insight, Aconex, Unifier and InEight are strong. The Dependencies on boq and bim_hub are dropped in v1 and replaced with asset, inspection, NCR and commercial sources.

What it does
One read model (materialised views or snapshots refreshed by jobs) serves every dashboard and report, filtered by the viewer's permissions in the read query. Project and portfolio dashboards show a KPI strip (active scopes, earned vs planned hours, QA/QC backlog, pending client review, ITP completion, expiring certificates) and a configurable tile grid where each tile is a saved view that drills into its register. It also provides an asset-tree heatmap, nightly KPI snapshots with trends, CUI/NDT finding analytics, a handover readiness score, report templates with immutable generated outputs, and scheduled digests and threshold alerts.

Features
- KPI strip and configurable tile grid (drag/resize canvas)
- Each tile is a saved view; click drills into the filtered register
- Tiles show 'restricted' rather than blank when the user lacks access
- Asset hierarchy heatmap of status by area
- Earned vs planned hours, ITP completion, open NCRs, overdue, expiring
- Custom dashboards per user/role (AIP has these)
- Nightly KPI snapshot table with trend charts (week-on-week QA backlog, CUI findings, period comparisons)
- CUI and NDT finding analytics by asset, coating or insulation system, severity and area
- Handover readiness score per asset subtree, combining ITP completion, open NCRs, certificates and documents
- Report templates with parameters, preview and branded layouts; generated outputs are immutable with a content hash and stored in documents
- Priority templates: inspection reports such as ITP completion by asset subtree
- Actions: generate, schedule, sign off, export PDF/Excel
- Threshold alerts and subscription digests per role (for example expiring certificates, overdue hold points)
- Scheduled email digests and scheduled PDF/Excel distribution with recipients and run history
- CSV/Excel export respecting permissions, with spreadsheet formula injection neutralised
- Read-model parity tests proving dashboard counts equal register counts under each role

Interactions
- Search, retrieval & saved views: saved views behind tiles
- Roles, permissions & teams: permission filtering at query time, including exports and digests
- Scopes of work (RSW), disciplines & tasks: planned and earned value (PV/EV)
- Inspections, ITPs & hold points: completion
- Issues, NCRs & corrective actions: backlog and trends
- Also reads punchlist, RFI, submittals, deadlines, safety, procurement, certificates and the asset hierarchy through the shared read model
- Documents: stores generated reports; notifications or transmittals send them; signing uses the shared workflow engine

Data
- KPI snapshot: date, scope, metric, value
- Report template
- Generated report: parameters, file, content hash
- Saved view definitions (from search module)
- Dashboard and tile configuration per user/role
- Read model carries permissions or is filtered by them so materialised views never bypass RLS

Pages
- Project and portfolio dashboards (KPI strip, tile grid, heatmap)
- Trend views from snapshots
- CUI/NDT analytics
- Handover readiness by subtree
- Template library
- Report builder with preview
- Run history with distribution

Decisions and notes
- AIP status: Dashboard page (TASKS section 9.2) and custom Dashboards (section 46) are built. Deferred: drag/resize canvas, about 15 more widget types, per-widget filters, recent-activity widget.
- Materialised views refreshed by jobs are adequate at 5,000 users; no separate warehouse until dashboards prove slow.
- Permissions are enforced on every aggregate, export and digest so counts never leak.
- Generated reports are immutable and hashed because issued reports become evidence.
- Owner accepted all six scout suggestions listed under Features.
- Scope is the vertical asset-centric ITP and traceability pilot for Kaefer; anything not demonstrable in the pilot is not MVP.
- Terminology must be renamable per market.
- Suggested phase P2.

Open questions
- Whether embedded BI connectors or governed datasets and external-BI access are wanted at all (seen in market, not accepted).
- Weights and formula for the handover readiness score are not defined.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
