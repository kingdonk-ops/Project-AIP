# Issues, NCRs & corrective actions (`issues`)

- **Group:** Inspection & quality
- **Phase:** P1

What it is
Defects, non-conformances and the actions that fix them. Issues are raised against an asset, often from a failed inspection answer, then assessed, assigned, fixed, verified and closed. NCRs add root-cause analysis and corrective/preventive actions (CAPA). Each issue has severity, responsible person, due date, evidence and closeout proof.

What it does
It runs a shared workflow definition, auto-raises issues from failed inspection answers through configurable rules, and records NCR classification, root cause, disposition and CAPA. An open NCR can place a hold flag on the related ITP step and asset, which inspections must honour until closure. Subcontractors and clients see only items scoped to them.

Features
- Workflow: open > assessed > action assigned > in progress > ready for verification > verified > closed
- Admin-configurable issue types, severities (rank, SLA days, blocks ITP step) and workflows
- Auto-raise from inspection answers (for example Fail creates a high-severity issue), carrying source step, asset and photo
- NCR: material/workmanship/design, root cause (5-why or category), disposition (use-as-is, rework, repair, reject), CAPA
- Disposition workflow with engineering approval and sealed records
- Root cause categories and trend reports
- Corrective and preventive actions with owner, due date, status, evidence and linked task
- Per-issue attachments with photo markup
- Kanban by status and register list
- Overdue and SLA notifications with escalation, including overdue CAPA
- NCR hold flag on ITP step and asset
- Raise NCR from the v2 blade returns the asset to the defect backlog

Interactions
- Inspections, ITPs & hold points: raised from failed checks; hold flag honoured
- Asset hierarchy & registers: raised against an asset, with asset history
- Punch list & defects liability: snags versus formal NCRs; escalation
- Quality roll-up & audits: feeds cost-of-poor-quality
- Client & subcontractor portal: subcontractor responses
- Tasks: CAPA tasks; possible escalation to change orders or variations when rework has commercial impact

Data
Extend issues with issue_type_id, severity_id, source_inspection_id, source_response_id, itp_step_id, due_date, responsible_user_id, responsible_company_id, sync_version. Extend corrective_actions with kind (corrective or preventive), task_id, owner, due_date, status. New: issue_types (code, name, is_ncr, default_due_days), issue_severities, ncr_details (category, disposition, cost impact), root_causes. Overdue index on tenant and due_date where not closed. Portal scoping via responsible_company_id with RLS. Events consumed include inspection.answer_failed, punch.escalated, task.completed, portal.response_submitted.

Pages
- Issue register (/issues) with status pipeline filter
- Issue board (/issues/board)
- Raise issue (/issues/new)
- Issue detail (/issues/:id)
- NCR detail (/ncrs/:id) with root cause, disposition, CAPA, cost, ITP hold, related inspections
- CAPA board (/issues/capa)
- Admin settings for types, severities and rules

Decisions and notes
- Owner accepted all six suggestions listed above.
- Keep the status model shared with the workflow engine.
- Verifier should be independent; hold-ITP-step-on-NCR is a default setting.
- Terminology (Issue, NCR, Defect) is renamable.
- Built in AIP: issues and corrective actions CRUD. Deferred items are now accepted scope.

Open questions
- Which root-cause method is the default (5-why or fishbone) is not decided.
- Whether cost impact flows to qms cost-of-poor-quality and to variations in this phase is not decided.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
