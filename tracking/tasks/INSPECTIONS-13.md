# INSPECTIONS-13 — Inspections and ITP references (standards, codes, material specs) as asset document sources

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | ASSETS-09, INSPECTIONS-12 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md)
3. [`ASSETS-09.md`](ASSETS-09.md) (the source contract) and [`INSPECTIONS-12.md`](INSPECTIONS-12.md) (D10 references)
4. ADRs: 0039

## Spec

Register the inspections module's documents on the asset documents list (owner 2026-11-03) (tag: extend).

- **files**:
  - apps/api/aip/modules/inspections/asset_documents.py (new), api.py (registration at import)
  - apps/api/aip/modules/inspections/tests/test_asset_documents_db.py
- **steps**:
  - 1. Source `inspection`: every inspection on the asset (any state except soft-deleted), with its status, form
    template and revision, and a link to the inspection; needs `inspection.view`.
  - 2. Source `reference`: the ITP references of those inspections (INSPECTIONS-12 `itp_references`), mapped to
    subkinds standard, code, specification, material spec, drawing and procedure, de-duplicated by kind, code and
    revision (the newest inspection's row wins); a file shows `hasFile` and downloads through the inspections route.
- **acceptance**:
  - An asset's documents list shows its inspections (including ones in progress) and their standards, codes and
    material specs, each once.
- **tests**:
  - **integration**:
    - two inspections citing the same standard revision → one `reference` item; a viewer without `inspection.view`
      → no inspection or reference items; tenant B → none
