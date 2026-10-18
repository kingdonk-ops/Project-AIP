# ISSUES-02 — Raise an issue from a failed inspection answer (configurable raise rules)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`issues`](../../docs/blueprint/modules/issues/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-02, ISSUES-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/issues/README.md`](../../docs/blueprint/modules/issues/README.md) ("Auto-raise from inspection answers") and [`data-model.md`](../../docs/blueprint/modules/issues/data-model.md) (`issue_raise_rules`)
3. [`ISSUES-01.md`](ISSUES-01.md) (the `issues` table, `create_issue`, the `issue` workflow) and [`INSPECTIONS-02.md`](INSPECTIONS-02.md) (the `inspection.answer_failed` v1 payload and `InspectionsApi.get_current_responses`)
4. ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox, subscribers in the same transaction), [0030](../../docs/adr/0030-outbox-dispatch-semantics.md) (at-least-once delivery, retries, dead letters), [0035](../../docs/adr/0035-transition-service-implementation.md) (the JSONLogic allow-list and limits), [0036](../../docs/adr/0036-r1-module-decisions.md) (rules are JSONLogic, no CEL)
5. Code: `apps/api/aip/platform/events/subscribers.py` (the `@subscriber` contract: idempotent, never commit), `apps/api/aip/platform/links/__init__.py` (`LinkService`)

## Spec

Let a tenant admin configure raise rules (template, field, JSONLogic condition over the failed answer, issue type and severity) and raise exactly one issue per failed response by consuming `inspection.answer_failed` v1 from the outbox (tag: extend).

Out of scope: carrying photos from the response onto the issue (evidence lands with ISSUES-04 through uploads); the
ITP step link and hold (ISSUES-03); a rule-test console; notifications to the responsible person.

- **files**:
  - apps/api/migrations/versions/<timestamp>_issues_raise_rules.py
  - apps/api/aip/modules/issues/manifest.toml
  - apps/api/aip/modules/issues/tables.py
  - apps/api/aip/modules/issues/schemas.py
  - apps/api/aip/modules/issues/repository.py
  - apps/api/aip/modules/issues/raise_rules.py
  - apps/api/aip/modules/issues/service.py
  - apps/api/aip/modules/issues/events.py
  - apps/api/aip/modules/issues/routes.py
  - apps/api/aip/modules/issues/tests/test_raise_rules_unit.py
  - apps/api/aip/modules/issues/tests/test_raise_rules_db.py
  - apps/api/aip/modules/issues/tests/test_auto_raise.py
  - config/terms/en-AU/issues.json
