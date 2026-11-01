# Forms JSONLogic golden vectors (FORMS-02, FORMS-10)

One set of cases drives two implementations of the shared form evaluator: the Python one
(`apps/api/aip/modules/forms/evaluator.py`) on the server and the TypeScript one
(`packages/form-renderer/src/logic`) in the browser. Both must return **identical** results for
every case here; a case that one passes and the other fails breaks CI in both `check-py` and
`check-ts`. The vectors are the executable form of the semantics below.

Three files, each `{"version": n, "description": "...", "cases": [...]}`. The two v1 files are
frozen at `version: 1` and never change. `evaluate-v2.json` has `version: 2`, which must equal
`EVALUATOR_VERSION` (`"2"`) in both languages. The suites that load the files assert this.

- `expressions-v1.json` — the shared JSONLogic evaluator (the approvals guard allow-list), ≥ 80
  cases. Each case is either `{name, expr, data, expected}` (`evaluateGuard(expr, data)` equals
  `expected`) or `{name, expr, error}` (`validateGuard(expr)` — or evaluating it — raises a
  `GuardError` whose message equals `error`).
- `evaluate-v1.json` — the answer evaluator, ≥ 30 cases. Each case is
  `{name, schema, answers, mode, context, expected}`, where `expected` is the `AnswerEvaluation`
  in camelCase (below). Every `schema` is a valid FORMS-01 template (`lint_template` returns `[]`,
  checked by the Python suite). Each v1 `expected` is the v1 result, without `sections`. The
  runners compare everything except `sections` with it, and compare `sections` with
  `evaluate-v2.json`'s `v1Sections[<case name>]`.
- `evaluate-v2.json` — section rules and per-section results (FORMS-10, §3), ≥ 10 cases, same
  shape as `evaluate-v1.json` with `expected` including `sections`. Every `schema` has no lint
  *errors* (a `RULE_READS_HIDDEN_FIELD` warning is allowed). `v1Sections` maps every
  `evaluate-v1.json` case name to its expected `sections`.

## 1. The shared JSONLogic evaluator

The operator set, limits and semantics are the approvals transition-guard allow-list (ADR 0035 §1,
`apps/api/aip/modules/approvals/guards/jsonlogic.py`). The 17 allowed operators are:

```
== != === !== < <= > >= ! !! and or if var missing missing_some in
```

Everything else is refused by `validateGuard` with `operator not allowed: <op>`. A guard is capped
at depth 20, 200 nodes and 8 KB serialised (`guard too deep`, `guard too large`). An operation
object must have exactly one key (`a guard operation has exactly one operator`). Truthiness is
JavaScript's (every object is true) except an empty array is false; `NaN` is false. Equality and
numeric coercion follow jsonlogic.com: loose `==` coerces across number/string/boolean and treats
`null` as equal only to `null`; strict `===` never coerces and compares arrays/objects by identity.
`<` and `<=` also take a 3-argument "between" form (`a < b < c`). The Python side calls
`aip.modules.approvals.api.evaluateGuard`/`validateGuard`/`truthy`; the TypeScript side is a port
with the same limits, messages, equality and number coercion, its operators held in a
module-private map that nothing can extend (no `json-logic-js`).

## 2. The answer evaluator

`evaluateAnswers(schema, answers, {mode, context})` →  `AnswerEvaluation`. Pure: no I/O, JSONLogic
only through the shared evaluator above.

- **Input.** `schema` is a FORMS-01 revision schema (`{schemaVersion, sections}`). `answers` is
  `{fieldKey: value}`. `mode` is `"draft"` or `"submit"`. `context` is `{kind, assetId?,
  projectId?}` (or absent → `{}`).
- **Expression data.** Every expression (`visibleIf`, `requiredIf`, `failWhen`, a rule) sees
  `{"answers": <answers of fields already found visible>, "context": context}`. A field's answer
  enters that map only once the field is found visible, so a hidden field's stale answer can never
  show or require another field. Fields (and sections) are walked in a topological order of the
  `visibleIf`/`requiredIf` reference graph — each field also depends on its own section — with ties
  broken by document order (FORMS-01 lint guarantees the reference graph has no cycle; a residual
  cycle falls back to document order deterministically).
- **Visibility.** `visible[f]` is true when the field's section is visible (its `visibleIf` absent
  or truthy) and the field's own `visibleIf` is absent or truthy.
- **Required.** `required[f] = visible[f] and (field.required is true or requiredIf is truthy)`.
  `requiredIf` is evaluated only for visible fields.
- **Empty.** An answer is *empty* when it is absent, `null`, `""`, `[]`, or a measurement whose
  `value` is null (or absent).
