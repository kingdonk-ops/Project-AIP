# INSPECTIONS-02 — Append-only responses, current-response view and server-side answer validation

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | FORMS-02, INSPECTIONS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md) ("Data": `inspection_responses` stays append-only, current value by view, `client_id` for idempotent push; "What it does": corrections are superseding entries)
3. [INSPECTIONS-01](INSPECTIONS-01.md) (the `inspections` table, `InspectionService`, the guard facts provider) and [FORMS-02](FORMS-02.md) (`evaluate_answers`)
4. [PLAN-R1 "Carried forward: append-only evidence tables"](PLAN-R1.md) (the DATABASE-05 check this task owns)
5. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md), [0021](../../docs/adr/0021-retention-schedule.md) (inspection evidence is kept 7 years; the app never drops partitions), [0025](../../docs/adr/0025-time-and-timezones.md), [0031](../../docs/adr/0031-audit-log-not-partitioned.md) (why a partitioned table cannot carry a table-wide unique key), [0036](../../docs/adr/0036-r1-module-decisions.md) (choice 1: answers live in inspections)
6. Code to build on: `db/templates/append_only_table.sql.tpl`, `apps/api/migrations/versions/202610141100_partition_functions.py` (`partition_settings`), `apps/api/aip/modules/inspections/` (from INSPECTIONS-01)

## Spec

Store every answer an inspector gives as an append-only `inspection_responses` row, validated on the server against the inspection's pinned form revision with the shared FORMS-02 evaluator, expose the current value per field through a view, and announce failed answers so issues can be raised (tag: extend).

- **files**:
  - apps/api/migrations/versions/<timestamp>_inspections_responses.py
  - apps/api/aip/modules/inspections/tables.py
  - apps/api/aip/modules/inspections/schemas.py
  - apps/api/aip/modules/inspections/repository.py
  - apps/api/aip/modules/inspections/responses.py
  - apps/api/aip/modules/inspections/workflow.py
  - apps/api/aip/modules/inspections/events.py
  - apps/api/aip/modules/inspections/routes.py
  - apps/api/aip/modules/inspections/api.py
  - apps/api/aip/modules/inspections/manifest.toml
  - apps/api/aip/modules/inspections/tests/test_responses_unit.py
  - apps/api/aip/modules/inspections/tests/test_responses_db.py
  - config/workflows/inspection.standard.json
  - config/terms/en-AU/inspections.json
