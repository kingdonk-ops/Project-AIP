# FORMS-12 — Designer logic builder and test console: conditions, fail rules, section rules, sample answers

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`forms`](../../docs/blueprint/modules/forms/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | FORMS-11 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`FORMS-11.md`](FORMS-11.md) (the designer this extends), [`FORMS-02.md`](FORMS-02.md) (the evaluator and its operator allow-list) and [`FORMS-10.md`](FORMS-10.md) (section rules)
3. [`docs/blueprint/modules/forms/README.md`](../../docs/blueprint/modules/forms/README.md) and [`routes.md`](../../docs/blueprint/modules/forms/routes.md) ("Designer": logic builder, test console)
4. ADRs: [0043](../../docs/adr/0043-form-designer-in-r1.md), [0035](../../docs/adr/0035-transition-service-implementation.md) §1 (the JSONLogic allow-list), [0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md)

## Spec

Add to the FORMS-11 designer a condition builder for a field's `visibleIf`, `requiredIf` and `failWhen` and a section's `visibleIf` and `rules` (rows of field, operator and value, joined by all or any, written as JSONLogic using only the allow-listed operators), and a test console that runs sample answers through the shared evaluator and shows each field's and section's result (tag: extend).

Stub: full spec is written when FORMS-11 merges (PLAN-R1 convention). Scope fixed now (ADR 0043):

- The builder reads back any expression it can show as rows; anything else (nested groups deeper than one level, operators it has no row for) stays as JSON with an "Edit as JSON" box checked by `validateGuard`, never dropped.
- Operators offered by field type (for example `==`, `!=` for dropdowns and booleans; `<`, `<=`, `>`, `>=` for numbers and measurements; `in` for multi-select), values picked from the field's options where it has them.
- Section rules: key, message and condition; the FORMS-07 arithmetic arrives in the builder when FORMS-07 lands.
- Test console: a side panel that fills answers through the preview, shows `evaluateAnswers` results (visible, required, failed, section pass or fail with rule messages), and keeps up to five named sample sets for the session only (no server storage in R1).
- Publish stays blocked by lint issues (FORMS-11); failing sample sets warn but do not block (saved test cases are BACKLOG).
- e2e: build a field that shows only when "Surface prepared" is No, prove it in the test console and in the preview, publish, and see the same behaviour in an INSPECTIONS-04 inspection.
