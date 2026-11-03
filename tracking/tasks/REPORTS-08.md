# REPORTS-08 — Completed inspection reports are locked and listed on the inspected asset's documents

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`report_engine`](../../docs/blueprint/modules/report_engine/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | ASSETS-09, REPORTS-03, REPORTS-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/report_engine/README.md`](../../docs/blueprint/modules/report_engine/README.md)
3. [`docs/reviews/13-merged-pr-review-2026-11-03.md`](../../docs/reviews/13-merged-pr-review-2026-11-03.md) (D3) and
   [`ASSETS-09.md`](ASSETS-09.md) (the source contract)
4. ADRs: 0036, 0039 (#49 with the owner's 2026-11-03 line, and the S3 Object Lock answer)

## Spec

ADR 0039 #49: completed reports "are locked and added to the documents list". Owner 2026-11-03: that list lives on
the **asset** that was inspected (ASSETS-09), not on the inspection (tag: extend).

- **files**:
  - apps/api/aip/modules/report_engine/asset_documents.py (new), api.py (registration at import)
  - apps/api/aip/modules/report_engine/tests/test_asset_documents_db.py
- **steps**:
  - 1. Register the `report` source with ASSETS-09: every succeeded render job whose record resolves to the asset
    (for inspections, through the inspection's `asset_id`), with variant, template, revision, sha256, rendered time
    and a link to the REPORTS-04 download route; filtered by REPORTS-07's rules (`report.view` and the record's view
    permission). Superseded revisions (REPORTS-06) show as superseded.
  - 2. "Locked": a succeeded report is never re-rendered in place; a re-render makes a new job (already true) and a
    later revision supersedes it (REPORTS-06). S3 Object Lock (governance) applies on AWS (ADR 0039); record in the
    as-built notes that the Coolify demo has no object lock.
- **acceptance**:
  - After an inspection is approved, its asset's documents list shows the internal and the client report.
  - A user without `inspection.view` sees neither; another tenant gets 404.
- **tests**:
  - **integration**:
    - approve an inspection → the asset's `report` source returns two items with matching hashes; a user with
      `report.view` but not `inspection.view` → none; tenant B → none
