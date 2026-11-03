# REPORTS-07 — Report access and error fixes: record-level view on read and download, create check on replay, client snapshot strips internal fields

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`report_engine`](../../docs/blueprint/modules/report_engine/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | REPORTS-03, REPORTS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/report_engine/README.md`](../../docs/blueprint/modules/report_engine/README.md)
3. [`docs/reviews/13-merged-pr-review-2026-11-03.md`](../../docs/reviews/13-merged-pr-review-2026-11-03.md) (M1, L1 to L5)
4. ADRs: 0014, 0027, 0036, 0039

## Spec

Close the report_engine gaps the review found in REPORTS-02, -03 and -04 (tag: harden).

- **files**:
  - apps/api/aip/modules/report_engine/render_service.py
  - apps/api/aip/modules/report_engine/snapshots.py
  - apps/api/aip/modules/report_engine/providers/inspection.py
  - config/report-templates/inspection/*/v1/style.css (font)
  - apps/api/aip/modules/report_engine/tests/
  - tracking/tasks/REPORTS-04.md (as-built note: reads need the record's view permission)
- **steps**:
  - 1. **Record-level view on reads (M1).** `get`, `list` and `download` require `report.view` **and** the source
    record type's `view_permission` (from `get_provider(record_type)`) on the job's project, as `request_render`
    already does. `list` leaves out rows the caller may not see; `get` and `download` answer 404 when the caller lacks
    the record permission (do not reveal the job), and 403 only when `report.view` itself is missing, as today. A job
    whose record type has no registered provider is refused (fail closed).
  - 2. **Replay needs create (L1).** A POST that reuses a known `Idempotency-Key` checks `report.create` plus the
    record's view permission, the same codes as a new request. Scope the key lookup to the requesting user
    (`requested_by`), so one user's key never returns another user's job.
  - 3. **Missing pinned file is 404 (L2).** `request_render` maps `RecordNotFound` raised by `build_snapshot` to
    404 `RECORD_NOT_FOUND`, like the provider's.
  - 4. **Client snapshot is clean (L4).** For the `client` variant the inspection provider leaves `respondedBy`,
    `internalTag`, the inspection id and `schemaHash` out of the snapshot itself, not only out of the template.
  - 5. **Embedded font (L5).** Both inspection templates load an OFL font shipped in the repo (IBM Plex Sans, ADR
    0014) through `@font-face` from the template directory, with `sans-serif` only as the fallback.
- **acceptance**:
  - A user with `report.view` but without `inspection.view` on the project cannot list, get or download an inspection
    report (404 on get and download, absent from the list).
  - Replaying an idempotency key without `report.create` answers 403; a different user's key does not find the job.
  - A render whose pinned file is gone answers 404, never 500.
  - The stored client-variant snapshot contains no responder name, internal tag, inspection id or schema hash.
  - Both inspection PDFs embed the Plex font (checked with pypdf's font list).
- **tests**:
  - **unit**:
    - client provider snapshot → none of the four internal keys present
  - **integration**:
    - `report.view` without `inspection.view` → list omits the job; get and download 404
    - replay by a user without `report.create` → 403; replay of the same key by another user → its own job
    - pinned file deleted before render → 404 `RECORD_NOT_FOUND`
    - client PDF text has no internal tag (add to `test_auto_render_db.py`)
    - the pinning test asserts the v1 marker is present as well as the v2 marker absent (L3)
  - **e2e**:
    - none (API only; the REPORTS-04 register e2e must still pass)
