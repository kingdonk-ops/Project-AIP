# INSPECTIONS-10 — Section and report acknowledgements lock answers; submit follows the supervisor-review setting

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | APPROVALS-10, FORMS-10, INSPECTIONS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md)
3. [INSPECTIONS-02](INSPECTIONS-02.md) (answers, the editing rules, `ResponseService`), [FORMS-10](FORMS-10.md)
   (per-section results, `hasSupervisorReview`), [APPROVALS-09](APPROVALS-09.md) and [APPROVALS-10](APPROVALS-10.md)
   (the preset codes)
4. ADRs: **[0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md)** (the design; read all of it),
   [0035](../../docs/adr/0035-transition-service-implementation.md) (guards, `GUARD_FAILED`, step-up),
   [0036](../../docs/adr/0036-r1-module-decisions.md) §9 (inspections publishes later versions of its own preset),
   [0031](../../docs/adr/0031-audit-log-not-partitioned.md)
5. Code to build on: `apps/api/aip/modules/inspections/` (INSPECTIONS-01 and -02), `db/templates/append_only_table.sql.tpl`,
   `config/workflows/inspection_standard.json` and `inspection_client_review.json`

## Spec

The person doing an inspection confirms each section and then the whole report. Confirming validates and locks the
answers, only the person who confirmed can undo it, and submit is allowed only on a confirmed report. Submit means
Request Supervisor Review or Submit Report, depending on the template ([ADR 0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md)
§3–§6) (tag: extend).

