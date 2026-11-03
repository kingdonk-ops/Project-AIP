# REPORTS-08 — Completed inspection reports are locked and listed in their inspection's documents

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`report_engine`](../../docs/blueprint/modules/report_engine/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | REPORTS-03, REPORTS-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/report_engine/README.md`](../../docs/blueprint/modules/report_engine/README.md)
3. [`docs/reviews/13-merged-pr-review-2026-11-03.md`](../../docs/reviews/13-merged-pr-review-2026-11-03.md) (D3)
4. ADRs: 0036, 0039 (#49 and the S3 Object Lock answer)

## Spec

Implement ADR 0039 #49: completed reports "are locked and added to the documents list of their inspection" (tag: extend).

- **files**: decided in step 1; likely `apps/api/aip/modules/report_engine/` (the render job's success path or a
  `report.rendered` subscriber) and the inspections read model
- **steps**:
  - 1. **Open question first.** No `documents` module task exists in R1. Decide with the owner whether the inspection's
    documents list is (a) a read on the inspection detail that lists its succeeded render jobs, or (b) a row in a
    future documents module. Record the answer here before building.
  - 2. When an inspection's report render succeeds, the report appears on that inspection's documents list with its
    variant, revision and hash, newest first, readable under the same rules as REPORTS-07 step 1.
  - 3. "Locked": a succeeded report is never re-rendered in place; a re-render makes a new job (already true) and a
    later revision supersedes it (REPORTS-06). S3 Object Lock (governance) applies on AWS (ADR 0039); record in the
    as-built notes that the Coolify demo has no object lock.
- **acceptance**:
  - After approval, the inspection's documents list shows both the internal and the client report.
  - A user without `report.view` sees no reports there, and the other tenant gets 404.
- **tests**:
  - **integration**:
    - approve an inspection → its documents list has two entries with matching hashes; tenant B → 404
  - **e2e**:
    - if a page shows the list: inspection detail lists the reports (cross-tenant check and axe)
