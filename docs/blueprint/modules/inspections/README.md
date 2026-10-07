# Inspections, ITPs & hold points (`inspections`)

- **Group:** Inspection & quality
- **Phase:** P1

What it is
The central execution record of the platform. An inspection is a template (pinned to a revision) filled in against an asset. ITPs and RFIs are inspection kinds whose hold points gate downstream tasks until released. Inspections move through a full review chain with RBAC at every step, can need client sign-off, can be scheduled with customers and inspectors notified, and can recur on calendar, certificate-expiry or issue triggers. It is the flagship module and is built on the shared workflow and form engines, with a single inspection record model that other quality modules reference.

What it does
Templates drive the questions. ITP steps carry hold, witness, review and surveillance points linked to real scope tasks and assets. Holds block downstream tasks until released; witness points notify with a notice period and waiver rule; surveillance is sampled. Sign-off is multi-party, recorded as immutable events with identity, auth strength and document hash, and an eligibility check (signer credentials, instrument calibration, material use-by) runs before each step. Failed answers raise issues. Approval generates a report. Corrections are superseding entries, never edits.

Features
- Lifecycle: draft > assignable > assigned > in progress > inspector review > supervisor review > [client review] > completed; reject/resend; re-inspect
- ITP steps with hold, witness, review and surveillance points linked to scope tasks
- Point-type-aware behaviour: hold blocks, witness notifies with notice period and waiver rule, surveillance sampled
- Inspection notice and waiver workflow: timers, reminders, recorded waiver if the client does not attend
- Release-to-proceed record for holds: signed, sealed, tied to the hold and downstream tasks
- Multi-party sign-off: row of signatory chips showing auth strength
- Eligibility banner before each step
- Customer/inspector scheduling: calendar, invitations, reminders, reschedule
- Inspection programmes: frequency, next due date, triggers (calendar, certificate expiry, issue, ad hoc)
- Inspection Register across assets with filters, bulk assign/approve/reject/reschedule/export
- Review queue with next/previous and bulk actions
- Competency-aware assignment suggestions (valid qualifications and availability); notification on assignment
- Inspection coverage and backlog dashboard (percentage of required inspections done per RSW, area or discipline)
- Autosave, discard, full-page view, related inspections grouped by discipline
- Design-side supervision visits and observations (from site_supervision)
- Generate report on approval

Interactions
- Form & template designer: template drives the questions
- Asset hierarchy & registers: run against an asset
- Scopes of work (RSW), disciplines & tasks: tasks spawn ITPs and inspections; hold gating enforced in task completion
- Certificates, competency & calibration gate: checked before signing
- Issues, NCRs & corrective actions: failed answers raise issues; open NCR can hold an ITP step
- Workflow & approvals engine: review chain
- Report engine & published records: PDF on approval

Data
Extend existing inspections with template_revision_id (pinned), kind, programme_id, itp_parent_id, sync_version, client_review_required. inspection_responses stays append-only; current value is the latest row per inspection and field via a view, with client_id for idempotent push. New: itp_steps (seq, point_type, acceptance_criteria, task_id, blocks_task_id, child_inspection_id, status pending/ready/in_progress/released/waived/rejected, hold_flag_issue_id, released_at, notice_hours), signoffs, bookings, programmes. Lifecycle is a workflow definition; point types, notice periods, reminder offsets and programme rules are configuration.

Pages
- Inspection register (/inspections) with saved views and board toggle; calendar toggle and asset tree filter
- Create inspection wizard (/inspections/new)
- Inspection detail (/inspections/:id): header and workflow bar, eligibility banner, answers, ITP steps, sign-off chips, linked tasks, evidence, issues, bookings, related inspections, review history, report, audit trail
- Review queue (/inspections/review)
- ITP progress timeline with point-type badges

Decisions and notes
- Owner: full ITP system linked to actual tasks, sign-off, notifications, alerts, customer/inspector scheduling, multi-party sign-off.
- Owner accepted all six feature suggestions listed above.
- Build first, in phase 1, and have other quality modules reference its records.
- Built in AIP: full lifecycle, re_inspect, concurrent inspections, Register, Workflow settings, ITP/RFI template kinds, lifecycle tests. Deferred: inspection_programs scheduling (E4-S1), point-type-aware behaviour, bulk actions, competency-aware assignment, review queue.
- Notifications cover assignment, bookings, reminders, witness and hold alerts, review, rejection, approval, overdue and eligibility failure.

Open questions
- Which competitors natively support customer witness notification is unconfirmed.
- State machine implementation: advisors suggested XState or a Postgres workflow table, while the architecture output uses the existing workflow definition; not decided.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