- **files**:
  - `apps/api/migrations/versions/<timestamp>_inspections_acknowledgements.py`
  - `apps/api/aip/modules/inspections/` (`tables.py`, `schemas.py`, `repository.py`, `acknowledgements.py` (new),
    `responses.py`, `service.py`, `workflow.py`, `events.py`, `routes.py`, `api.py`, `manifest.toml`)
  - `apps/api/aip/modules/inspections/tests/test_acknowledgements_unit.py`, `test_acknowledgements_db.py`
  - `config/workflows/inspection_standard.json`, `config/workflows/inspection_client_review.json`
  - `apps/api/aip/modules/inspections/tests/test_submit_preset_db.py` (the guarded submit cases, run through
    `TransitionService` with the real facts provider; approvals' golden file stays APPROVALS-owned)
  - `config/terms/en-AU/inspections.json`, `config/terms/en-AU/approvals.json`
- **steps**:
  - 1. **Supervisor-review setting on the inspection.** Add `inspections.has_supervisor_review boolean NOT NULL
    DEFAULT true`. `InspectionService.create` copies it from the template (`FormsApi.get_template`), and it never
    changes afterwards. Expose it as `hasSupervisorReview` on the detail output.
  - 2. **Acknowledgements table.** Create `inspection_acknowledgements` with the `append_only_table` template
    (monthly partitions, in `partition_settings` in the same revision, FORCE RLS, SELECT and INSERT only). Own
    columns: `inspection_id`, `scope text CHECK (scope IN ('section','report'))`, `section_key text NULL` (set
    exactly when `scope = 'section'`), `action text CHECK (action IN ('tick','untick','cleared_by_rework'))`,
    `actor uuid NOT NULL`, `revision_id uuid NOT NULL`, `acted_at timestamptz NOT NULL` (`clock_timestamp()`, as in
    INSPECTIONS-02). Add the view `inspection_current_acknowledgements` (`security_invoker`), which returns the
    latest row per `(inspection_id, scope, section_key)`. A scope is **locked** when its latest action is `tick`.
  - 3. **`AcknowledgementService`** (each call is one `with_tenant` transaction that locks the inspection row
    `FOR UPDATE` first, so it serialises with answer writes):
    - `tick_section(section_key)`:
      - The state must be `in_progress`, `inspector_review` or `rework_required`, else 409 `INSPECTION_NOT_EDITABLE`.
      - The caller needs `inspection.respond`, else 403.
      - The section must be in the pinned revision (else 422 `UNKNOWN_SECTION`) and visible (else 422
        `SECTION_NOT_VISIBLE`).
      - If it's already ticked → 409 `SECTION_ALREADY_ACKNOWLEDGED`.
      - Run `evaluate_answers` on the current answers. If the section isn't `complete` → 422 `SECTION_INCOMPLETE`
        with `{missingRequired, invalid, ruleFailures}`. Otherwise insert `tick`.
    - `untick_section(section_key)`:
      - Same state and permission checks.
      - The latest row must be a `tick` by **this actor**, else 403 `NOT_ACKNOWLEDGER`.
      - Refused with 409 `REPORT_ACKNOWLEDGED` while the report is ticked. Otherwise insert `untick`.
    - `tick_report()`:
      - Same state and permission checks.
      - Every visible section must be ticked, else 422 `SECTIONS_NOT_ACKNOWLEDGED` with the keys.
      - The whole-form evaluation must pass, else 422 `REPORT_INCOMPLETE`. Otherwise insert `tick`.
    - `untick_report()`: same checks as `untick_section`.
    - `clear_for_rework()` (system): when the inspection enters `rework_required`, insert `cleared_by_rework` for
      every scope whose latest action is `tick`. It must run in the same transaction as the transition if approvals
      offers a host hook. Otherwise, handle `inspection.state_changed` idempotently, and make sure answer writes and
      ticks also treat ticks older than the latest entry into `rework_required` as cleared, so nothing is ever
      locked during rework.
  - 4. **Locks on answer writes** (extend INSPECTIONS-02's `ResponseService.submit`):
    - In `in_progress`, `inspector_review` and `rework_required`, an answer for a field in a ticked section → 409
      `SECTION_LOCKED` (with `sectionKey`). Any answer while the report is ticked → 409 `REPORT_LOCKED`.
    - In `supervisor_review`, a supervisor with `approvals.inspection.review` is not blocked by ticks.
    - Any 409 writes nothing for the whole batch.
  - 5. **Guard facts** (`workflow.py`): add `hasSupervisorReview` and `reportAcknowledged`.
  - 6. **Preset version** (both presets, published through `install_preset`; APPROVALS-10's codes):
    - Every `request_supervisor_review` (from `assigned`, `in_progress`, `in_progress_sitesync`,
      `inspector_review` and `rework_required`) gets the guard
      `{"and":[{"==":[{"var":"record.hasSupervisorReview"},true]},{"==":[{"var":"record.reportAcknowledged"},true]}]}`.
    - New `submit_report` from `in_progress`, `in_progress_sitesync` and `inspector_review`:
      - Standard preset → `performed`. Client-review variant → `client_review`.
      - Permission `approvals.inspection.execute`, `critical: true`, `signoffAction: inspection.submit_report`.
      - Guard: the same expression, with `hasSupervisorReview == false`.
    - Both guards use `guardMessageKey: "inspection.guard.submit_not_ready"`. A record must never offer both submits
      at once: `GET .../transitions` leaves out the transition whose `hasSupervisorReview` clause is false. If the
      engine can't do that, add the smallest host-side filter in inspections and say so in the PR.
    - Keep the previous versions intact.
  - 7. **Routes** (strict bodies; another tenant's inspection → 404 first):
    - `POST` and `DELETE /api/v1/inspections/{id}/sections/{sectionKey}/acknowledgement`, and the same for
      `/report/acknowledgement` (`inspection.respond`) → 200 with the acknowledgement state.
    - `GET /api/v1/inspections/{id}/acknowledgements` (`inspection.view`) →
      `{sections: {key: {locked, by, at}}, report: {locked, by, at}}`.
  - 8. **API for the report engine:** `InspectionsApi.get_acknowledgements(conn, inspection_id)`, so REPORTS-03 can
    show "completed by X at T" per section.
  - 9. **Events:** `inspection.section_acknowledged` v1 and `inspection.report_acknowledged` v1 on tick, with
    payload `{inspectionId, scope, sectionKey, actor}`, and their exported schemas committed.
  - 10. **Terms:** the new error codes, `inspection.guard.submit_not_ready`, and
    `workflow.inspection.action.submit_report` ("Submit Report").
- **acceptance**:
  - A section can only be ticked when complete. Ticking locks its answers, and only the person who ticked it can
    untick it, including after a handover to another inspector.
  - Submit (either kind) is refused with 422 `GUARD_FAILED` until the report is ticked, and nobody can untick after
    submit.
  - A record offers Request Supervisor Review when `hasSupervisorReview` is true, and Submit Report when it is false,
    never both.
  - Submit Report is a critical sign-off by the person doing the work (`execute`, not `approve`).
  - Request Rework leaves no scope locked. Earlier ticks stay in the history as `cleared_by_rework`.
  - Acknowledgements are never updated or deleted.
- **tests**:
  - **unit:** the lock rule (latest action per scope, and ticks before the last rework entry count as cleared), the
    guard expressions for each combination of `hasSupervisorReview` and `reportAcknowledged`, and strict route bodies.
  - **integration** (testcontainers Postgres, `kaefer-demo` and `tenant-b`; a template with sections `prep`
    (required `surface_prep`) and `coating` (required `dft_1`, `dft_2`, rule `avg_dft_ok`)):
    - Tick `coating` with `dft_2` missing → 422 `SECTION_INCOMPLETE` listing `dft_2`. Answer it below the rule →
      422 with `ruleFailures: ["avg_dft_ok"]`. Fix it → tick succeeds. Writing `dft_1` → 409 `SECTION_LOCKED`.
    - Handover: alice ticks `prep` → hand over to bob. Bob unticking `prep` → 403 `NOT_ACKNOWLEDGER`. Bob ticks
      `coating` and then the report → `request_supervisor_review` succeeds → `supervisor_review`. Alice and bob
      unticking → 409 `INSPECTION_NOT_EDITABLE`.
    - `request_supervisor_review` before the report tick → 422 `GUARD_FAILED` with
      `messageKey: "inspection.guard.submit_not_ready"`.
    - A supervisor with `approvals.inspection.review` changes `dft_1` in `supervisor_review` → 200, recorded under
      the supervisor. A supervisor without it → 403.
    - `request_rework` → `GET /acknowledgements` shows nothing locked, the history has `cleared_by_rework` rows, and
      the inspector can write again.
    - A template with `hasSupervisorReview: false`: available transitions include `submit_report` and not
      `request_supervisor_review`. `submit_report` without step-up → 401 `STEP_UP_REQUIRED`. With step-up →
      `performed`, with a sign-off recorded. Any answer afterwards → 409.
    - As `aip_app`: UPDATE, DELETE and TRUNCATE on `inspection_acknowledgements` → permission denied. The table is
      in `partition_settings`.
    - RLS: `tenant-b` sees 0 rows in the view, and every route returns 404 for a `kaefer-demo` inspection.
  - **e2e:** API only here. INSPECTIONS-04 adds the section tick boxes, the report tick box and the submit button to
    the inspection page, with the Playwright journey and axe checks.
