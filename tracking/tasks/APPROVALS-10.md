# APPROVALS-10 — Rename "In Progress (Go)" to "In Progress (SiteSync)" in the inspection presets

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | APPROVALS-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/APPROVALS-09.md`](APPROVALS-09.md) and [`config/workflows/README.md`](../../config/workflows/README.md): the v2 presets and how a changed preset publishes its next version
3. ADRs: [0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md) §1 (the rename), [0036](../../docs/adr/0036-r1-module-decisions.md) §9

## Spec

Publish the next version of `inspection_standard` and `inspection_client_review` with the tablet state and its
actions renamed from "Go" to "SiteSync" ([ADR 0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md)
§1). No other state, action, permission or guard changes (tag: extend).

- **files**:
  - `config/workflows/inspection_standard.json`, `config/workflows/inspection_client_review.json`
  - `config/workflows/README.md` (the "Shipped presets" rows, if they name the state)
  - `config/terms/en-AU/approvals.json`
  - `apps/api/aip/modules/approvals/manifest.toml` (permission descriptions that say "Go")
  - `apps/api/aip/modules/approvals/tests/golden/inspection_lifecycle_cases.json`
  - any test or module code that names `in_progress_go`, `go_checkout` or `check_in` (search the repo, including
    `apps/api/aip/modules/inspections/`)
  - `tracking/tasks/INSPECTIONS-09.md` (rename its `go_*` action names)
- **steps**:
  - 1. In both presets, rename:

    | From | To | Label term (en-AU) |
    |---|---|---|
    | state `in_progress_go` | `in_progress_sitesync` | `workflow.inspection.state.in_progress_sitesync`: "In Progress (SiteSync)" |
    | action `go_checkout` | `sitesync_checkout` | `workflow.inspection.action.sitesync_checkout`: "SiteSync: Checkout" |
    | action `check_in` | `sitesync_check_in` | `workflow.inspection.action.sitesync_check_in`: "SiteSync: Check In" |

    Every transition into or out of the state keeps its other properties (from, to, permission, comment rule).
  - 2. Terms: add the three new keys and remove `workflow.inspection.state.in_progress_go`,
    `workflow.inspection.action.go_checkout` and `workflow.inspection.action.check_in`, unless another preset still
    uses them. Update any description text that says "Go" for the tablet.
  - 3. Golden cases: rename the codes in every case (the Go round trip, the rework loop, the refusals). Keep
    `source`, `confirmedBy` and `confirmedOn` as they are, and add a `notes` line citing ADR 0041. The case count must
    not drop.
  - 4. Installing the changed presets publishes them as the next version through `install_preset`. Records already on
    the previous version keep it (dev and demo data only; no data migration). State the effect on the Coolify demo in
    the PR.
- **acceptance**:
  - No preset, term, test or module code in the repo still names `in_progress_go`, `go_checkout` or `check_in`
    (`git grep` is clean, except ADR and task-file history).
  - Both presets pass `list_presets()` validation at startup, and re-installing them is idempotent.
  - Every APPROVALS-09 golden case passes with the renamed codes.
- **tests**:
  - **unit**:
    - The golden runner (`test_inspection_golden.py`) passes on the renamed cases for both presets.
    - A terms test: every `labelKey` in both presets resolves in `config/terms/en-AU/approvals.json`, and no removed
      key is still referenced.
  - **integration**:
    - `test_inspection_preset_db.py`: installing the changed presets publishes version n+1; a new instance walks
      `assigned → sitesync_checkout → in_progress_sitesync → sitesync_check_in → inspector_review`; `go_checkout` is
      refused as not available.
  - **e2e**:
    - API and config only: covered by the integration tests (as ADR 0035 §9).
