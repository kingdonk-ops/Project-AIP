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
  "key": "inspection_lifecycle",
  "recordType": "inspection",
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

APPROVALS-05 ships the first real preset (`inspection_lifecycle`) and adds the image copy.
