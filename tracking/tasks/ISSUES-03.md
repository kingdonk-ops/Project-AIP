# ISSUES-03 — NCR details (category, disposition) and the hold flag on the ITP step

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`issues`](../../docs/blueprint/modules/issues/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-03, ISSUES-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/issues/README.md`](../../docs/blueprint/modules/issues/README.md) ("NCR", "NCR hold flag on ITP step and asset", "Decisions and notes") and [`data-model.md`](../../docs/blueprint/modules/issues/data-model.md) (`ncr_details`)
3. [`ISSUES-01.md`](ISSUES-01.md) (tables, the `issue` preset, guard facts), [`ISSUES-02.md`](ISSUES-02.md) (the auto-raise subscriber), [`INSPECTIONS-03.md`](INSPECTIONS-03.md) (`InspectionsApi.get_itp_step`, `place_hold`, `clear_hold`)
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md), [0035](../../docs/adr/0035-transition-service-implementation.md) (guards, pinned definition versions), [0036](../../docs/adr/0036-r1-module-decisions.md)
5. [`OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md) #46 (root-cause method, open) — do not build root cause here

## Spec

Give NCR-type issues a 1:1 NCR record with category and disposition, make an NCR complete before it can go to verification, and hold the linked ITP step through `InspectionsApi` from the moment a blocking NCR is linked until the issue is closed (tag: extend).

