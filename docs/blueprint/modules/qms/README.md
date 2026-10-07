# Quality roll-up & audits (`qms`)

- **Group:** Inspection & quality
- **Phase:** P2

What it is
Quality roll-up & audits sits in Inspection & quality (suggested phase P2, not yet built in AIP). It is a read-only quality overview across inspections, ITPs, NCRs (issues) and punch items, plus a small owned audit register for ISO 9001 internal audits. It is a reporting and audit view over existing records, not a competing data store.

What it does
Rolls up ITP completion, open NCRs, punch ageing, first-time pass rates, cost of poor quality and audit status live from source modules, with no copied data. Audit findings link to issues or corrective actions. Every KPI drills down to the underlying records. It writes only its own audit and related records.

Features
- Quality dashboard over existing records, with filters for project, site, discipline, subcontractor and period, trend charts, and a last-refreshed and data-definition note
- Internal audit register (internal, external, supplier audits) with findings linked to issues, closure verification and ISO 9001 clause mapping
- Cost of poor quality: rework hours and cost from issues, grouped by COPQ category, discipline, subcontractor and period
- First-time pass rate by discipline, inspector and subcontractor, with a defined denominator and exclusions (first submission, reinspection and withdrawn inspections counted consistently), the definition shown, and drill-down to failed inspections
- ISO 9001 clause-mapped evidence pack generator, assembling approved ITPs, NCR closures, calibration and competency records per clause without duplicating data
- Repeat-defect and root-cause trend view by asset class, coating system or CUI mechanism
- Audit sampling that pulls random closed inspections or hold points for internal audit
- Quality objectives and targets with RAG status per project, owned as small records
- Client-facing quality snapshot via the portal with fixed, approved KPIs, without exposing internal NCR detail
- Scheduled quality report distribution and notifications (audit scheduled, due, finding assigned or overdue, linked issue closed awaiting verification, audit closed, report ready)

Interactions
- Issues, NCRs & corrective actions: source data; findings raise or link issues
- Inspections, ITPs & hold points: source data
- Dashboards & KPI reporting: tiles reuse the reporting layer; tile layout lives there
- Rules engine and workflow engine: audit and finding workflows use the shared workflow engine; no duplicate status models
- Documents: completed audit checklists stored as documents

Data
- Owned tables: qms_audits (tenant, project, audit type, unique reference per tenant, title, scope, ISO clause refs, lead auditor, auditee company, asset, planned and conducted dates, status, checklist document, sync version, soft delete), audit findings (per-audit finding number, linked issue), management review, quality objectives, COPQ categories. All with tenant_id and RLS.
- Reuses assets, inspections, inspection_responses, issues, documents, disciplines, tasks.
- Roll-ups are read-only SQL views (for example first-time pass by discipline, inspector and subcontractor), created security_invoker so RLS applies, with supporting indexes on inspections (tenant, discipline, inspector, status).
- Config not code: COPQ categories and rework cost rates, KPI definitions and thresholds, audit types and checklists, finding severity scale, workflow definitions, ISO clause list, FTPR definition, cost source, tile layout.
- Events consumed: inspection.approved, inspection.rejected, issue.created, issue.closed, punch.item.closed, hold_point.released. Events emitted include qms.audit.scheduled, qms.audit.completed, qms.finding.raised.

Pages
- Quality dashboard at /projects/:projectId/quality
- Cost of poor quality report at /quality/copq
- First-time pass rate analysis at /quality/ftpr
- Internal audit register with create form, filters and detail (summary, scope and clauses, team, checklist and evidence, findings, closure, attachments, activity)

Access: quality.view; the inspector dimension needs quality.inspector_metrics and is limited to quality managers and above; COPQ needs quality.copq.view and cost rates are hidden from users without cost visibility; portal users see only shared tiles.

Decisions and notes
- Read-only roll-up only; no parallel data store (architecture, delivery manager and competitor advice agree).
- Phase P2 at most.
- All six scout suggestions were accepted by the owner and are included above.
- Differentiator: live roll-up from ITPs, NCRs and audits with COPQ and evidence packs, avoiding double entry, unlike document-centric QMS tools.

Open questions
- Whether COPQ cost source includes change orders or issues only (currently a setting, default not decided).
- Whether management review is built in the first release or deferred.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
