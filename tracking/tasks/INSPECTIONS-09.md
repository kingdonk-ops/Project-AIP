# INSPECTIONS-09 — Guarded lifecycle actions: inspection categories, SiteSync tablet return, reinspect and supersede

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited 2026-11-01: ADR 0041 moved "skip supervisor review" to INSPECTIONS-10 (Submit Report) and renamed Go to SiteSync -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | APPROVALS-10, INSPECTIONS-10 |
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
  Part B) with at least `hasSupervisorReview`, `category.allowConcurrentInspections` and
  `checkout.fromState` (the status before the tablet checkout). `hasSupervisorReview` (default true) is a new
  field on the inspection category **and** the template (owner, 2026-10-31): the category sets the default and a
  template may override it either way (nullable on the template = use the category); the provider returns the
  resolved value. `allowConcurrentInspections` (default
  false) is a category field.
- **Skipping supervisor review is now INSPECTIONS-10** ([ADR 0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md) §5):
  `submit_report`, guarded on `hasSupervisorReview == false` and by the person doing the work (`execute`), replaces the
  earlier "Mark as Performed from in_progress / Go / inspector_review with `approve`". INSPECTIONS-10 copies the
  setting from the form template. This task adds inspection **categories** with a `hasSupervisorReview` default, and
  changes the copy to resolve as template override, else category default, else `true`.
- **Return from the tablet** (owner, 2026-10-31):
  - Abort and Unlock from `in_progress_sitesync` return to `checkout.fromState` (one of assignable, assigned,
    in_progress, inspector_review, rework_required). The engine allows one transition per `(from, action)`, so
    each becomes guarded twins, one per origin state, for example `sitesync_abort_to_assigned` with guard
    `checkout.fromState == "assigned"`, sharing one label key. Abort discards the tablet's changes.
  - Unlock needs `approvals.inspection.unlock` (new) and follows ADR 0024 (token epoch, quarantined uploads).
  - **Update & Return to Pool** (`sitesync_return_to_pool`) syncs the tablet's answers, clears the assignee and goes to
    `assignable`, so someone else can be assigned. No guard.
- **Reinspect and supersede:** `reinspect` `performed` → `superseded` (permission `approvals.inspection.assign`)
  also creates a new Draft inspection for the same asset in the same transaction, linked to the old one;
  `supersede` `retired` → `superseded`, guarded on `category.allowConcurrentInspections`; when a re-inspection is
  retired, its superseded predecessor returns to `performed` (`restore` `superseded` → `performed`, a system
  transition run by the inspections module). This replaces APPROVALS-05's rule that re-inspection is not a
  transition.
- **Create New** from Performed (owner, 2026-10-31) is a host action, not a transition. It creates a new Draft
  inspection for the same asset without superseding the performed one, so an asset can be inspected repeatedly
  over time for maintenance (for example a yearly wall-thickness check).
- **Golden cases:** each guarded path both allowed and refused, every SiteSync return twin, and the reinspect →
  retire-the-reinspection → restore loop.
- **Out of scope:** the email alerts (no notifications module in R1) and the SiteSync app itself.
