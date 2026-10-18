# UPLOADS-08 — Server-side file access in the uploads interface: store a generated file, read and attach a clean stored file

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | UPLOADS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Add to the uploads published interface `store_generated_file` (a worker-made file such as a PDF becomes a clean `stored_files` row in the tenant prefix, with sha256 and size) and `open_stored_file` / `get_stored_file` (read a clean file, check it belongs to the caller's tenant) for report_engine, data_io and evidence links; the session status returns the stored `file_id` once clean, the file-type policy admits CSV and XLSX for imports, and `store_generated_file` takes an `idempotency_key` so a retried job does not leave an orphan object (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
