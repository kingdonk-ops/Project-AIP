# FORMS-02 — Shared JSONLogic form evaluator: Python and TypeScript on the same golden vectors

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`forms`](../../docs/blueprint/modules/forms/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | FORMS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`FORMS-01.md`](FORMS-01.md) (the template contract: field keys, types, `visibleIf`, `requiredIf`, `failWhen`, `validations`, `rules`, and the JSONLogic data shape)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) ("Shared rules": JSONLogic, no CEL, no scripts), [0035](../../docs/adr/0035-transition-service-implementation.md) §1 (the in-house allow-listed evaluator and its semantics), [0036](../../docs/adr/0036-r1-module-decisions.md) (one Python and one TypeScript evaluator on shared vectors; answers are stored by inspections)
4. Code: [`approvals/guards/jsonlogic.py`](../../apps/api/aip/modules/approvals/guards/jsonlogic.py) (the semantics the TypeScript twin must match line for line), [`packages/contracts/csv-vectors/csv-v1.json`](../../packages/contracts/csv-vectors/csv-v1.json) with [`apps/api/tests/platform/http/test_csv.py`](../../apps/api/tests/platform/http/test_csv.py) and [`packages/ui/src/register/csv.test.ts`](../../packages/ui/src/register/csv.test.ts) (how one vector file drives a Python and a Vitest suite)

## Spec

Build the one answer evaluator every form consumer uses: given a frozen revision schema and a set of answers it decides which fields are visible and required, which answers are invalid and which answers fail, in Python on the server and in TypeScript in the browser, proven identical on one set of golden vectors (tag: extend).

> **JSONLogic reuse.** The operator set, limits and semantics are the approvals guard allow-list
> (`== != === !== < <= > >= ! !! and or if var missing missing_some in`; depth 20, 200 nodes, 8 KB). Python calls
> `aip.modules.approvals.api.evaluate_guard`, `validate_guard`, `truthy` and `GuardError`. approvals must export
> them from `api.py` (the FORMS-01 precondition); forms never imports `aip.modules.approvals.guards`. TypeScript has
> no shared JSONLogic yet, so this task writes the twin in `packages/form-renderer` with the same 17 operators and
> no `json-logic-js` dependency (its global `add_operation` registry is what the allow-list exists to avoid).

> **Out of scope:** calculated fields (need arithmetic operators the allow-list refuses; no R1 row), repeating
> sections, storing answers and checking that referenced assets, users and files exist (INSPECTIONS-02), the React
> components (FORMS-03).

- **files**:
  - apps/api/aip/modules/forms/evaluator.py
  - apps/api/aip/modules/forms/api.py
  - apps/api/aip/modules/forms/schemas.py
  - apps/api/aip/modules/forms/routes.py
  - apps/api/aip/modules/forms/service.py
  - apps/api/aip/modules/forms/tests/test_evaluator_vectors.py
  - apps/api/aip/modules/forms/tests/test_evaluate_route.py
  - packages/contracts/jsonlogic-vectors/forms/expressions-v1.json
  - packages/contracts/jsonlogic-vectors/forms/evaluate-v1.json
  - packages/contracts/jsonlogic-vectors/forms/README.md
  - packages/contracts/package.json
  - packages/form-renderer/package.json
  - packages/form-renderer/tsconfig.json
  - packages/form-renderer/vitest.config.ts
  - packages/form-renderer/eslint.config.mjs
  - packages/form-renderer/src/index.ts
  - packages/form-renderer/src/logic/types.ts
  - packages/form-renderer/src/logic/jsonlogic.ts
  - packages/form-renderer/src/logic/evaluate.ts
  - packages/form-renderer/src/logic/jsonlogic.test.ts
  - packages/form-renderer/src/logic/evaluate.test.ts
  - config/terms/en-AU/forms.json
  - e2e/web/forms-evaluate-api.spec.ts
