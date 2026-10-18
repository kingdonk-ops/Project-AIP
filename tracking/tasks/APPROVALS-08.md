# APPROVALS-08 — Approvals interface for R1 modules: export the guard JSONLogic evaluator and a workflow preset installer

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Add to `aip.modules.approvals.api` (1) the guard evaluator (`ALLOWED_OPERATORS`, `GuardError`, `validate_guard`, `evaluate_guard`, `truthy`), so forms, item_types and issues use the same allow-listed JSONLogic without a deep import (import-linter `no-deep-module-import`), and (2) `ApprovalsApi.install_preset(conn, preset_key, *, project_id=None)`, which loads a versioned definition from `config/workflows/`, validates it and publishes it idempotently, so host modules (issues, inspections) ship their lifecycles as data. APPROVALS-05 then installs the inspection preset with it instead of building its own loader (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