Out of scope: root cause and its method (ISSUES-06, blocked on OPEN-QUESTIONS #46); cost impact and currency
(not in R1, ADR 0036); `component_id` (there is no components table in R1); `responsible_company_id` (no portal in
R1); the engineering-approval disposition workflow and sealed NCR records (a later row); a hold flag on the asset
itself (inspections offers only the step hold); CAPA (ISSUES-05).

- **files**:
  - apps/api/migrations/versions/<timestamp>_issues_ncr_details.py
  - apps/api/aip/modules/issues/manifest.toml
  - apps/api/aip/modules/issues/tables.py
  - apps/api/aip/modules/issues/schemas.py
  - apps/api/aip/modules/issues/repository.py
  - apps/api/aip/modules/issues/service.py
  - apps/api/aip/modules/issues/ncr.py
  - apps/api/aip/modules/issues/holds.py
  - apps/api/aip/modules/issues/workflow.py
  - apps/api/aip/modules/issues/events.py
  - apps/api/aip/modules/issues/routes.py
  - apps/api/aip/modules/issues/api.py
  - apps/api/aip/modules/issues/tests/test_ncr_unit.py
  - apps/api/aip/modules/issues/tests/test_ncr_db.py
  - apps/api/aip/modules/issues/tests/test_itp_hold.py
  - config/workflows/issue.standard.json
  - config/terms/en-AU/issues.json
- **steps**:
  - 1. Migration `<timestamp>_issues_ncr_details.py`:
    - create `ncr_details` from `render_template("tenant_table", ..., sync=True)` (so `tenant_id`, uuid `id`,
      `sync_version`, timestamps, `deleted_at`, `FORCE ROW LEVEL SECURITY`, fail-closed policy, `aip_app` grants):
      `issue_id uuid NOT NULL` (composite FK to `issues (id, tenant_id)`, `UNIQUE (tenant_id, issue_id)`),
      `category text NULL CHECK (category IN ('material','workmanship','design'))`,
      `disposition text NULL CHECK (disposition IN ('use_as_is','rework','repair','reject'))`,
      `disposition_comment text NULL`, `disposition_by uuid NULL`, `disposition_at timestamptz NULL`,
      `CHECK ((disposition IS NULL) = (disposition_by IS NULL) AND (disposition IS NULL) = (disposition_at IS
      NULL))`, `hold_itp_step_id uuid NULL` (the step this NCR currently holds; the record of what issues asked
      inspections to hold), `hold_placed_at timestamptz NULL`. Index `(tenant_id, category)`.
    - Backfill: `INSERT INTO ncr_details (id, tenant_id, issue_id) SELECT ...` for every live issue whose type has
      `is_ncr = true` (ids from `gen_random_uuid()` are acceptable in the migration only).
    - Downgrade drops the table.
  - 2. `ncr.py` and `service.py`:
    - Creating an issue whose type has `is_ncr` (manual `POST /issues` and the ISSUES-02 subscriber) inserts its
      `ncr_details` row in the same transaction. Changing an issue's type is not allowed (it is not in the PATCH body).
    - `PUT /api/v1/issues/{id}/ncr {category, expectedSyncVersion}` (`issue.update`): sets the category.
    - `POST /api/v1/issues/{id}/ncr/disposition {disposition, comment, expectedSyncVersion}` (`issue.approve`):
      sets `disposition`, `disposition_comment`, `disposition_by` = actor, `disposition_at = now()`; `comment` is
      required for `use_as_is` and `reject` (422 `COMMENT_REQUIRED`). Emits `issue.ncr_dispositioned` v1
      `{issueId, disposition, previousDisposition}`.
    - Both refuse a non-NCR issue (409 `NOT_AN_NCR`) and an issue in `ready_for_verification`, `verified` or
      `closed` (409 `ISSUE_CLOSED`: the NCR is frozen once it is put up for verification); stale
      `expectedSyncVersion` → 409 through `update_with_version`.
    - `GET /issues/{id}` includes `ncr: {category, disposition, dispositionComment, dispositionBy, dispositionAt,
      holdItpStepId, syncVersion}` for NCR issues and `null` otherwise.
  - 3. Preset version 2 in `config/workflows/issue.standard.json`: `submit_for_verification` gains the guard
    `{"or":[{"!":[{"var":"record.isNcr"}]},{"and":[{"!!":[{"var":"record.ncrCategory"}]},{"!!":[{"var":"record.ncrDisposition"}]}]}]}`
    with `guardMessageKey` `workflow.issue.guard.ncr_incomplete`. Nothing else changes. `workflow.py`'s guard
    provider adds `ncrCategory` and `ncrDisposition` (null for non-NCR issues). `POST /issues/setup` installs v2
    through `ApprovalsApi.install_preset`; issues already started keep their pinned v1 (approvals pins the
    definition per instance), which the PR states.
  - 4. ITP step link: `itpStepId` is accepted on `POST /issues` and on `PUT /api/v1/issues/{id}/itp-step
    {itpStepId | null}` (`issue.update`, refused for `closed` issues with 409 `ISSUE_CLOSED`). A step id is checked
    with `aip.modules.inspections.api.InspectionsApi.get_itp_step(conn, step_id)`; `None` (missing or another
    tenant's) → 422 `ITP_STEP_UNKNOWN`. The ISSUES-02 subscriber copies the ITP step of the source inspection onto
    the issue when the inspection view from `InspectionsApi.get_inspection` carries one.
  - 5. `holds.py`: `sync_hold(conn, issue_id)` is the only code that calls inspections' hold functions. It works out
    the step the issue should hold: `itp_step_id` when the type `is_ncr`, the severity `blocks_itp_step`, and
    `state <> 'closed'`; otherwise none. It compares that with `ncr_details.hold_itp_step_id`:
    - same → nothing (idempotent);
    - different → `InspectionsApi.clear_hold(conn, old_step, issue_id=issue_id)` for the old step (if any), then
      `InspectionsApi.place_hold(conn, new_step, issue_id=issue_id)` for the new one (if any), update
      `hold_itp_step_id` / `hold_placed_at`, and emit `issue.hold_changed` v1 `{issueId, itpStepId, held}` once per
      step touched.
    - It runs in the caller's transaction after: issue create (manual and auto-raise), PATCH `severityId`,
      `PUT /itp-step`, and every applied transition (so `close` clears the hold). Errors from inspections
      propagate, so the issue change and the hold commit or roll back together.
    - Only `closed` clears a hold; `verified` keeps it ("honoured until closure", README).
  - 6. `api.py`: `IssuesApi.open_holds_for_step(conn, step_id) -> list[UUID]` (live issues currently holding the
    step), for inspections' pages and for diagnosing a hold.
  - 7. `manifest.toml`: events `issue.ncr_dispositioned` v1 and `issue.hold_changed` v1. `config/terms/en-AU/issues.json`:
    `issues.ncr.category.{material,workmanship,design}`, `issues.ncr.disposition.{use_as_is,rework,repair,reject}`,
    `workflow.issue.guard.ncr_incomplete`, and the error keys `NOT_AN_NCR`, `ITP_STEP_UNKNOWN`.
- **acceptance**:
  - Every live NCR-type issue has exactly one `ncr_details` row; non-NCR issues have none.
  - Category and disposition can be set only on NCRs, only before verification, by the right permission; the
    disposition records who and when.
  - Under preset v2 an NCR cannot be submitted for verification without a category and a disposition; a non-NCR
    issue can.
  - A blocking NCR linked to an ITP step holds that step from the same transaction as the link, moves the hold
    when the link changes, drops it when the severity stops blocking, and clears it when the issue is closed.
  - Every hold change is one `place_hold` / `clear_hold` call and one `issue.hold_changed` event, and repeating
    the same change does nothing.
- **tests**:
  - **unit** (`test_ncr_unit.py`):
    - `desired_hold(is_ncr=True, blocks=True, step=S, state="in_progress")` → `S`; `state="verified"` → `S`;
      `state="closed"` → `None`; `blocks=False` → `None`; `is_ncr=False` → `None`; `step=None` → `None`.
    - `hold_plan(current=None, desired=S)` → `[place S]`; `(S, S)` → `[]`; `(S, S2)` → `[clear S, place S2]`;
      `(S, None)` → `[clear S]`.
    - Preset v2 passes `validate_spec`; its `submit_for_verification` guard with `record = {isNcr: true,
      ncrCategory: "workmanship", ncrDisposition: null}` → false (via `evaluate_guard`); with both set → true;
      `{isNcr: false}` → true.
    - `NcrDisposition` body `{"disposition":"scrap"}` → `ValidationError`; `{"disposition":"rework","extra":1}` →
      `ValidationError` (unknown key).
  - **integration** (`test_ncr_db.py`, `test_itp_hold.py`; testcontainers-python Postgres, TESTING-01 tenants
    `kaefer-demo` and `tenant-b`, ISSUES-01 setup at preset v2, users Alice, Bob and Carol as in ISSUES-01, one ITP
    step per tenant created through the INSPECTIONS-03 interface):
    - Alice creates an `ncr` issue, severity `critical`, no step → 201 with `ncr: {category: null, disposition:
      null, holdItpStepId: null}`; 1 `ncr_details` row. A `defect` issue → `ncr: null`, 0 rows for it.
    - `PUT /issues/{defect id}/ncr {category: "material"}` → 409 `NOT_AN_NCR`.
    - `PUT /issues/{ncr id}/ncr {category: "workmanship", expectedSyncVersion: 1}` → 200, `syncVersion: 2`; again
      with `expectedSyncVersion: 1` → 409.
    - Carol posts `{disposition: "use_as_is"}` with no comment → 422 `COMMENT_REQUIRED`.
    - Bob (only `issue.update`) posts a disposition → 403. Carol (`issue.approve`) posts `{disposition: "rework"}`
      → 200 with `dispositionBy: Carol`, `dispositionAt` set; 1 `domain_events` row `issue.ncr_dispositioned` with
      `payload.previousDisposition = null`.
    - Guard: a second NCR with only a category, taken to `in_progress`, `submit_for_verification` → 422
      `GUARD_FAILED`, `messageKey: "workflow.issue.guard.ncr_incomplete"`; after a disposition → 200. Then
      `PUT /ncr` → 409 `ISSUE_CLOSED`. A `defect` issue submits without any NCR data → 200.
    - Hold on create: an `ncr` / `critical` issue with `itpStepId: S1` → 201; `InspectionsApi.get_itp_step(conn,
      S1)` reports this issue among its holds; `ncr_details.hold_itp_step_id = S1`; 1 `issue.hold_changed` event
      `{held: true, itpStepId: S1}`; `IssuesApi.open_holds_for_step(conn, S1)` → `[issue id]`.
    - Move: `PUT /itp-step {itpStepId: S2}` → S1 no longer held by this issue, S2 held; 2 more
      `issue.hold_changed` events. The same PUT again → 0 new events.
    - Severity: PATCH `severityId: medium` (not blocking) → S2 released by this issue, `hold_itp_step_id = null`;
      PATCH back to `critical` → S2 held again.
    - Close: run the issue to `verified` → still held; `close` → 200, the hold is cleared, and
      `open_holds_for_step(conn, S2)` → `[]`.
    - Auto-raise: an ISSUES-02 rule raising `ncr` / `critical` from an inspection that belongs to step S3 → after
      `drain`, the issue has `itp_step_id = S3` and S3 is held.
    - A `defect` issue with severity `critical` and `itpStepId: S1` → no hold (`is_ncr` false).
    - `itpStepId` of a `tenant-b` step → 422 `ITP_STEP_UNKNOWN`; a `tenant-b` user `GET /issues/{kaefer ncr id}` →
      404 and `POST /issues/{kaefer ncr id}/ncr/disposition` → 404; as `aip_app` with the `tenant-b` context,
      `SELECT count(*) FROM ncr_details` → only `tenant-b` rows.
    - Make `place_hold` raise (test hook) during `PUT /itp-step` → 500; the issue's `itp_step_id` and
      `ncr_details` are unchanged and no `issue.hold_changed` event is written.
  - **e2e**:
    - None in this task: no page, and the compose stack seeds no ITP steps or issue fixtures. The hold path runs
      end to end in the integration tests above through the real inspections interface on Postgres; ISSUES-04's
      Playwright journey (register, detail, cross-tenant 404, axe) covers the NCR section on the detail page.
