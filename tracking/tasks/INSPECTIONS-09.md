# INSPECTIONS-09 — Guarded lifecycle actions: skip supervisor review, tablet return, reinspect and supersede

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | APPROVALS-09, INSPECTIONS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/APPROVALS-09.md`](APPROVALS-09.md): the state and action codes, step 4 and the owner's tables
3. ADRs: [0024](../../docs/adr/0024-remote-unblock-and-targeted-wipe.md) (remote un-block of a tablet lock), [0035](../../docs/adr/0035-transition-service-implementation.md), [0036](../../docs/adr/0036-r1-module-decisions.md) §9

## Spec

Publish the next version of the inspection presets with the owner actions that need facts from the inspections
module, and build the host side of those actions (tag: extend).

Stub: the full spec is written once APPROVALS-09 and INSPECTIONS-01 have merged. Scope agreed so far:

- **Guard facts.** The inspections module registers its guard context provider for `inspection` (APPROVALS-02
  Part B) with at least `category.hasSupervisorReview`, `category.allowConcurrentInspections` and
  `checkout.fromState` (the status before the tablet checkout). Both category settings default to true / false
  respectively and are new inspection-category fields.
- **Mark as Performed without supervisor review:** `mark_performed` from `in_progress`, `in_progress_go` and
  `inspector_review` → `performed`, critical (`signoffAction: inspection.approve`), guarded on
  `category.hasSupervisorReview == false`, permission `approvals.inspection.approve`.
- **Return from the tablet:** Abort, Update & Return to Pool and Unlock from `in_progress_go` return to
  `checkout.fromState` (one of assignable, assigned, in_progress, inspector_review, rework_required). The engine
  allows one transition per `(from, action)`, so each becomes guarded twins, one per origin state, for example
  `go_abort_to_assigned` with guard `checkout.fromState == "assigned"`, sharing one label key. Unlock needs
  `approvals.inspection.unlock` (new) and follows ADR 0024 (token epoch, quarantined uploads). Update & Return to
  Pool syncs the tablet's answers first; Abort discards them. Owner question 1 in APPROVALS-09 may change the target
  to Assignable.
- **Reinspect and supersede:** `reinspect` `performed` → `superseded` (permission `approvals.inspection.assign`)
  also creates a new Draft inspection for the same asset in the same transaction, linked to the old one;
  `supersede` `retired` → `superseded`, guarded on `category.allowConcurrentInspections`; when a re-inspection is
  retired, its superseded predecessor returns to `performed` (`restore` `superseded` → `performed`, a system
  transition run by the inspections module). This replaces APPROVALS-05's rule that re-inspection is not a
  transition. "Create New" from Performed is a host action that creates a new Draft inspection without
  superseding (owner question 3).
- **Golden cases:** each guarded path both allowed and refused, every Go return twin, and the reinspect →
  retire-the-reinspection → restore loop.
- **Out of scope:** the email alerts (no notifications module in R1) and the Go app itself.
