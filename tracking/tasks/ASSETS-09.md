# ASSETS-09 — Asset documents list: every document that goes with an asset that has been or is being inspected

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`assets`](../../docs/blueprint/modules/assets/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ASSETS-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/assets/README.md`](../../docs/blueprint/modules/assets/README.md)
3. [`docs/reviews/13-merged-pr-review-2026-11-03.md`](../../docs/reviews/13-merged-pr-review-2026-11-03.md) (D3)
4. ADRs: 0039 (#49, with the owner's 2026-11-03 line), 0037

## Spec

Owner 2026-11-03: the documents for an inspection are listed on the **asset** that has been or is being inspected.
The list shows every accompanying document: inspection reports, inspections, standards, codes, qualifications and
material specs (tag: extend).

- **files**:
  - apps/api/aip/modules/assets/documents.py (new: source registry and aggregation)
  - apps/api/aip/modules/assets/api.py (`register_asset_document_source`), routes.py, schemas.py
  - apps/web/src/features/assets/AssetDocuments.tsx (the Documents tab on the ASSETS-05 detail page)
  - apps/web/src/features/assets/__tests__/documents.test.tsx
  - config/terms/en-AU/assets.json
  - apps/api/aip/modules/assets/tests/test_asset_documents_db.py
  - e2e/web/asset-documents.spec.ts
- **steps**:
  - 1. **Source registry.** Assets cannot import the modules that own the documents (they depend on assets), so it
    exposes `register_asset_document_source(kind, fn)`; each owning module registers a source at import:
    `report` (REPORTS-08), `inspection` and `reference` with kinds standard, code, specification, material spec,
    drawing, procedure (INSPECTIONS-13), `qualification` (ELIGIBILITY-01 or a later eligibility task). A source
    returns items `{kind, subkind, code, title, revision, status, date, recordType, recordId, href, hasFile}` for an
    asset id and the caller's principal, already filtered by its own permissions.
  - 2. `GET /api/v1/assets/{assetId}/documents?kind=&q=&cursor=&limit=`: `asset.view` on the asset (404 outside the
    caller's scope), runs every registered source, merges and sorts newest first, groups by kind; one failing source
    returns the others plus a `partial: [kind]` flag, never a 500. `includeDescendants=true` adds the asset's
    subtree.
  - 3. The Documents tab lists the groups (Reports, Inspections, Standards and codes, Material specs,
    Qualifications), with filters, search and links to each record or download. Downloads go through each owner's
    route (the upload pipeline), never a direct storage link.
- **acceptance**:
  - An asset with an approved inspection lists its reports, the inspection, the ITP's standards, codes and material
    specs, and the inspectors' qualifications once their sources are registered.
  - An inspection still in progress is listed with its status.
  - A user sees only documents each owning module lets them see; another tenant gets 404.
- **tests**:
  - **unit**:
    - aggregation: two stub sources merge and sort; one raising → the other's items and `partial`
  - **integration**:
    - stub sources registered by the test: the list honours `kind`, `q` and the cursor; an asset outside the caller's
      project scope → 404; tenant B → 404
  - **e2e**:
    - the Documents tab on the asset detail page shows the groups (desktop, mobile, iPad; cross-tenant 404; axe)