- **steps**:
  - 1. Migration `<timestamp>_issues_raise_rules.py`:
    - create `issue_raise_rules` from `render_template("tenant_table", ...)` (so `tenant_id`, uuid `id`,
      `created_at`, `updated_at`, `deleted_at`, `FORCE ROW LEVEL SECURITY`, fail-closed policy, `aip_app` grants):
      `template_id uuid NULL` (null = any template; no cross-module FK), `field_key text NULL` (null = any failed
      field; same pattern as form field keys `^[a-z][a-z0-9_]*$`), `condition jsonb NULL` (JSONLogic over the
      failed answer; null = always), `issue_type_id`, `severity_id` (composite FKs to `issue_types` and
      `issue_severities` on `(id, tenant_id)`), `title text NULL CHECK (length(title) <= 200)`,
      `active boolean NOT NULL DEFAULT true`. Index `(tenant_id, template_id, field_key) WHERE active AND
      deleted_at IS NULL`.
    - On `issues` (created by ISSUES-01): `CREATE UNIQUE INDEX ux_issues_source_response ON issues (tenant_id,
      source_response_id) WHERE source_response_id IS NOT NULL`. It deliberately has no `deleted_at` filter: a
      response that already raised an issue never raises another, even after that issue is soft-deleted.
    - Downgrade drops the index and the table.
  - 2. `raise_rules.py` (pure, no I/O):
    - `rule_data(answer, field_key, template_id, inspection_kind) -> dict` builds
      `{"answer": <value>, "fieldKey": str, "templateId": str, "inspection": {"kind": str}}`. Values are JSON
      (`Decimal` → number, dates → ISO strings), as ADR 0035 §8 requires of guard facts.
    - `order_rules(rules)`: template-specific before any-template, field-specific before any-field, then severity
      `rank` descending, then `created_at`, then `id`.
    - `pick_rule(rules, data) -> Rule | None`: the first rule in that order whose `condition` is null or evaluates
      truthy with `aip.modules.approvals.api.evaluate_guard` (truthiness by `truthy`). A rule whose evaluation
      raises is skipped and logged (`issues.raise.rule_error`, rule id only, never the answer).
    - Conditions are validated on save with `aip.modules.approvals.api.validate_guard` (the 17-operator allow-list,
      depth 20, 200 nodes, 8 KB). See the cross-module note in the final step.
  - 3. Admin routes in `routes.py`, all `issue.manage`, bodies with `extra="forbid"`:
    - `GET /api/v1/issues/raise-rules`, `POST /api/v1/issues/raise-rules`, `PATCH /api/v1/issues/raise-rules/{id}`,
      `DELETE /api/v1/issues/raise-rules/{id}` (soft delete).
    - A condition that fails `validate_guard` → 422 with `loc: ["body", "condition"]` and the evaluator's message.
    - `templateId` must exist: `aip.modules.forms.api.FormsApi.get_current_revision(conn, template_id)` returns
      `None` → 422 `TEMPLATE_UNKNOWN`. Type and severity must be live in this tenant → 422 `ISSUE_TYPE_UNKNOWN` /
      `ISSUE_SEVERITY_UNKNOWN`.
  - 4. Subscriber in `events.py`: `@subscriber("inspection.answer_failed", 1) async def raise_from_failed_answer(conn,
    event)`, and `[[subscribes]] name = "inspection.answer_failed" version = 1` in `manifest.toml` (boot fails
    without it). It runs in the dispatcher's transaction as the event's actor and tenant, never commits, and is
    idempotent:
    - (a) If an issue with `source_response_id = payload.responseId` exists (live or deleted) → return.
    - (b) `InspectionsApi.get_inspection(conn, payload.inspectionId)` for `template_id` and `kind`; `None` → return
      (the inspection is gone or not visible; logged).
    - (c) `InspectionsApi.get_current_responses(conn, inspectionId)`: take the entry for `payload.fieldKey`. If its
      response id is not `payload.responseId` (the answer was corrected before dispatch) → return; the corrected
      answer emits its own event if it also fails. The answer value comes from this entry.
    - (d) Load the live, active rules matching `template_id` (or null) and `fieldKey` (or null), then `pick_rule`.
      No rule → return (logged `issues.raise.no_rule`).
    - (e) Insert the issue through the ISSUES-01 create path without a permission check (the trigger is the failed
      answer, not a user request): `asset_id` and `project_id` from the payload, type and severity from the rule,
      `title` = `rule.title` or the field key (the page shows the field label), `source = 'inspection'`,
      `source_inspection_id`, `source_response_id`, `raised_by = event.actor_id`, due date from the severity as in
      ISSUES-01. The insert is `INSERT ... ON CONFLICT (tenant_id, source_response_id) WHERE source_response_id IS
      NOT NULL DO NOTHING`; a conflict means another delivery won → return without emitting.
    - (f) Start the workflow with `ApprovalsApi.get_or_start_instance(conn, "issue", issue_id, project_id)`, emit
      `issue.raised` v1 with `source: "inspection"`, and link the records with
      `LinkService().link(conn, RecordRef("issue", issue_id), RecordRef("inspection", inspection_id),
      "raised_from", asset_id=asset_id)`.
    - Any other exception propagates, so the dispatcher retries and dead-letters per ADR 0030 (the whole delivery
      rolls back; nothing half-raised is left).
  - 5. `GET /api/v1/issues?source=inspection&inspectionId=` filter, and `source`, `sourceInspectionId`,
    `sourceResponseId`, `raiseRuleId` in the issue response. Add `raise_rule_id uuid NULL` to `issues` in the same
    migration (composite FK to `issue_raise_rules`), so the detail page can say which rule raised it.
  - 6. Terms: `issues.raise_rule.*` field and error keys (`TEMPLATE_UNKNOWN`), `issues.source.manual`,
    `issues.source.inspection`.
  - 7. The evaluator comes from `aip.modules.approvals.api` (exported by APPROVALS-08, which ISSUES-01 depends on).
    Never import `aip.modules.approvals.guards.jsonlogic` directly and never copy the evaluator.
- **acceptance**:
  - A failed answer that matches an active rule raises exactly one issue, with the rule's type and severity, the
    inspection's asset and project, and a workflow instance in `open`, in the same transaction as the event
    delivery.
  - Delivering the same event twice, or two events for the same response, still leaves exactly one issue.
  - A failed answer with no matching rule, a superseded response or an invisible inspection raises nothing and
    does not fail the delivery.
  - Rules accept only allow-listed JSONLogic; a bad condition is refused on save with a field path.
  - Rules, and issues raised from them, never cross tenants.
