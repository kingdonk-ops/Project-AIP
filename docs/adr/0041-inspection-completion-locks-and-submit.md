# ADR 0041: Inspection completion: section and report acknowledgements lock answers, submit follows the template's supervisor-review setting, and "In Progress (Go)" becomes "In Progress (SiteSync)"

- **Status:** accepted
- **Date:** 2026-11-01
- **Affects:** approvals (APPROVALS-10), inspections (INSPECTIONS-02, INSPECTIONS-09, INSPECTIONS-10), forms (form
  template contract, `hasSupervisorReview`), report_engine (REPORTS-03 shows who completed each section)

## Context

[APPROVALS-09](../../tracking/tasks/APPROVALS-09.md) (PR #213) replaced the v1 inspection lifecycle from APPROVALS-05
with the owner's AIP status and action tables. v1 was one line, `draft → assignable → assigned → in_progress →
inspector_review → supervisor_review → completed`, with `rejected`/`resend` as the only loop. Its `submit` action
(`in_progress → inspector_review`) was where the inspector handed in. v2 has no `submit`: the inspector hands in with
**Request Supervisor Review** from `assigned`, `in_progress`, `in_progress_go`, `inspector_review` or
`rework_required`. `completed` is now `performed`, and `rejected` is split into `rework_required` and
`clarification_required`.

[INSPECTIONS-02](../../tracking/tasks/INSPECTIONS-02.md) was written against v1. It allows answers only in
`in_progress` and puts its answers-complete guard on `submit`, so it cannot be built as written. Planning the change,
the owner set out how an inspection is completed and locked (2026-11-01). This ADR records those answers.

## Decision

### 1. "In Progress (Go)" is renamed "In Progress (SiteSync)"

The tablet app is called SiteSync. In both inspection presets, the state `in_progress_go` becomes
`in_progress_sitesync`, labelled "In Progress (SiteSync)". Its actions are renamed to match:

| v2 (APPROVALS-09) | Renamed |
|---|---|
| `in_progress_go` | `in_progress_sitesync` |
| `go_checkout` | `sitesync_checkout` |
| `check_in` | `sitesync_check_in` |

Codes stay lowercase snake_case (the preset key rule). The INSPECTIONS-09 tablet returns are renamed in the same way
(`go_abort_to_<state>` becomes `sitesync_abort_to_<state>`, `go_return_to_pool` becomes `sitesync_return_to_pool`).
[APPROVALS-10](../../tracking/tasks/APPROVALS-10.md) publishes the rename as the next version of both presets.

### 2. Sections are the unit of completion

Form templates already have sections (`key`, `label`, `fields`, `visibleIf`). The template author decides how many:
one section holding everything (one tick), or several, each with its own title and rules. A section can also carry
**section rules**: JSONLogic checks across its fields, such as "the average DFT in this section is at least 250", each
with a message. They are evaluated by the same shared FORMS-02 evaluator the web uses. This is the next
`schemaVersion` of the form template contract, and older revisions without `rules` stay valid.

### 3. Acknowledging a section validates it and locks its answers

- At the end of each visible section, the person doing the inspection ticks **"Section complete"**. Ticking runs the
  section's checks: required fields answered, every value valid, `failWhen` outcomes recorded, and the section rules.
  If any check fails, the tick is refused with the reasons. If all pass, the section's answers are locked, and the
  tick records who ticked it and when.
- Hidden sections need no tick, and their answers are not checked.
- **Only the person who ticked a section can untick it.** This is what makes handover mid-inspection safe: inspector A
  can complete and lock sections 1 and 2, then hand over or unassign. Inspector B then completes sections 3 and 4 but
  cannot unlock A's work. Each section's completion ("completed by A at 10:42") is shown on the PDF report.
- Ticks and unticks are append-only rows, like answers. The current lock state of a section is its latest row.

### 4. Acknowledging the report enables submit

- After every visible section is ticked (by anyone), the submitter ticks **"Report complete"**. That runs the whole
  form's checks once more. The report tick can be unticked by whoever ticked it, which also lets sections be
  unticked again.
- Every submit action requires a current report tick. The transition service enforces this as a guard on the fact
  `record.reportAcknowledged`, so it holds whichever route takes the transition.

### 5. Submit depends on the template's supervisor-review setting

- **Supervisor review on:** the submit action is **Request Supervisor Review**, from `assigned`, `in_progress`,
  `in_progress_sitesync`, `inspector_review` and `rework_required` → `supervisor_review`. **Mark as Performed**
  (supervisor, `approvals.inspection.approve`, critical) is the final lock.
- **Supervisor review off:** the submit action is **Submit Report**, a new action (`submit_report`) from
  `in_progress`, `in_progress_sitesync` and `inspector_review` → `performed`. It is critical (step-up and a recorded
  sign-off, `signoffAction: inspection.submit_report`) and needs `approvals.inspection.execute`, **not**
  `approvals.inspection.approve`. Not every form is done by an inspector: a vehicle inspection or a delivery
  acknowledgement is signed off by whoever filled it in.
- Each pair is guarded on the resolved fact `record.hasSupervisorReview`, so a record shows only the submit action
  that applies to it. Inspection categories don't exist yet, so `hasSupervisorReview` is a field on the form template
  (default `true`), and the inspection copies the value from its template when it is created. Changing the template
  later never changes inspections that already exist. When categories
  arrive (INSPECTIONS-09), the category sets the default and a template may override it.
- This replaces INSPECTIONS-09's "Mark as Performed without supervisor review" (`approve` permission).

### 6. Who can change answers

| State | Who can save answers | Locks |
|---|---|---|
| `in_progress`, `inspector_review`, `rework_required` | the person doing it (`inspection.respond`) | refused in sections ticked by anyone; refused everywhere while the report is ticked |
| `in_progress_sitesync` | nobody on the web: checked out to SiteSync | tablet sync comes after R1 |
| `supervisor_review` | a supervisor with "Edit Inspection during Review" (`approvals.inspection.review`) | ticks do not block the supervisor; each change is recorded under the supervisor's name |
| every other state | nobody | 409 `INSPECTION_NOT_EDITABLE` |

- From `supervisor_review` onwards, nobody can untick anything.
- **Request Rework** clears every section and report tick, including those from earlier inspectors, so whoever does
  the rework can edit. Each tick is cleared with a "cleared by rework" row, not deleted.
- **Performed** is the final lock. Only **Reinspect** (INSPECTIONS-09) leads to editable answers again, and it does
  that by creating a new inspection.

## Consequences

- INSPECTIONS-02 is narrowed to append-only answers plus the editing rules above (who can write, in which states, with
  the supervisor's review permission). Its v1 `submit` guard is removed, and the locks and guards move to the new
  INSPECTIONS-10.
- FORMS-10 (new) adds section rules (template `schemaVersion: 2`, in both the Python and TypeScript evaluators with
  shared golden vectors) and the template's `hasSupervisorReview` field. It depends only on FORMS-02, so it can start
  now.
- INSPECTIONS-10 (new) owns the section and report acknowledgements, the locks, the guarded submit transitions,
  `submit_report`, copying `hasSupervisorReview` onto the inspection, and rework clearing the ticks. It depends on
  INSPECTIONS-02, FORMS-10 and APPROVALS-10 and runs alongside INSPECTIONS-03, so it does not lengthen the demo's
  critical path. REPORTS-03 shows who completed each section, and when, if INSPECTIONS-10 has landed.
- APPROVALS-10 (new, small) publishes the SiteSync rename. It must land before INSPECTIONS-10 publishes its
  guarded preset version.
- INSPECTIONS-09 keeps the tablet returns (renamed to SiteSync), Reinspect and Supersede, and adds inspection
  categories with a `hasSupervisorReview` default. It loses "Mark as Performed without supervisor review".
- `approvals.inspection.review` keeps the meaning APPROVALS-09 gave it ("Edit Inspection during Review").
- Forms that aren't about an asset (for example a delivery acknowledgement) are out of scope: inspections always
  belong to an asset. Whether R1 needs a general "form submission" record is a separate decision.