- **steps**:
  - 1. **Evaluation semantics** (write them in `packages/contracts/jsonlogic-vectors/forms/README.md`; both implementations follow it exactly):
    - Input: `schema` (a FORMS-01 revision schema), `answers` (`{fieldKey: value}`), `mode` (`"draft"` or `"submit"`), `context` (`{kind, assetId?, projectId?}`).
    - Walk sections and fields in a topological order of the `visibleIf`/`requiredIf` reference graph, ties broken by document order (FORMS-01 lint guarantees no cycle).
    - Expression data is `{"answers": <answers of fields already found visible>, "context": context}`, so a hidden field's stale answer can never show or require another field.
    - `visible[f]` = section visible (its `visibleIf` absent or truthy) and field `visibleIf` absent or truthy.
    - `required[f]` = `visible[f]` and (`required` is true, or `requiredIf` is truthy).
    - An answer is *empty* when it is absent, `null`, `""`, `[]`, or a measurement with `value` null.
    - Errors (only for visible fields; hidden fields are never validated and their answers are reported in `ignored`), each `{fieldKey, code, messageKey, params}`, at most one per field, first match wins in this order:
      - `REQUIRED` (only in `submit` mode): required and empty.
      - `WRONG_TYPE`: `text` str; `number` integer (not bool); `decimal` finite number (not bool); `date` `YYYY-MM-DD` and a real date; `dropdown` str; `multi_select` list of distinct str; `measurement` `{value: finite number, unit: <the field's unit>}`; `boolean` bool; `photo` list of `{fileId: uuid}`; `signature` `{fileId: uuid}`; `asset_ref`/`user_ref` uuid string.
      - `NOT_AN_OPTION`: a value not in `options[].value`.
      - `BELOW_MIN` / `ABOVE_MAX` (number, decimal, measurement value), `TOO_SHORT` / `TOO_LONG` (text, counted in Unicode code points), `TOO_FEW` / `TOO_MANY` (multi_select, photo); `params` carry the limit.
      - `RULE_FAILED`: the first `rules[i].rule` that is not truthy; `messageKey` from the rule.
      - `UNKNOWN_FIELD`: an answer key that is not a field of the revision (`fieldKey` = that key).
    - `failed`: keys of visible, non-empty fields whose `failWhen` is truthy, in document order.
    - Expression errors fail closed: a `GuardError` while evaluating `visibleIf` → visible; `requiredIf` → required; `failWhen` → failed; a rule → `RULE_FAILED`; and the field also gets an entry in `expressionErrors` (`{fieldKey, expression: "visibleIf"|..., message}`).
    - `complete` = no `errors` in `submit` mode.
    - Numbers: vectors use only values exactly representable in IEEE 754 doubles and integers below 2^53, so Python `float`/`int` and JavaScript `number` agree.
  - 2. **Python** `evaluator.py`: `EVALUATOR_VERSION = "1"`; frozen dataclasses `AnswerError(field_key, code, message_key, params)`, `ExpressionError(field_key, expression, message)`, `AnswerEvaluation(visible: dict[str, bool], required: dict[str, bool], errors: list[AnswerError], failed: list[str], ignored: list[str], expression_errors: list[ExpressionError], complete: bool)`; `evaluate_answers(revision_schema, answers, *, mode="submit", context=None) -> AnswerEvaluation`. Pure: no database, no I/O; JSONLogic only through `aip.modules.approvals.api.evaluate_guard`/`truthy`. Replace FORMS-01's literal `evaluator_version = "1"` in `service.publish` with `EVALUATOR_VERSION`.
  - 3. `api.py` exports `evaluate_answers`, `AnswerEvaluation`, `AnswerError`, `ExpressionError`, `EVALUATOR_VERSION`. INSPECTIONS-02 calls `evaluate_answers` to validate saves (`draft`) and submit (`submit`) on the server and raises `inspection.answer_failed` from `failed`; clients never send an evaluation result.
  - 4. Route `POST /api/v1/forms/revisions/{revisionId}/evaluate {answers, mode, context?}` (`form.view`, strict body) → 200 the evaluation in camelCase. Works on drafts too, so an admin can test a template before publishing (the FORMS-04 test console calls it). Another tenant's revision → 404.
  - 5. **Golden vectors** (`packages/contracts/jsonlogic-vectors/forms/`, each file `{"version": 1, "description", "cases": [...]}`; `version` must equal `EVALUATOR_VERSION` in both languages):
    - `expressions-v1.json`: at least 80 cases `{name, expr, data, expected}` or `{name, expr, error}` covering every allowed operator, JSONLogic truthiness (`[]` false, `{}` true, `"0"` true, `0` false), loose versus strict equality (`{"==":[1,"1"]}` true, `{"===":[1,"1"]}` false, `{"==":[null,0]}` false, `{"==":[true,"1"]}` true), the 3-argument "between" form of `<` and `<=`, `var` with dotted paths, array indexes and defaults, `missing`/`missing_some`, `in` on strings and arrays, `if` with an odd argument count, and refusals with the exact message: `operator not allowed: some`, `operator not allowed: +`, `operator not allowed: exec`, `guard too deep` (depth 21), `guard too large` (201 nodes), `a guard operation has exactly one operator`.
    - `evaluate-v1.json`: at least 30 cases `{name, schema, answers, mode, context, expected: <AnswerEvaluation in camelCase>}`, covering every error code, every field type's `WRONG_TYPE`, section-level `visibleIf`, a chain (`a` shows `b` shows `c`; hiding `a` hides `c` even when `b` holds a stale answer), `requiredIf`, `failWhen` on a measurement, `draft` versus `submit`, `ignored`, and one fail-closed case per expression kind (an expression that raises at evaluation, e.g. `{"missing_some":["x",[]]}`).
    - Every `schema` in `evaluate-v1.json` passes FORMS-01 `lint_template` (checked by the Python test), so the vectors stay valid templates.
    - Add `"./jsonlogic-vectors/*": "./jsonlogic-vectors/*"` to `packages/contracts/package.json` `exports`.
  - 6. **TypeScript** package `@aip/form-renderer` (`packages/form-renderer`, ESM, `type: module`, same tsconfig/eslint/vitest setup as `packages/ui`, devDependency `@aip/contracts: workspace:*`):
    - `logic/types.ts`: `FormSchema`, `FormSection`, `FormField`, `FieldType`, `AnswerValue`, `Answers`, `EvaluationMode`, `AnswerEvaluation`, `AnswerError`, `ExpressionError`, matching the JSON Schema and the Python dataclasses (camelCase).
    - `logic/jsonlogic.ts`: `ALLOWED_OPERATORS`, `GuardError`, `validateGuard(expr)`, `evaluateGuard(expr, data)`, `truthy(v)`, a port of the approvals module's Python evaluator: same limits, same error messages, same equality and number coercion, `data` deep-frozen with `Object.freeze`, operators held in a module-private `Map` that nothing can extend.
    - `logic/evaluate.ts`: `EVALUATOR_VERSION = "1"`, `evaluateAnswers(schema, answers, {mode, context})`, following step 1.
    - `index.ts` exports the above. No React in this task.
  - 7. `config/terms/en-AU/forms.json`: one `forms.answer.<CODE>` message per error code with ICU params (e.g. `forms.answer.BELOW_MIN`: `Must be at least {min}.`), and `forms.answer.failed` (`Fail`).