- **steps**:
  - 1. Migration `<timestamp>_inspections_responses.py`, one revision:
    - Create `inspection_responses` with `render_template("append_only_table", table="inspection_responses", partition_column="created_at", columns=...)`. Own columns: `inspection_id uuid NOT NULL`, `field_key text NOT NULL` (`CHECK (field_key ~ '^[a-z][a-z0-9_]{0,62}$')`), `value jsonb NULL` (null = the answer was cleared), `failed boolean NOT NULL`, `revision_id uuid NOT NULL` (the pinned revision the answer was validated against), `client_id uuid NOT NULL` (idempotent push), `supersedes_id uuid NULL` (the row that was current for this field before), `responded_by uuid NOT NULL`, `responded_at timestamptz NOT NULL` (server time, UTC). The template gives `id`, `tenant_id`, `created_at`, monthly range partitions, FORCE RLS fail closed, `GRANT SELECT, INSERT` to `aip_app` and `REVOKE UPDATE, DELETE, TRUNCATE` from every runtime role.
    - Add `CREATE INDEX ix_inspection_responses_current ON inspection_responses (tenant_id, inspection_id, field_key, created_at DESC, id DESC)` and `CREATE INDEX ix_inspection_responses_client_id ON inspection_responses (tenant_id, inspection_id, client_id)`. `client_id` cannot be unique table-wide on a partitioned table (ADR 0031); the service serialises writes per inspection (step 3) and checks it.
    - `INSERT INTO partition_settings (table_name) VALUES ('inspection_responses')` in the same revision, so `ensure_partitions` keeps monthly partitions ahead.
    - Create view `inspection_current_responses` `WITH (security_invoker = true)` (so the caller's RLS applies) as `SELECT DISTINCT ON (inspection_id, field_key) id, tenant_id, inspection_id, field_key, value, failed, revision_id, responded_by, responded_at, created_at FROM inspection_responses ORDER BY inspection_id, field_key, created_at DESC, id DESC`. Ids are UUIDv7 from the app, so `id DESC` breaks ties between rows written in one transaction (same `created_at`). `GRANT SELECT` on the view to `aip_app` and `aip_readonly`.
  - 2. `tables.py` declares both; `repository.py` adds `insert_response`, `find_by_client_id(conn, inspection_id, client_id)`, `current_responses(conn, inspection_id)` (from the view) and `field_history(conn, inspection_id, field_key)` (oldest first).
  - 3. `responses.py` `ResponseService.submit(conn, policy, actor, inspection_id, answers)` in one `with_tenant` transaction, where `answers` is a list (1–200) of `{fieldKey, value, clientId}`:
    - (a) `repository.lock_inspection` (`FOR UPDATE`); missing or another tenant's → 404. `policy.assert_can(principal, "inspection.respond", Resource(project))` → 403.
    - (b) The instance state (`InspectionsApi.get_state`) must be `in_progress` → else 409 `INSPECTION_NOT_EDITABLE` with the current state.
    - (c) Every `clientId` already stored for this inspection is skipped and returned with `created: false` (idempotent retry); nothing else is checked for it.
    - (d) Load the pinned revision with `FormsApi.get_revision(conn, template_revision_id)`. A `fieldKey` not in the revision → 422 `UNKNOWN_FIELD` (path `answers[i].fieldKey`).
    - (e) Merge the current answers (view) with the new ones and call `aip.modules.forms.api.evaluate_answers(revision_schema, merged)`. Any `errors` entry for a submitted field (wrong type, option not in the list, out of range) → 422 `ANSWER_INVALID` with `[{path, code}]`; a submitted field that is not `visible` → 422 `FIELD_NOT_VISIBLE`. Any 422 writes nothing for the whole batch.
    - (f) Insert one row per new answer with `failed` taken from the evaluation (clients cannot send it: the body model forbids unknown keys) and `supersedes_id` = the field's current row id, if any.
    - (g) For each inserted row with `failed = true` whose superseded row was absent or not failed, `emit(conn, "inspection.answer_failed", 1, {inspectionId, responseId, fieldKey, assetId, projectId})`. Re-saving an already failed value emits nothing; a pass followed by a new failure emits again.
  - 4. Read side in `responses.py`: `current(conn, inspection_id)` returns `{answers: {fieldKey: {value, failed, respondedBy, respondedAt, responseId}}, evaluation: {visible, required, missingRequired, failed}}` (the evaluation re-run on the current answers); `history(conn, inspection_id, field_key)` returns every row for the field, oldest first.
  - 5. Guard facts: extend the `inspection` facts provider in `workflow.py` with `answeredCount`, `missingRequiredCount` (visible required fields with no non-null current value), `invalidCount` and `failedCount`, computed with the same evaluator. In `config/workflows/inspection.standard.json` (the APPROVALS-05 preset data; tell the approvals owner in the PR) give the `submit` transition the guard `{"==":[{"var":"record.missingRequiredCount"},0]}` with `guardMessageKey: "inspection.guard.answers_incomplete"`, so a submit with missing required answers is refused by the transition service whichever route takes it.
  - 6. Routes (strict bodies, camelCase, 422 validation errors; another tenant's inspection → 404 first):
    - `POST /api/v1/inspections/{id}/responses {answers: [{fieldKey, value, clientId}]}` (`inspection.respond`) → 200 `{results: [{clientId, responseId, created, failed}]}`;
    - `GET /api/v1/inspections/{id}/responses` (`inspection.view`) → step 4's current view;
    - `GET /api/v1/inspections/{id}/responses/{fieldKey}/history` (`inspection.view`).
  - 7. `api.py`: `InspectionsApi.get_current_responses(conn, inspection_id) -> CurrentResponses` (step 4's shape, used by report_engine and issues). Manifest: permission `inspection.respond` ("Answer inspection questions"), `[[events]]` `inspection.answer_failed` v1 with its pydantic payload in `events.py`.
  - 8. Terms: `inspection.error.not_editable`, `.unknown_field`, `.answer_invalid`, `.field_not_visible` and `inspection.guard.answers_incomplete` in `config/terms/en-AU/inspections.json`.
- **Out of scope**: checking that `photo` and `signature` answers name a clean stored file needs `aip.modules.uploads.api.get_stored_file` (UPLOADS-08), which is not a dependency; this task stores those values as validated uuids only, and INSPECTIONS-04 adds the uploads check. Offline push (`client_id` from a device queue) is after R1.
- **acceptance**:
  - Answers are never updated or deleted: `aip_app` has no UPDATE, DELETE or TRUNCATE on `inspection_responses`, and a correction is a new row that supersedes the old one.
  - `inspection_current_responses` returns exactly one row per answered field, the latest; the history lists every row (the DATABASE-05 check).
  - Answers are validated on the server against the pinned revision with the same evaluator the web uses; an invalid batch writes nothing.
  - `inspection_responses` is in `partition_settings` from the same revision that creates it.
  - A newly failed answer emits one `inspection.answer_failed` v1 in the same transaction.
  - `submit` is refused with 422 `GUARD_FAILED` while required answers are missing.
- **tests**:
  - **unit** (`test_responses_unit.py`):
    - The failure-transition rule: (previous absent, new failed) → emit; (previous failed, new failed) → no emit; (previous passed, new failed) → emit; (previous failed, new passed) → no emit.
    - `ResponsesIn` with `{"answers":[{"fieldKey":"dft","value":300,"clientId":"…","failed":false}]}` → validation error on `failed`; 0 answers or 201 answers → validation error.
    - `fieldKey: "DFT-1"` → validation error (pattern).
  - **integration** (`test_responses_db.py`, testcontainers-python Postgres, `kaefer-demo` and `tenant-b`; the INSPECTIONS-01 conftest plus a published revision with `coating_dft` (number, required, `failWhen` `{"<":[{"var":"coating_dft"},250]}`), `surface_prep` (dropdown `Sa2.5`/`Sa3`, required) and `remarks` (text, visible only when `surface_prep` is `Sa3`); an inspection moved to `in_progress`):
    - DATABASE-05 check: submit `coating_dft = 300`, then `coating_dft = 320` with a new `clientId` → `GET /responses` gives `coating_dft.value = 320`; `SELECT count(*) FROM inspection_current_responses WHERE field_key = 'coating_dft'` → 1; `GET /responses/coating_dft/history` lists 2 entries (300 then 320), the second with `supersedesId` = the first's id.
    - Same `clientId` sent twice → second call `created: false`, same `responseId`; `SELECT count(*) FROM inspection_responses` unchanged.
    - `coating_dft = 200` → `failed: true` and 1 `domain_events` row named `inspection.answer_failed` with the payload's `fieldKey: "coating_dft"`; then `coating_dft = 180` → still 1; then 300, then 190 → 2.
    - `surface_prep = "Sa1"` → 422 `ANSWER_INVALID` with path `answers[0].value`; `nozzle_size = 3` → 422 `UNKNOWN_FIELD`; `remarks = "x"` while `surface_prep = "Sa2.5"` → 422 `FIELD_NOT_VISIBLE`. A batch of one valid and one invalid answer → 422 and 0 new `inspection_responses` rows.
    - Inspection in `assigned` → 409 `INSPECTION_NOT_EDITABLE`; viewer without `inspection.respond` → 403; both write nothing.
    - `submit` with `surface_prep` unanswered → 422 `GUARD_FAILED` with `messageKey: "inspection.guard.answers_incomplete"`; after answering it → 200 `inspector_review`; then a further answer → 409 `INSPECTION_NOT_EDITABLE`.
    - As `aip_app`: `UPDATE inspection_responses SET value = '1'` → permission denied; `DELETE FROM inspection_responses` → permission denied; `TRUNCATE inspection_responses` → permission denied.
    - `SELECT table_name FROM partition_settings` includes `inspection_responses`; after running `ensure_partitions`, the current month's partition exists and the row submitted above is readable through the parent.
    - RLS: as `aip_app` bound to `tenant-b`, `SELECT count(*) FROM inspection_current_responses` → 0; a `tenant-b` user `GET /api/v1/inspections/{kaefer id}/responses` → 404 and `POST` → 404.
    - `InspectionsApi.get_current_responses` returns the same answers as the HTTP route.
  - **e2e**:
    - API-only task: covered by the in-process HTTP integration tests above (as ADR 0035 §9). INSPECTIONS-04 adds the Playwright journey that answers through the form renderer, plus its cross-tenant and axe checks.
