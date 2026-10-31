# FORMS-10 — Section rules and the supervisor-review setting in form templates

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`forms`](../../docs/blueprint/modules/forms/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | FORMS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/forms/README.md`](../../docs/blueprint/modules/forms/README.md)
3. [FORMS-01](FORMS-01.md) (template contract, lint, publish freeze) and [FORMS-02](FORMS-02.md) (the shared evaluator and its golden vectors)
4. ADRs: [0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md) §2 and §5, [0036](../../docs/adr/0036-r1-module-decisions.md) (JSONLogic)
5. Code to build on: `apps/api/aip/modules/forms/data/form-template.schema.json`, `evaluator.py`, `lint.py`;
   `packages/form-renderer/src/logic/`; `packages/contracts/jsonlogic-vectors/forms/`

## Spec

Let a template author give each section its own validation rules, checked by the same evaluator in Python and
TypeScript, and let a template say whether its inspections go to supervisor review (tag: extend).

- **files**:
  - `apps/api/aip/modules/forms/data/form-template.schema.json`
  - `apps/api/aip/modules/forms/evaluator.py`, `lint.py`, `schemas.py`, `tables.py`, `repository.py`, `service.py`,
    `routes.py`, `api.py`
  - `apps/api/migrations/versions/<timestamp>_forms_supervisor_review.py`
  - `packages/form-renderer/src/logic/` (the TypeScript evaluator)
  - `packages/contracts/jsonlogic-vectors/forms/evaluate-v2.json` and its README
  - `config/terms/en-AU/forms.json`
  - tests beside each
- **steps**:
  - 1. **Contract `schemaVersion: 2`.** A section may carry `rules`: 0–20 items of
    `{key, expr, label | labelKey}`. `key` is snake_case and unique within the template (section, field and rule
    keys share one namespace). `expr` is an allow-listed JSONLogic expression that must be **true** for the section
    to pass, and `label` is the message shown when it is false. The schema accepts `schemaVersion` 1 or 2.
    Version 1 templates have no `rules`, and stored version 1 revisions stay valid and evaluate as before.
  - 2. **Lint:** a rule may only read fields of the template (the same `_reads` check as `visibleIf`). A rule that
    reads a field in a section that can be hidden while its own section is visible is a lint warning, not an error.
  - 3. **Evaluator (Python and TypeScript, same behaviour):** `evaluate_answers` gains a per-section result:
    `sections: {sectionKey: {visible, missingRequired: [fieldKey], invalid: [fieldKey], failed: [fieldKey],
    ruleFailures: [ruleKey], complete: bool}}`, where `complete` means visible with no missing required fields, no
    invalid values and no failed rules. A rule is evaluated only when its section is visible, and an expression error
    counts as a failure. `failWhen` outcomes (`failed`) do not make a section incomplete, because a failed reading is
    a valid answer.
  - 4. **Golden vectors:** add `evaluate-v2.json`, covering a passing rule, a failing rule, a rule in a hidden
    section, a rule reading a hidden field, and a v1 template unchanged. Both the Python and TypeScript runners must
    pass every v1 and v2 vector.
  - 5. **Supervisor review setting:** add `form_templates.has_supervisor_review boolean NOT NULL DEFAULT true`
    (migration, `tables.py`, create and update bodies `hasSupervisorReview`, list and detail outputs).
    `FormsApi.get_template(...)` exposes it, so INSPECTIONS-10 can copy it onto an inspection when it is created.
    Changing it never changes inspections that already exist.
- **acceptance**:
  - A version 2 template with section rules publishes. A rule that reads an unknown field fails lint.
  - Python and TypeScript return identical section results on every vector.
  - Every existing template and revision still validates and evaluates exactly as before.
  - Templates default to `hasSupervisorReview: true`, and the flag can be set on create and update.
- **tests**:
  - **unit**:
    - The schema accepts version 1 without `rules` and version 2 with `rules`, and refuses `rules` on version 1 and
      duplicate rule keys.
    - Lint: a rule reading `nozzle_size` (not in the template) → `UNKNOWN_FIELD` issue.
    - Evaluator vectors (both languages): section `coating` with rule `avg_dft_ok` =
      `{">=":[{"/":[{"+":[{"var":"answers.dft_1"},{"var":"answers.dft_2"}]},2]},250]}`. dft 300/300 →
      `complete: true`; 200/250 → `ruleFailures: ["avg_dft_ok"]`, `complete: false`; section hidden → rule not
      evaluated, `complete` not required.
  - **integration**:
    - Create a template with `hasSupervisorReview: false` → detail returns false; omitted → true; another tenant's
      template → 404.
    - Publish a version 2 revision with rules → the frozen revision keeps `rules`, and
      `POST /api/v1/forms/evaluate` returns the per-section result.
  - **e2e**:
    - API and evaluator only: covered above. The template editor UI for rules is a later forms UI task.
