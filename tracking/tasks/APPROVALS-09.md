# APPROVALS-09 — Inspection lifecycle preset v2: the owner's AIP status and action tables

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | APPROVALS-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/APPROVALS-05.md`](APPROVALS-05.md) and [`config/workflows/README.md`](../../config/workflows/README.md): what v1 shipped and how presets install
3. ADRs: [0035](../../docs/adr/0035-transition-service-implementation.md) (422 validation, 401 step-up), [0036](../../docs/adr/0036-r1-module-decisions.md) §9 (guard-free preset first; guarded versions later)
4. The owner's tables in the appendix below. They are the source; this spec only maps them to codes.

## Why

APPROVALS-05 shipped a provisional, blueprint-derived chain (`source: "blueprint (provisional)"` in the golden file):
draft → assignable → assigned → in_progress → inspector_review → supervisor_review → completed, with
rejected → resend. On 2026-10-30 the owner supplied AIP's real status list and action table (appendix). They add
Clarification Req, In Progress (Go), Rework Required, Performed, Superseded and Retired, and many more actions.
INSPECTIONS-01 starts its records on this preset, so v2 should land **before INSPECTIONS-01** to avoid building on
codes that are about to change. No inspection instances exist yet (INSPECTIONS-01 is `todo`), so renaming states
needs no data migration; the installer publishes v2 as the next version and retires v1.

## Spec

Rewrite `inspection_standard` and `inspection_client_review` to the owner's tables: every status becomes a state,
every action that changes status becomes one or more transitions, and the golden cases become owner-confirmed. This
task ships only the transitions that need **no host facts**. The ones that need inspection data (guards, reinspect,
returning to the status before a tablet checkout) are INSPECTIONS-09 (tag: extend).

- **files**:
  - `config/workflows/inspection_standard.json`, `config/workflows/inspection_client_review.json`
  - `config/workflows/README.md` (the "Shipped presets" rows)
  - `config/terms/en-AU/approvals.json` (`workflow.inspection.state.*`, `workflow.inspection.action.*`)
  - `apps/api/aip/modules/approvals/manifest.toml` (inspection permissions)
  - `apps/api/aip/modules/approvals/tests/golden/inspection_lifecycle_cases.json`
  - `apps/api/aip/modules/approvals/tests/test_inspection_golden.py`, `test_inspection_preset_db.py` (cases only;
    the runners stay)
- **steps**:
  - 1. **States** (codes are snake_case; labels are `workflow.inspection.state.<code>`):

    | Owner status | Code | Terminal | Notes |
    |---|---|---|---|
    | Draft | `draft` | | initial; not checkable-out to Go |
    | Clarification Req | `clarification_required` | | |
    | Assignable | `assignable` | | can be scheduled, assigned or downloaded to Go |
    | Assigned | `assigned` | | other inspectors cannot check it out |
    | In progress | `in_progress` | | being worked on in the web app |
    | In progress (Go) | `in_progress_go` | | checked out to a tablet; read-only on the web |
    | Inspector Review | `inspector_review` | | checked in from Go for desk review |
    | Supervisor Review | `supervisor_review` | | inspector can no longer edit |
    | Client Review | `client_review` | | client-review variant only (unchanged from v1) |
    | Rework Required | `rework_required` | | replaces v1 `rejected` |
    | Performed | `performed` | | replaces v1 `completed`; **not terminal** (reinspect, INSPECTIONS-09) |
    | Superseded | `superseded` | | reached only through INSPECTIONS-09 |
    | Retired | `retired` | | not terminal (concurrent-inspection supersede, INSPECTIONS-09) |

    The graph validator rejects unreachable states, so `superseded` cannot ship in v2 without an incoming
    transition. Ship it with INSPECTIONS-09, not here. v2 has 11 states in the standard preset (12 with
    `client_review`). Delete (Draft only) is a soft delete of the record by the inspections module, not a
    transition.

  - 2. **"Assigned if an assignee is set, otherwise Assignable."** The engine allows one transition per
    `(from, action)`, and APPROVALS-05 fixed the rule "lifecycle changes go in JSON, never in engine code". So each
    such owner action becomes **two action codes**: `<action>` → `assigned` and `<action>_unassigned` →
    `assignable`, sharing one label key. The inspections module calls the one that matches whether the request
    carries an assignee. This applies to Ready For Inspection, Schedule, Assign, Assign With Comment and Handover.

  - 3. **Transitions** (all `labelKey: workflow.inspection.action.<owner action code>`; `→ A/U` means the pair from
    step 2):

    | From | Owner action | Action code(s) | To | Permission | Flags |
    |---|---|---|---|---|---|
    | draft | Ready For Inspection | `ready`, `ready_unassigned` | A/U | assign | |
    | draft | Schedule | `schedule`, `schedule_unassigned` | A/U | assign | |
    | draft | Request Clarification | `request_clarification` | clarification_required | execute | requiresComment |
    | draft | Retire | `retire` | retired | retire | requiresComment |
    | draft | Quick Assign To Me | `assign_to_me` | assigned | execute | |
    | draft | Quick Inspect | `quick_inspect` | in_progress | execute | |
    | clarification_required | Assign With Comment | `assign_with_comment`, `assign_with_comment_unassigned` | A/U | assign | requiresComment |
    | clarification_required | Retire | `retire` | retired | retire | requiresComment |
    | clarification_required | Return to Draft | `return_to_draft` | draft | assign | |
    | assignable | Schedule | `schedule` (→ assigned only) | assigned | assign | |
    | assignable | Assign | `assign` | assigned | assign | |
    | assignable | Assign To Me | `assign_to_me` | assigned | execute | |
    | assignable | Request Clarification | `request_clarification` | clarification_required | execute | requiresComment |
    | assignable | Retire / Return to Draft | `retire`, `return_to_draft` | retired, draft | retire, assign | retire: requiresComment |
    | assignable | Quick Inspect | `quick_inspect` | in_progress | execute | |
    | assignable | Go: Checkout | `go_checkout` | in_progress_go | execute | |
    | assigned | Assign / Schedule / Handover | `assign`, `assign_unassigned`, `schedule`, `schedule_unassigned`, `handover`, `handover_unassigned` | A/U | assign | |
    | assigned | Assign To Me | `assign_to_me` | assigned | execute | self-loop, records the new assignee |
    | assigned | Inspect / Quick Inspect | `inspect`, `quick_inspect` | in_progress | execute | |
    | assigned | Request Supervisor Review | `request_supervisor_review` | supervisor_review | execute | |
    | assigned | Request Clarification | `request_clarification` | clarification_required | execute | requiresComment |
    | assigned | Retire / Return To Draft | `retire`, `return_to_draft` | retired, draft | retire, assign | retire: requiresComment |
    | assigned | Go: Checkout | `go_checkout` | in_progress_go | execute | |
    | in_progress | Request Supervisor Review | `request_supervisor_review` | supervisor_review | execute | |
    | in_progress | Abort | `abort` | assignable | execute | |
    | in_progress | Request Clarification | `request_clarification` | clarification_required | execute | requiresComment |
    | in_progress | Assign | `assign`, `assign_unassigned` | A/U | assign | |
    | in_progress | Go: Checkout | `go_checkout` | in_progress_go | execute | |
    | in_progress_go | Request Supervisor Review | `request_supervisor_review` | supervisor_review | execute | |
    | in_progress_go | Check In | `check_in` | inspector_review | execute | |
    | in_progress_go | Request Clarification | `request_clarification` | clarification_required | execute | requiresComment |
    | inspector_review | Request Supervisor Review | `request_supervisor_review` | supervisor_review | execute | |
    | inspector_review | Handover | `handover`, `handover_unassigned` | A/U | assign | |
    | inspector_review | Abort | `abort` | assignable | execute | |
    | inspector_review | Request Clarification | `request_clarification` | clarification_required | execute | requiresComment |
    | inspector_review | Retire / Return To Draft | `retire`, `return_to_draft` | retired, draft | retire, assign | retire: requiresComment |
    | inspector_review | Go: Checkout | `go_checkout` | in_progress_go | execute | |
    | supervisor_review | Mark as Performed | `mark_performed` | performed (standard) / client_review (variant) | approve | standard: critical, `signoffAction: inspection.approve`; variant: not critical |
    | supervisor_review | Request Rework | `request_rework` | rework_required | approve | requiresComment |
    | supervisor_review | Request Clarification | `request_clarification` | clarification_required | execute | requiresComment |
    | supervisor_review | Retire / Return To Draft | `retire`, `return_to_draft` | retired, draft | retire, assign | retire: requiresComment |
    | rework_required | Handover | `handover`, `handover_unassigned` | A/U | assign | |
    | rework_required | Return To Draft | `return_to_draft` | draft | assign | |
    | rework_required | Request Supervisor Review | `request_supervisor_review` | supervisor_review | execute | |
    | rework_required | Go: Checkout | `go_checkout` | in_progress_go | execute | |
    | client_review (variant) | Client approve / reject | `client_approve`, `request_rework` | performed, rework_required | client_approve | as v1 `client_approve` / `reject` |

    Not transitions (the record's own editing, no status change): Inspect in In progress, Edit/Inspect in
    Inspector Review, Edit in Rework Required, and Delete in Draft. The table's "Quick Inspect" from Draft is kept
    even though Draft is "not able to be checked out by inspectors": it is a web-only start.

  - 4. **Left for INSPECTIONS-09** (each needs facts from the inspections module, so a guard or a host action):
    - Mark as Performed from `in_progress`, `in_progress_go` and `inspector_review`, which skips Supervisor Review
      when the inspection category or template has supervisor review turned off (guard on the resolved fact).
    - Abort and Unlock from `in_progress_go`, which return to the status the inspection had before checkout
      (guarded per origin; see INSPECTIONS-09). Update & Return to Pool goes to `assignable` with the assignee
      cleared; it needs no guard, but it ships with the other tablet returns in INSPECTIONS-09.
    - Reinspect from `performed` (→ `superseded`, and a new Draft inspection), Supersede from `retired` when the
      category allows concurrent inspections, and restoring `superseded` → `performed` when the re-inspection is
      retired.

  - 5. **Permissions** (`approvals/manifest.toml`; descriptions updated):
    - `approvals.inspection.assign`: ready, schedule, assign, handover, assign with comment, return to draft.
    - `approvals.inspection.execute`: assign to me, inspect, quick inspect, Go checkout and check in, request
      supervisor review, request clarification, abort.
    - `approvals.inspection.approve` (the owner's "Mark Inspection as Performed" permission): mark performed,
      request rework.
    - `approvals.inspection.client_approve`: unchanged.
    - **New** `approvals.inspection.retire`: retire (and later supersede).
    - `approvals.inspection.review` has no transition left in v2: Inspector Review is now the inspector's own desk
      review. Keep the code and redefine it as the owner's "Edit Inspection during Review" (a supervisor may edit
      answers in Supervisor Review), which INSPECTIONS-02 checks on answer writes.
    - Default roles get these codes by verb ([ADR 0027](../../docs/adr/0027-default-role-permission-expansion.md)).
      `retire` is not in the verb table, so it falls to `admin`. Either accept that (quality managers retire
      inspections) or add `retire` at `approve` in the verb table and its role test, and say which in the PR.
      `approvals/demo.py` uses only `execute` and `approve`, so it is unaffected.

  - 6. **Terms** (`config/terms/en-AU/approvals.json`): one `workflow.inspection.state.<code>` per state using the
    owner's wording ("Clarification Req", "In Progress (Go)", "Rework Required", "Performed", …), and one
    `workflow.inspection.action.<code>` per owner action. The `_unassigned` twins reuse their pair's key. Remove the
    v1 keys that no longer exist (`rejected`, `completed`, `unassign`, `submit`, `review_pass`, `reject`, `resend`,
    `approve`, `start`), unless another preset still uses them.

  - 7. **Golden cases** (`inspection_lifecycle_cases.json`): set `source` to
    `"owner AIP status and action tables (2026-10-30)"`, `confirmedBy: "owner"`, `confirmedOn: "2026-10-30"`, and
    replace the cases with at least:
    - happy path: `ready` → `inspect` → `request_supervisor_review` → `mark_performed` → `performed`
    - unassigned: `ready_unassigned` → `assignable` → `assign_to_me` → `assigned`
    - Go round trip: `assigned` → `go_checkout` → `in_progress_go` → `check_in` → `inspector_review` →
      `request_supervisor_review` → `supervisor_review`
    - rework loop: `supervisor_review` → `request_rework` (with comment) → `rework_required` → `go_checkout` →
      `check_in` → `request_supervisor_review` → `mark_performed`
    - clarification: from each of draft, assignable, assigned, in_progress, in_progress_go, inspector_review and
      supervisor_review, `request_clarification` → `clarification_required`; then `assign_with_comment` →
      `assigned`
    - comment required: `request_clarification`, `request_rework`, `retire` and `assign_with_comment` without a
      comment → 422 `COMMENT_REQUIRED`
    - retire: from draft, clarification_required, assignable, assigned, inspector_review and supervisor_review
    - refusals: `go_checkout` from `draft` and `retire` from `in_progress` → not available
    - client variant: `mark_performed` → `client_review` → `client_approve` (critical) → `performed`;
      `request_rework` from `client_review` → `rework_required`
- **acceptance**:
  - Both presets validate at boot; the installer publishes them as the next version of the existing definitions and
    retires v1; `kaefer-demo` is re-seeded on v2.
  - Every owner status in the appendix is a state, or is named in step 1 or 4 as shipping in INSPECTIONS-09; every
    owner action that changes status is a transition, or is named in step 3 or 4.
  - No engine code changes (`aip/modules/approvals/*.py` other than tests are untouched).
- **tests**:
  - **unit**: the golden cases in step 7 through the pure evaluator (`test_inspection_golden.py`).
  - **integration**: the same cases through `TransitionService` on Postgres (`test_inspection_preset_db.py`),
    including the critical `mark_performed` step-up and 422 `COMMENT_REQUIRED`.
  - **e2e**: none (no page changes; INSPECTIONS-04 owns the inspection pages).

## Email alerts (recorded here, built later)

The owner's table names an email per status. The transition service already emits an event on every applied
transition, so a notifications subscriber can send these with no preset change. There is no notifications module
in R1 ([BACKLOG](../BACKLOG.md), "Inspection notifications"), so this task builds none of them.

| On entering | Email to |
|---|---|
| `clarification_required` | users with `approvals.inspection.assign` (the owner's "Schedule Inspection" permission) |
| `assigned` | the assignee |
| `supervisor_review` | users with `approvals.inspection.approve` (the owner's "Mark Inspection as Performed" permission) |
| `rework_required` | the assignee ("Rework Required" email) |

## Owner answers (2026-10-31)

1. **Returning from the tablet:** Abort and Unlock return the inspection to the status it had before checkout.
   **Update & Return to Pool** syncs the tablet's answers, clears the assignee and returns it to **Assignable**, so
   someone else can be assigned.
2. **Skipping supervisor review** is an option on the inspection **category or template**, not tied to a plan or
   tier. A template that sets it overrides its category; otherwise the category's setting applies.
3. **Create New** under Performed is a host action that creates a new Draft inspection for the same asset without
   superseding the performed one. It supports repeat inspections of an asset over time for maintenance (for
   example a yearly wall-thickness check).

## Appendix: the owner's tables (2026-10-30)

**Statuses**

| Status | Description | Notes | Email alert |
|---|---|---|---|
| Draft | New inspections are created in Draft | Cannot be checked out by inspectors | |
| Clarification Req | A clarification was requested by the inspector on a previously assigned inspection | Email to nominated users | To users with Schedule Inspection permission |
| Assignable | Can be downloaded to Go, scheduled and assigned to a user | | |
| Assigned | Assigned to an inspector | Other inspectors cannot check out | To the assignee |
| In progress | Being worked on in Portal | Can be checked out to Go by the same inspector | |
| In progress (Go) | Being worked on in Go | Cannot be worked on in Portal; checked out to a tablet | |
| Inspector Review | Checked in from Go for desk review | Inspector can edit in Portal or check back out to Go | |
| Supervisor Review | To be reviewed by a Supervisor | Inspector cannot edit; a supervisor with Edit Inspection during Review can | To users with Mark Inspection as Performed permission |
| Rework Required | Back to the inspector for rework | Inspector can edit in Portal or check back out to Go | Rework Required email to the assignee |
| Performed | Inspection work complete | | |
| Superseded | Previous revisions of an inspection | | |
| Retired | Retired inspection | Deleted state | |

**Actions** ("A/U" = Assigned if an assignee is set, otherwise Assignable)

| Status | Action → To status |
|---|---|
| Draft | Ready For Inspection → A/U · Schedule → A/U · Request Clarification → Clarification Req · Retire → Retired · Delete → (deleted) · Quick Assign To Me → Assigned · Quick Inspect → In Progress |
| Clarification Req | Assign With Comment → A/U · Retire → Retired · Return to Draft → Draft |
| Assignable | Schedule → A/U · Assign → A/U · Assign To Me → Assigned · Request Clarification → Clarification Req · Retire → Retired · Return to Draft → Draft · Quick Inspect → In Progress · Go: Checkout → In Progress (Go) |
| Assigned | Assign → A/U · Assign To Me → Assigned · Schedule → A/U · Handover → A/U · Inspect → In Progress · Request Supervisor Review → Supervisor Review · Request Clarification → Clarification Req · Retire → Retired · Return To Draft → Draft · Quick Inspect → In Progress · Go: Checkout → In Progress (Go) |
| In Progress | Inspect → In Progress · Request Supervisor Review → Supervisor Review · Abort → Assignable · Request Clarification → Clarification Req · Assign → A/U · Go: Checkout → In Progress (Go) · Mark as Performed → Performed (when supervisor review is off) |
| In Progress (Go) | Unlock → (see Unlock Inspection) · Request Supervisor Review → Supervisor Review · Check In → Inspector Review · Request Clarification → Clarification Req · Update & Return to Pool → Assignable or previous status · Abort → Assignable or previous status · Mark Performed → Performed (when supervisor review is off) |
| Inspector Review | Edit/Inspect → Inspector Review · Request Supervisor Review → Supervisor Review · Handover → A/U · Abort → Assignable · Request Clarification → Clarification Req · Retire → Retired · Return To Draft → Draft · Go: Checkout → In Progress (Go) · Mark as Performed → Performed (when supervisor review is off) |
| Supervisor Review | Mark as Performed → Performed · Request Rework → Rework Required · Request Clarification → Clarification Req · Retire → Retired · Return To Draft → Draft |
| Rework Required | Edit → Rework Required · Handover → A/U · Return To Draft → Draft · Request Supervisor Review → Supervisor Review · Go: Checkout → In Progress (Go) |
| Performed | Reinspect → Superseded (creates a new Draft inspection) · Create New |
| Retired | Supersede → Superseded (only where Allow Concurrent Inspections is on) · otherwise final |
| Superseded | → Performed (when the re-inspection is retired) |