- **acceptance**:
  - Python and TypeScript return identical results for every vector (deep equality on the camelCase output); a vector that one passes and the other fails breaks CI in both `check-py` and `check-ts`.
  - Neither evaluator accepts an operator outside the approvals allow-list, and the Python one uses the approvals implementation rather than a copy.
  - Hidden fields never produce errors and never feed other conditions.
  - Evaluation errors never make a field disappear, become optional or pass.
  - `form_revisions.evaluator_version` on newly published revisions equals `EVALUATOR_VERSION`.
- **tests**:
  - **unit**:
    - Python `test_evaluator_vectors.py` and Vitest `jsonlogic.test.ts` + `evaluate.test.ts` each load the two vector files (the CSV-vector pattern) and run every case; each asserts `vectors.version == EVALUATOR_VERSION` and that the case count is ≥ 80 and ≥ 30.
    - `evaluate_answers(coating schema, {"surface_prepared": false}, mode="submit")` → `visible.remarks = true`, `required.blast_standard = true`, `errors` contains `{fieldKey:"blast_standard", code:"REQUIRED"}`; the same in `draft` mode → no `REQUIRED` errors, `complete` is false only in submit.
    - `{"surface_prepared": true, "remarks": "old"}` → `visible.remarks = false`, `ignored = ["remarks"]`, no error for `remarks`.
    - `dft_avg = {"value": 0.18, "unit": "mm"}` with `failWhen {"<":[{"var":"answers.dft_avg.value"},0.25]}` → `failed = ["dft_avg"]`; `0.30` → `failed = []`; `{"value": 0.3, "unit": "in"}` → `WRONG_TYPE`.
    - `blast_standard = "sa4"` (options `sa2`, `sa2_5`, `sa3`) → `NOT_AN_OPTION`; `{"extra": 1}` → `UNKNOWN_FIELD` for `extra`.
    - `text` with `maxLength 3` and `"héllo"` → `TOO_LONG` with `params {maxLength: 3}`; `date` `"2026-02-30"` → `WRONG_TYPE`.
    - A `visibleIf` of `{"missing_some":["x",[]]}` (raises at evaluation) → field visible and an `expressionErrors` entry `expression: "visibleIf"`.
    - TS only: `evaluateAnswers` leaves its `answers` argument deep-equal to a `structuredClone` taken before the call; the package exports no way to register an operator (an exports test lists `index.ts` exports exactly); `validateGuard({"some":[]})` → `GuardError` `operator not allowed: some`.
  - **integration** (`test_evaluate_route.py`, testcontainers-python Postgres, `kaefer-demo` and `tenant-b`):
    - Publish `coating-itr-min.json` (FORMS-01 fixture); `form_revisions` row `evaluator_version = '1'`.
    - Alice (`form.view`) `POST /api/v1/forms/revisions/{id}/evaluate {"answers":{"dft_avg":{"value":0.18,"unit":"mm"}},"mode":"submit"}` → 200, `failed: ["dft_avg"]`, `complete: false`, `errors` has `REQUIRED` for `blast_standard`.
    - The same call on a draft revision → 200 (drafts can be tested).
    - Bob (`tenant-b`) on Alice's revision → 404. A user without `form.view` → 403. A body with an extra key `{"answers":{},"mode":"submit","complete":true}` → 422.
  - **e2e**:
    - `e2e/web/forms-evaluate-api.spec.ts` (Playwright request context, `kaefer-demo` admin via `e2e/fixtures/login.ts`): upload and publish `coating-itr-<runId>`, evaluate a failing DFT answer → `failed` contains `dft_avg`; the `tenant-b` user evaluating the same revision → 404. The evaluator has no page; FORMS-03 renders it and runs axe.
