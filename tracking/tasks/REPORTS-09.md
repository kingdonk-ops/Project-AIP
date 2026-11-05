# REPORTS-09 — Client report labels never carry the internal asset tag

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`report_engine`](../../docs/blueprint/modules/report_engine/README.md) |
| Phase | R1 |
| Size | XS |
| Depends on | REPORTS-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/report_engine/README.md`](../../docs/blueprint/modules/report_engine/README.md)
3. [`tracking/tasks/REPORTS-07.md`](REPORTS-07.md) (As built: the variant reaches the provider)
4. ADRs: 0036, 0039

## Spec

Found in the review of PR #238 (REPORTS-07; tag: harden). REPORTS-07 removed the internal fields from the client
snapshot, but the render job's register label (`record_label`, REPORTS-04) still comes from
`asset.tag_number or asset.internal_tag` for every variant. When an asset has no tag number, a client report's label
holds the internal tag, which shows in the report register and will show in the portal's client report list
(PORTAL-05).

- **files**:
  - apps/api/aip/modules/report_engine/providers/inspection.py
  - apps/api/aip/modules/report_engine/render_service.py (rerender, only if step 2 needs it)
  - apps/api/aip/modules/report_engine/tests/
- **steps**:
  - 1. For any variant except `internal`, the inspection provider's `label` uses only the asset's tag number,
    never `internal_tag`. With no tag number the label is `"<project code> <asset name>"`. The internal variant
    keeps the current fallback.
  - 2. A rerender copies the first job's `record_label`. Check whether any stored client job's label holds an
    internal tag (count them on the demo database). If there are none, write that in the as-built note and change
    nothing. If there are some, ask the owner before adding a data fix, because rewriting labels needs the asset rows,
    which belong to another module.
- **acceptance**:
  - A client-variant inspection report for an asset without a tag number has a register label with no internal tag;
    the internal variant's label is unchanged.
- **tests**:
  - **unit**:
    - client provider, asset with `tag_number = None` → label is `"KF-01 Process line P-1001"`, no `AS-` tag;
      internal provider on the same data → label keeps the internal tag
  - **integration**:
    - none (the provider decides the label; REPORTS-04's register tests still pass)
  - **e2e**:
    - none
