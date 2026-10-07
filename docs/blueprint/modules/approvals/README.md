# Workflow & approvals engine (`approvals`)

- **Group:** Documents & records
- **Phase:** P0

What it is
The single state-machine and approval engine that every record type in the platform uses, so inspections, ITP sign-offs, issues and NCR closure, documents, POs, variations, invoices and submittals share one status model and one audit trail. It is built as a lightweight, data-driven engine (not Temporal or Camunda), seeded by generalising AIP's existing hardcoded inspection lifecycle. Suggested phase: P0. Module group: Documents & records.

What it does
Workflow definitions are data: states, transitions, required role, guard rule and side effects, per record type and optionally per project. Approval routes add ordered approver steps, delegation, thresholds and an approvals inbox. Presets cover inspections, issues, documents, POs, variations and invoices. Final document approval can burn an approval stamp onto the PDF. Commercial presets (invoices, POs, variations, BOQs) are delivered as a template pack and delegation matrix on top of the common engine, not as a second engine. Decisions are written back to the host record via approval.approved and approval.rejected events. Guards are evaluated server-side, and definitions are versioned so in-flight instances stay pinned to the version they started on.

Features
- workflow_definitions: states, transitions {from, to, action, required_role, guard}, side effects
- Per-project custom statuses, transitions and stage counts
- Approval routes: ordered steps, parallel or sequential (and conditional), delegation, thresholds, escalation on overdue steps with reminders
- Step approver can be a user, role or team, with a due time
- Approvals inbox with batch actions, inline document preview, approve and reject controls, and route visualisation
- Guards from the rules engine evaluated server-side; validation can act as a pre-submit gate
- Qualification guard on approver steps: a step can require the approver to hold a valid competency, linking to the eligibility gate
- Hash-chained transition and decision history recording auth strength and IP, with superseding entries
- Re-authentication or PIN confirmation on critical transitions such as hold point release and final sign-off
- Workflow definition versioning, with in-flight instances pinned to their version
- Delegation with date range and audit visibility, so the record shows who acted on whose behalf
- Instance timeline with delegate, reassign, recall and resubmit actions, history preserved
- Dry-run simulator: test a route against sample records before activating it
- Migration of the hardcoded inspection lifecycle onto the generic engine, mapping existing records to the new definitions and removing the scaffolding
- Preset templates: inspection review chain, issue lifecycle, document approval with stamp, PO approval, variation approval, invoice approval
- Authority matrix (role, entity, limit, currency) and delegation manager for value-threshold bands, out-of-office cover and workflow.escalated notifications
- Document approval: a new document version invalidates open approvals; the stamped PDF is saved as a new version

Interactions
- Rules & validation engine: transition guards
- Inspections, ITPs & hold points: review chain
- Issues, NCRs & corrective actions: issue lifecycle
- Document library & control: document approval, stamped PDF as new version; approval.completed promotes state and marks documents ready to issue, and can trigger an attested signature
- Supplier catalogue, requisitions & POs: PO approval, value read to choose the threshold band
- Variations and change orders: values read for threshold bands
- Audit trail, activity & timeline: transitions logged
- Users, projects and teams: approvers and scope
- Notifications: overdue steps, escalations and deadlines
- Competency and eligibility gate: qualification guard

Data
- Workflow definition (versioned): record type, optional project, states, transitions, guards, side effects
- Route template: entity type, conditions, threshold bands
- Step: approver user, role or team, order, parallel or serial, due time
- Instance: record reference, current step, state, pinned definition version
- Decision history: hash-chained, with comment, time, auth strength and IP
- Authority matrix: role, entity, limit, currency
- Delegation: from, to, dates, scope
- Stamp template

Pages
- Workflow settings page (existing scaffolding, to become the template designer)
- Template designer with dry-run simulator
- Approvals inbox (Documents and Records > Approvals Inbox)
- Instance timeline with delegate, reassign and recall
- Authority matrix editor and delegation manager
- Preset gallery for new projects
- Approval detail with stamp preview

Decisions and notes
- Build once as the core service; no separate engines for documents or commercial approvals.
- Definitions are data, so changes could bypass controls: version them, audit edits, restrict who can alter transitions and guards, and evaluate guards server-side.
- Commercial approvals must be visible only to the parties involved, so subcontractor teams never see others' commercial approvals.
- Accepted by the owner: lifecycle migration, definition versioning with pinning, re-authentication on critical transitions, dated delegation with audit visibility, dry-run simulator, qualification guard.
- AIP status: hardcoded inspection lifecycle and Workflow settings page built (TASKS 8.2); spec E4-S3/S4 and PRD 7.3.
- Terminology must be renamable per market.

Open questions
- None raised by advisors that conflict; the owner has not yet specified which transitions count as critical for re-authentication beyond hold point release and final sign-off.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