- **tests**:
  - **unit** (`test_raise_rules_unit.py`):
    - `pick_rule` with rules R1 `{template: T, field: "dft_um", condition: {"<":[{"var":"answer"},250]},
      severity: high}` and R2 `{template: null, field: null, condition: null, severity: low}`, data
      `{answer: 180, fieldKey: "dft_um", templateId: T}` → R1. With `answer: 300` → R2.
    - Same rules, data with `templateId: T2` → R2 (R1 is template-specific).
    - Two any-template rules for `dft_um`, `medium` (rank 20) and `critical` (rank 40), both conditions null →
      the `critical` rule.
    - Condition `{"in":[{"var":"answer"},["fail","reject"]]}` with `answer: "fail"` → matches; `"pass"` → no match.
    - A rule whose condition reads `{"<":[{"var":"answer"},"abc"]}` and raises inside the evaluator → skipped, the
      next rule is picked.
    - `validate_guard({"reduce":[...]})` on save → error `operator not allowed: reduce`.
    - `rule_data` with `Decimal("12.50")` → `answer == 12.5` (a number, not a string).
  - **integration** (`test_raise_rules_db.py`, `test_auto_raise.py`; testcontainers-python Postgres, TESTING-01
    tenants `kaefer-demo` and `tenant-b`, ISSUES-01 setup run in both; one form template, asset and inspection per
    tenant created through the FORMS-01 upload-and-publish endpoint, `AssetsApi.create_asset` and
    `InspectionsApi.create_inspection`, the template having a number
    field `dft_um` with `failWhen` `{"<":[{"var":"dft_um"},250]}`; a failing answer recorded
    through the INSPECTIONS-02 responses endpoint; events delivered with `aip.platform.events.dispatcher.drain`):
    - `POST /api/v1/issues/raise-rules {templateId: T, fieldKey: "dft_um", condition: {"<":[{"var":"answer"},
      250]}, issueTypeId: ncr, severityId: high}` as `issue.manage` → 201; with `condition: {"map":[1,2]}` → 422,
      `loc: ["body","condition"]`; with a `tenant-b` severity id → 422 `ISSUE_SEVERITY_UNKNOWN`; with an unknown
      `templateId` → 422 `TEMPLATE_UNKNOWN`; without `issue.manage` → 403.
    - Record `dft_um = 180` (fails) → after `drain`: 1 `issues` row with `source = 'inspection'`,
      `source_response_id` = that response, `severity` = high, `issue_type` = ncr, `asset_id` = the inspection's
      asset, `raised_by` = the inspector; the issue's workflow `current_state = 'open'`; 1 `domain_events` row
      `issue.raised` with `payload.source = "inspection"`; 1 `record_links` row `issue → inspection`,
      `link_kind = 'raised_from'`.
    - Re-deliver the same event (reset `published_at` on the `domain_events` row and `drain` again) → still 1
      issue, still 1 `issue.raised` event for that response.
    - Insert a second `inspection.answer_failed` event for the same `responseId` → still 1 issue.
    - Two deliveries of the same event run concurrently (`asyncio.gather` of the handler on two connections) → 1
      issue; the loser returns without error.
    - Record `dft_um = 180` and then `dft_um = 300` before `drain` (the first answer superseded) → 0 issues from
      the first event; the second response does not fail the field, so no event and 0 issues in total.
    - Rule deactivated (`active: false`) → a failing answer raises 0 issues; the event is published (not dead-
      lettered).
    - A rule whose condition is false for the answer and no fallback rule → 0 issues, event published.
    - `tenant-b` has no rules: a failing `tenant-b` answer → 0 issues in `tenant-b`, and the `kaefer-demo` count is
      unchanged. A `tenant-b` user `GET /api/v1/issues/raise-rules` → only `tenant-b` rules (0);
      `PATCH /api/v1/issues/raise-rules/{kaefer rule id}` → 404.
    - Soft-delete the raised issue, re-deliver the event → still no new issue (`ux_issues_source_response` holds).
    - Make the handler's `issue.raised` emit throw (test hook) → the delivery fails, 0 `issues` rows, and the event
      is retried with `attempts = 1`.
  - **e2e**:
    - None in this task: no page, and the dispatcher journey needs fixture rules and templates the compose stack
      does not seed. The integration tests run the whole path through the real dispatcher on Postgres; ISSUES-04's
      Playwright journey opens an auto-raised issue from the register.
