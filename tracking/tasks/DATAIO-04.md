# DATAIO-04 — AIP migration and reconciliation report with dry run (replaces DATABASE-03)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`data_io`](../../docs/blueprint/modules/data_io/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DATAIO-02, ELIGIBILITY-01, INSPECTIONS-02, ISSUES-01, SCOPEWORK-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/data_io/README.md`](../../docs/blueprint/modules/data_io/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions), [0001](../../docs/adr/0001-greenfield-python-backend.md) (AIP data arrives as an owner-provided export)

## Spec

Import Kaefer's existing records from the owner-provided AIP export through the DATAIO import jobs, with a reconciliation report and dry run (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).

Blocked: waits on [OPEN-QUESTIONS](../OPEN-QUESTIONS.md) #54. Do not guess the answer; the spec is written once the owner answers.