- **Errors.** Only visible fields are validated; a hidden field's answer is never validated and is
  listed in `ignored`. Each error is `{fieldKey, code, messageKey, params}`, at most one per field,
  first match wins in this order:
  - `REQUIRED` (submit mode only): required and empty.
  - `WRONG_TYPE` (non-empty answer of the wrong shape):
    `text` string; `number` an integer-valued JSON number (not boolean); `decimal` a finite number
    (not boolean); `date` a real `YYYY-MM-DD` date; `dropdown` string; `multi_select` a list of
    distinct strings; `measurement` `{value: finite number, unit: <the field's unit>}`; `boolean`
    boolean; `photo` a list of `{fileId: uuid}`; `signature` `{fileId: uuid}`; `asset_ref` /
    `user_ref` a uuid string.
  - `NOT_AN_OPTION`: a `dropdown`/`multi_select` value not in `options[].value`.
  - `BELOW_MIN` / `ABOVE_MAX` (`number`, `decimal`, `measurement` value), `TOO_SHORT` / `TOO_LONG`
    (`text`, counted in Unicode code points), `TOO_FEW` / `TOO_MANY` (`multi_select`, `photo`);
    `params` carry the limit (`{min}`, `{max}`, `{minLength}`, `{maxLength}`, `{minItems}`,
    `{maxItems}`).
  - `RULE_FAILED`: the first `rules[i].rule` that is not truthy; `messageKey` is that rule's
    `messageKey`.
  - `UNKNOWN_FIELD`: an answer key that is not a field of the revision (`fieldKey` is that key).
  Field errors come first in document order; `UNKNOWN_FIELD` errors follow, their keys sorted. The
  `messageKey` of every code but `RULE_FAILED` is `forms.answer.<CODE>`; `params` is `{}` for
  `REQUIRED`, `WRONG_TYPE`, `NOT_AN_OPTION`, `RULE_FAILED` and `UNKNOWN_FIELD`.
- **Failed.** `failed` is the keys of visible, non-empty fields whose `failWhen` is truthy, in
  document order. `failWhen` sees the full set of visible answers.
- **Ignored.** `ignored` is the keys of fields that are not visible but have an answer present, in
  document order.
- **Fail closed.** A `GuardError` while evaluating an expression never makes a field disappear,
  become optional or pass: `visibleIf` → visible, `requiredIf` → required, `failWhen` → failed, a
  rule → `RULE_FAILED`. The field (or section) also gets an `expressionErrors` entry
  `{fieldKey, expression, message}` with `expression` one of `visibleIf`, `requiredIf`, `failWhen`,
  `rule`.
- **Complete.** `complete = (errors is empty)`. In `draft` mode `REQUIRED` is suppressed, so a form
  missing only required answers is `complete` in draft and not in submit.
- **Numbers.** Vectors use only values exactly representable in IEEE-754 doubles and integers below
  `2^53`, so Python `float`/`int` and JavaScript `number` agree.

### `AnswerEvaluation` (camelCase)

```json
{
  "visible": {"<fieldKey>": true},
  "required": {"<fieldKey>": false},
  "errors": [{"fieldKey": "x", "code": "REQUIRED", "messageKey": "forms.answer.REQUIRED", "params": {}}],
  "failed": ["<fieldKey>"],
  "ignored": ["<fieldKey>"],
  "expressionErrors": [{"fieldKey": "x", "expression": "visibleIf", "message": "..."}],
  "complete": false,
  "sections": {"<sectionKey>": {"visible": true, "missingRequired": [], "invalid": [], "failed": [], "ruleFailures": [], "complete": true}}
}
```

`visible` and `required` carry every field key; `errors`, `failed`, `ignored` and
`expressionErrors` are compared as whole lists, so their order is part of the contract. `sections`
(FORMS-10, §3) carries every section key.

## 3. Section rules and per-section results (FORMS-10, ADR 0041 §2)

- **Contract.** `schemaVersion` is 1 or 2. A version 2 section may carry `rules`: 0–20 items of
  `{key, expr, label | labelKey}`. A version 1 section may not. Rule keys share one namespace with
  section and field keys (lint `DUPLICATE_KEY`). `expr` is an allow-listed guard (§1) that reads
  only template fields and known context keys (`EXPRESSION_INVALID`, `UNKNOWN_REFERENCE`). A rule
  that reads a field in another section that has a `visibleIf` gets the lint *warning*
  `RULE_READS_HIDDEN_FIELD`, which does not block upload or publish.
- **Evaluation.** Section rules run after the field passes, in document order. Each rule sees the
  same data as `failWhen`: every visible answer plus the context. A rule runs only when its
  section is visible. It *fails* when `expr` is not truthy. A `GuardError` also counts as a
  failure, and it adds an `expressionErrors` entry `{fieldKey: <rule key>, expression: "rule",
  message}` after the field entries.
- **`sections`.** `sections[sectionKey]` is
  `{visible, missingRequired, invalid, failed, ruleFailures, complete}`, with one entry per
  section in document order:
  - `missingRequired`: the section's visible, required, empty fields. This list ignores `mode`,
    because a section tick always checks required answers.
  - `invalid`: the section's fields that have an error other than `REQUIRED`.
  - `failed`: the section's fields listed in the top-level `failed`.
  - `ruleFailures`: the keys of failing rules.
  - `complete`: the section is visible, and `missingRequired`, `invalid` and `ruleFailures` are
    all empty.

  `failed` never makes a section incomplete, because a failed reading is a valid answer. A
  hidden section has `complete: false` and empty lists. It needs no tick.
- **Top-level `complete`** is `errors` empty *and* no section has a `ruleFailures` entry. For a
  version 1 template, which has no rules, it is unchanged.
- **Arithmetic** (`+ - * /`) is not in the allow-list. FORMS-07 adds a forms-only arithmetic
  extension. Until then, a rule like "the average DFT is at least 250" is refused with
  `EXPRESSION_INVALID` (`operator not allowed: /`).

### `sections` entry (camelCase)

```json
{"visible": true, "missingRequired": [], "invalid": [], "failed": [], "ruleFailures": ["dft_ok"], "complete": false}
```
