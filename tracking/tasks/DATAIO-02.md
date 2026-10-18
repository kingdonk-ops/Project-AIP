# DATAIO-02 — Asset tree import with hierarchy preview, duplicate-tag detection and batch rollback

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`data_io`](../../docs/blueprint/modules/data_io/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ASSETS-02, DATAIO-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`DATAIO-01.md`](DATAIO-01.md) (the import machinery and registry this importer plugs into), [`ASSETS-01.md`](ASSETS-01.md) and [`ASSETS-02.md`](ASSETS-02.md) (the `AssetsApi` functions used below)
3. [`docs/blueprint/modules/data_io/README.md`](../../docs/blueprint/modules/data_io/README.md) ("Asset tree import" and "Import batches with rollback")
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (ltree stays for the asset tree), [0004](../../docs/adr/0004-repository-layout.md) (only `api.py` crosses modules), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md), [0036](../../docs/adr/0036-r1-module-decisions.md)

> Scope. Create mode only, one item type per import (a mixed-type tree is imported in passes: later passes attach to
> earlier ones by Tag Number). No migration: DATAIO-01's tables already hold the batch, items and rollback state.
> Update-by-key is DATAIO-05; the AIP migration is DATAIO-04 (blocked on OPEN-QUESTIONS #54). Legal hold does not
> exist in R1, so rollback has no `blocked_legal_hold` state yet.

## Spec

Register an `asset_tree` importer that resolves each row's parent by Tag Number or by a Tag Number path, shows the resulting hierarchy with orphans, duplicate tags and cycles in the dry run, creates the assets through `AssetsApi` in parent-first order, and can roll back a whole committed batch by soft delete (tag: extend).

- **files**:
  - apps/api/aip/modules/data_io/importers/__init__.py
  - apps/api/aip/modules/data_io/importers/asset_tree.py
  - apps/api/aip/modules/data_io/tree.py
  - apps/api/aip/modules/data_io/rollback.py
  - apps/api/aip/modules/data_io/service.py
  - apps/api/aip/modules/data_io/routes.py
  - apps/api/aip/modules/data_io/schemas.py
  - apps/api/aip/modules/data_io/events.py
  - apps/api/aip/modules/data_io/manifest.toml
  - apps/api/aip/modules/data_io/api.py
  - apps/api/aip/modules/data_io/tests/test_tree.py
  - apps/api/aip/modules/data_io/tests/test_asset_tree_import_db.py
  - apps/api/aip/modules/data_io/tests/test_rollback_db.py
  - config/terms/en-AU/data_io.json
  - packages/api-client/openapi.json (regenerated)
- **steps**:
  - 1. `importers/asset_tree.py` registers `register_importer("asset_tree", AssetTreeImporter())` with
    `target_permission = "asset.create"`. Options (strict model): `itemTypeId` (required uuid),
    `parentResolution` (`tag_number` | `path`, default `tag_number`), `pathSeparator` (default `/`, one of `/ > \ |`).
    The pinned version is `aip.modules.item_types.api.ItemTypesApi.get_published_version(conn, item_type_id)`; no
    published version → 422 `ITEM_TYPE_NOT_PUBLISHED` at `POST /imports`.
  - 2. Fields (from `fields(conn, options)`): `tag_number` (text, required, max 64), `name` (text, required, max
    200), `parent_tag_number` (text, used when `parentResolution = tag_number`) or `parent_path` (text, used when
    `path`), plus one field per attribute of the pinned version's schema, keyed `attr.<key>`, typed from the field
    type (`text`/`dropdown` → text, `number` → integer, `decimal`/`measurement` → decimal, `date`, `boolean`; field
    types the import cannot carry — `photo`, `signature`, `asset_ref`, `user_ref`, `multi_select` — are not offered).
    The CSV template (`GET /importers/asset_tree/template.csv?itemTypeId=...`) lists these keys.
  - 3. `tree.py` — a pure function `plan_tree(rows, existing) -> TreePlan` (no I/O; `existing` is a lookup the
    importer fills through `AssetsApi.find_by_tag_number(conn, tag)` for every distinct parent tag and row tag):
    - Tag numbers compare trimmed and case-sensitive, as ASSETS-01 stores them.
    - `duplicate_tag`: a tag on two or more rows (every such row gets the error, `params.rows` lists the others), or
      a tag that already belongs to a live asset (`params.existingAssetId`).
    - Parent by `tag_number`: an empty parent makes a root; otherwise the parent is the row with that tag in the
      file (before or after this row) or else an existing asset; neither → `orphan_parent`.
    - Parent by `path`: segments split on the separator and trimmed, root first, the last segment being the parent.
      Each segment resolves in the file or to an existing asset, and each segment's parent must be the segment before
      it (for existing assets checked with `AssetsApi.get_asset(conn, id).parent_id`); an unresolved segment →
      `orphan_parent` (`params.segment`), a mismatch → `path_mismatch` (`params.segment`, `params.actualParentTag`).
    - `parent_cycle`: rows whose parents loop (A under B, B under A); every row on the loop gets it.
    - `parent_has_errors`: a row whose parent row in the file has any error (so no subtree is half-created).
    - `tree_too_deep`: a resulting depth over 20 levels from the root.
    - Order: parents before children (stable by row number within a level).
    - Preview: nodes `{tag, name, rowNumber | null, marker: "new" | "existing", children}` for the new rows and the
      existing assets they attach to, capped at 500 nodes (`truncated: true` beyond), and counts `{rows, new,
      roots, attachedToExisting, orphans, duplicates, cycles, errors}`. It becomes `dry_run_result.preview`.
  - 4. `validate` runs `plan_tree`, then checks attributes per row with
    `aip.modules.item_types.api.ItemTypesApi.validate_attributes(conn, version_id, attributes)`; each
    `AttributeValidationError` becomes row error `invalid_attribute` on column `attr.<key>`. Empty attribute cells
    are left out of `attributes`.
  - 5. `commit` re-plans (DATAIO-01 already re-checks the cells), walks the parent-first order and calls
    `AssetsApi.create_asset(conn, ctx.actor_id, {parent_id, name, tag_number, item_type_version_id, attributes})`,
    with `parent_id` the id just created for a file parent or the existing asset's id. Per created asset it calls
    `recorder.record("asset", asset.id, action="created", asset_id=asset.id, after_hash=...)`, where `after_hash` is
    the sha256 (hex) of canonical JSON (`rfc8785`) of `{name, tag_number, parent_id, item_type_version_id,
    attributes}` as `create_asset` returned them. Any `create_asset` error fails the whole commit (DATAIO-01 rolls
    the transaction back).
  - 6. `rollback.py` and `POST /api/v1/imports/{id}/rollback {reason}` (`import.rollback`, a new manifest
    permission, plus `asset.delete` on the job's project; `reason` 3–500 characters):
    - Allowed only when the job is `committed` and its batch `rollback_state` is `none` or `blocked_downstream`
      (else 409 `INVALID_IMPORT_STATE`). The batch row is locked `FOR UPDATE`, so two rollbacks cannot both run.
    - For each batch item, `AssetsApi.get_asset(conn, record_id)`: already deleted → skipped (counted);
      `after_hash` recomputed from the current asset differs → blocker `edited_since_import` with the tag;
      `AssetsApi.subtree_ids(conn, record_id)` contains an id not in the batch → blocker `children_added` with the
      tag and the count of foreign descendants.
    - Any blocker → no change to assets; the batch becomes `blocked_downstream` with `rollback_block_reason =
      {blockers: [{code, tag, ...}]}` (first 100) and the call returns 409 `ROLLBACK_BLOCKED` with the same list.
    - Otherwise one call `AssetsApi.soft_delete_assets(conn, ids, reason=f"import rollback {batch_id}: {reason}")`
      (children before parents is the assets module's concern; it is all or nothing). If it refuses because an asset
      is in use (for example by an inspection), that is a `blocked_downstream` blocker `in_use` and nothing changes.
    - On success, in one transaction: every item `rolled_back = true`, the batch `rolled_back` with
      `rolled_back_by`/`rolled_back_at`, the job status `rolled_back`, and
      `emit(conn, "import.batch_rolled_back", 1, ...)` with `{importJobId, importBatchId, kind, projectId,
      rolledBackCount, skippedCount, reason}` (declared in `manifest.toml`).
  - 7. `GET /api/v1/imports/{id}/batch` (`import.view`) → the batch with counts, `rollbackState`,
    `rollbackBlockReason`, and a cursor-paged item list `{recordId, assetId, action, rolledBack}`.
  - 8. Term keys for `orphan_parent`, `duplicate_tag`, `parent_cycle`, `parent_has_errors`, `path_mismatch`,
    `tree_too_deep`, `invalid_attribute`, `edited_since_import`, `children_added`, `in_use`, the options and the
    preview markers in `config/terms/en-AU/data_io.json`.
- **acceptance**:
  - A CSV describing a 3-level tree imports in one commit with every child under the right parent, whichever order
    the rows are in, and rows can attach to assets that already exist.
  - The dry run reports orphans, duplicate tags (in the file and against existing assets), cycles and path mismatches
    as row errors, shows the resulting tree with new and existing markers, and creates no asset.
  - A committed batch rolls back by soft-deleting exactly its assets, once; a batch whose assets were edited, gained
    children or are in use is refused with the blockers listed and nothing changes.
  - All asset reads and writes go through `aip.modules.assets.api.AssetsApi`; data_io never reads the `assets` table.
- **tests**:
  - **unit** (`test_tree.py`, `plan_tree` with an in-memory `existing` lookup):
    - Rows `(row 2: P-1, parent "")`, `(row 3: V-10, parent P-1)`, `(row 4: N-1, parent V-10)` given in the order
      4, 3, 2 → order `P-1, V-10, N-1`; counts `{rows: 3, new: 3, roots: 1, errors: 0}`.
    - Two rows with tag `V-10` → both rows `duplicate_tag`, each `params.rows` naming the other.
    - Row `V-11` with parent `U-999` (not in file, not existing) → `orphan_parent`; its child row → `parent_has_errors`.
    - Row `V-12` with parent `SITE-1`, which `existing` resolves → no error; the preview shows `SITE-1` with marker
      `existing` and `V-12` under it as `new`; `attachedToExisting = 1`.
    - Row tag `SITE-1` when `existing` has `SITE-1` → `duplicate_tag` with `params.existingAssetId`.
    - `A` under `B` and `B` under `A` → both `parent_cycle`.
    - Path mode, separator `/`: `parent_path = "SITE-1 / U-100"` where existing `U-100`'s parent is `SITE-2` →
      `path_mismatch` with `segment = "U-100"`, `actualParentTag = "SITE-2"`.
    - A 21-level chain → the 21st-level row `tree_too_deep`.
    - 600 new rows → preview `truncated: true` with 500 nodes, counts still 600.
  - **integration** (testcontainers-python Postgres, `kaefer-demo` and `tenant-b`, an item type `equipment` with a
    published version whose schema has `design_pressure` (decimal, optional) and `material` (dropdown `CS`, `SS`,
    required)):
    - Existing root `SITE-1` created through `AssetsApi.create_asset`. CSV rows (header `Tag Number,Name,Parent Tag
      Number,material,design_pressure`): `U-100,Unit 100,SITE-1,CS,`, `V-101,Vessel 101,U-100,SS,12.5`,
      `V-102,Vessel 102,U-100,Brass,-3` with `itemTypeId = equipment`. Dry run → `errorCount = 1` (row 4
      `invalid_attribute` on `attr.material`) and `-3` accepted as a decimal. Fix the cell to `CS`, upload again, new
      job → `errorCount = 0`, preview root `SITE-1` (`existing`) → `U-100` → `V-101`, `V-102`;
      `SELECT count(*) FROM assets` unchanged.
    - Commit → 3 new `assets` rows; `V-101`'s parent is `U-100`'s id; each pins the published version id; 3
      `import_batch_items` rows with `asset_id` set; `import.committed` v1 with `createdCount = 3`.
    - A file repeating `SITE-1` as a row tag → `duplicate_tag` on that row; commit → 409 `IMPORT_HAS_ERRORS`.
    - Rollback with `reason = "wrong unit"` → 200; the 3 assets are soft-deleted (`AssetsApi.get_asset` → none),
      `SITE-1` is untouched, the batch `rolled_back`, the job `rolled_back`, 1 `domain_events` row
      `import.batch_rolled_back` v1 with `rolledBackCount = 3`. A second rollback → 409 `INVALID_IMPORT_STATE`.
    - After commit, rename `V-101` through `AssetsApi` → rollback 409 `ROLLBACK_BLOCKED` with
      `{code: "edited_since_import", tag: "V-101"}`; the 3 assets still exist; the batch is `blocked_downstream`.
    - After commit, a user creates `N-1` under `V-102` by hand → rollback 409 with `children_added` for `V-102`.
    - A user with `import.rollback` but without `asset.delete` → 403 and nothing changes; with neither → 403.
    - Two concurrent rollbacks of the same batch → one 200, one 409.
    - A `tenant-b` user: `POST /api/v1/imports/{kaefer job id}/rollback` → 404; `GET .../batch` → 404. A `tenant-b`
      import whose parent tag is `SITE-1` (a `kaefer-demo` asset) → `orphan_parent` (tags never resolve across
      tenants).
    - `POST /imports` with `options = {"itemTypeId": <draft-only type>}` → 422 `ITEM_TYPE_NOT_PUBLISHED`; with an
      extra option key → 422.
  - **e2e**:
    - API-only task: the dry run, commit and rollback run in-process against Postgres in the integration tests above.
      The browser journey (tree preview, commit and rollback from the history page), its cross-tenant check and axe
      run are DATAIO-03's.
