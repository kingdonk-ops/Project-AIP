# Workflow presets (`config/workflows/`)

Host modules (issues, inspections, …) ship their approval lifecycle here as data rather than in
code. `ApprovalsApi.install_preset(conn, preset_key)` (APPROVALS-08) reads `<preset_key>.json` from
this directory, validates it with the same rules as `POST /api/v1/approvals/definitions`, and
publishes it idempotently: re-installing an unchanged preset is a no-op, and a changed spec is
published as the next version (retiring the previous one).

The directory is `$AIP_WORKFLOWS_DIR` when set, otherwise `<repo root>/config/workflows`. Deploy
jobs that call `install_preset` must have it on disk (mirror the `config/terms` copy in the image).

Each file is one definition:

```json
{
  "key": "widget_lifecycle",
  "recordType": "widget",
  "spec": {
    "states": [
      { "code": "draft", "labelKey": "inspections.state.draft" },
      { "code": "done", "labelKey": "inspections.state.done", "terminal": true }
    ],
    "initial": "draft",
    "transitions": [
      {
        "action": "complete",
        "from": "draft",
        "to": "done",
        "requiredPermission": "inspections.complete",
        "labelKey": "inspections.action.complete"
      }
    ]
  }
}
```

- `key` must equal the file stem and be snake_case; `recordType` is snake_case.
- `spec` follows `aip.modules.approvals.schemas.WorkflowDefinitionSpec` (states, `initial`,
  transitions; guards are allow-listed JSONLogic). Labels are terminology keys, never text.

- `requiresComment: true` on a transition makes the transition service refuse it without a
  non-blank comment (422 `COMMENT_REQUIRED`).
- Every preset here is validated when the API starts (`list_presets`), so a broken file stops startup.
  The API image copies this directory to `/app/config/workflows` (`AIP_WORKFLOWS_DIR`).

## Shipped presets

| Preset | Record type | Scope | Notes |
|---|---|---|---|
| `inspection_standard` | `inspection` | tenant-wide | APPROVALS-09 (v2, from the owner's AIP status and action tables; v1 was APPROVALS-05). APPROVALS-10 renamed the tablet state and its actions from Go to SiteSync (`in_progress_sitesync`, `sitesync_checkout`, `sitesync_check_in`; ADR 0041 §1), published as the next version. 11 states: draft, clarification_required, assignable, assigned, in_progress, in_progress_sitesync, inspector_review, supervisor_review, rework_required, performed, retired (none terminal). Actions that go to "Assigned if an assignee is set, otherwise Assignable" ship as pairs, `<action>` → assigned and `<action>_unassigned` → assignable (ready, schedule, assign, assign_with_comment, handover); the host calls the one that matches. `request_clarification`, `request_rework`, `retire` and `assign_with_comment` need a comment. `mark_performed` is critical. INSPECTIONS-03 guards every `request_supervisor_review` on `record.openStepCount == 0` (`inspection.guard.not_ready_to_submit`), so an ITP with open steps cannot be handed in. Seeded in `kaefer-demo` by `python -m aip.modules.approvals.seeds`, which publishes v2 over an installed v1. INSPECTIONS-09 adds the guarded and host actions (skip supervisor review, tablet returns, reinspect, supersede, `superseded`). |
| `inspection_client_review` | `inspection` | **project only** | As standard (including the open-steps guard) plus `client_review`: `mark_performed` → client_review (not critical) → `client_approve` (critical) → performed, or `request_rework` (comment) → rework_required. Install it with a `projectId`: resolution prefers a project's definition, then the tenant-wide one, so a tenant-wide install would compete with `inspection_standard`. |

The inspection cases are owner-confirmed (2026-10-30): see
`apps/api/aip/modules/approvals/tests/golden/inspection_lifecycle_cases.json`. A lifecycle change is
made in these JSON files and the golden cases, never in engine code.
