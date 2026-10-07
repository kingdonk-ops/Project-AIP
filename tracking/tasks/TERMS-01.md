# TERMS-01 — Terms schema, default en-AU dictionary and loader
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. [`docs/blueprint/01-decisions.md`](../../docs/blueprint/01-decisions.md) (inspection status vocabulary, RFI as hold point, MEWP/Ladder split, en-AU only at launch)
4. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (no AIP code or data), [0002](../../docs/adr/0002-data-access-and-migrations.md) (Alembic raw SQL, `with_tenant`, roles), [0004](../../docs/adr/0004-repository-layout.md) (`config/terms/en-AU/`, module layout)
5. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/terms/data-model.md) in the module folder; the lifecycle and ITP point types in [`inspections/README.md`](../../docs/blueprint/modules/inspections/README.md); access methods in [`scope_work/README.md`](../../docs/blueprint/modules/scope_work/README.md)

## Spec

Create the dictionary tables, seed the platform en-AU default from the blueprint vocabulary, and load it idempotently.

- **files**:
  - apps/api/migrations/versions/<rev>_terms_tables.py
  - apps/api/aip/modules/terms/__init__.py (exports `api` only)
  - apps/api/aip/modules/terms/manifest.toml
  - apps/api/aip/modules/terms/tables.py
  - apps/api/aip/modules/terms/loader.py
  - apps/api/aip/modules/terms/api.py
  - apps/api/aip/modules/terms/tests/test_loader.py
  - config/terms/en-AU/core.json
  - config/terms/en-AU/inspections.json
  - config/terms/en-AU/scope_work.json
- **steps**:
  - 1. Write one Alembic revision (raw SQL via `op.execute`, from the `db/templates/` tenant-table template) for `term_key`, `term_override`, `term_pack`, `term_pack_version`, `glossary_entry`, `term_alias` and `locale_settings`, with the columns in `data-model.md`. Every table has FORCE RLS. Platform rows use the reserved `PLATFORM_TENANT_ID` (the nil UUID; no FK to `tenants`, since this task does not depend on TENANCY-01). Read policy: `USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid OR tenant_id = PLATFORM_TENANT_ID)`. Write policy (`INSERT`/`UPDATE`, `USING` and `WITH CHECK`): `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND (tenant_id <> PLATFORM_TENANT_ID OR current_user = 'aip_owner')`, so `aip_app` can never write platform rows. Grant `aip_app` SELECT, INSERT, UPDATE (no DELETE; soft delete).
  - 2. Declare the tables as SQLAlchemy Core `Table` objects in `tables.py` (the CI schema-diff check compares them with the migrated schema).
  - 3. Write the en-AU defaults from the blueprint text only (no AIP code, schema or data is read). One JSON file per owning module, each entry `{"key": {"text": "<ICU message>", "description": "<translator context>"}}`, module taken from the file name. Seed at least:
    - `inspection.status.*` from the inspections lifecycle: `draft` "Draft", `assignable` "Assignable", `assigned` "Assigned", `in_progress` "In progress", `inspector_review` "Inspector review", `supervisor_review` "Supervisor review", `client_review` "Client review", `completed` "Completed", `rejected` "Rejected".
    - `inspection.kind.*`: `inspection` "Inspection", `itp` "ITP", `rfi` "RFI" (description: "Inspection kind that is a hold point, not a request for information" per the owner decision).
    - `itp.point_type.*`: `hold` "Hold point", `witness` "Witness point", `review` "Review point", `surveillance` "Surveillance point"; `itp.step.status.*`: pending, ready, in_progress, released, waived, rejected.
    - `access.method.*` from scope_work, with MEWP and Ladder split (owner decision): `ground` "Ground", `rope_access` "Rope access", `scaffold` "Scaffold", `mewp` "MEWP", `ladder` "Ladder".
    - `record.type.*` neutral names from the terms README: `variation` "Variation", `ncr` "NCR", `defect` "Defect", `work_pack` "Work pack".
  - 4. Write an idempotent loader in `loader.py` (`python -m aip.modules.terms.loader config/terms/en-AU`) that upserts `term_key` rows by key with `INSERT ... ON CONFLICT (key) DO UPDATE ... WHERE` the text or description changed, inside `with_tenant(PLATFORM_TENANT_ID)` on a connection as `aip_owner`. It runs in the deploy migrate job right after `alembic upgrade head`. It returns `LoadResult(inserted, updated, unchanged)`.
  - 5. Validate every message parses as ICU MessageFormat with a pure-Python parser (`pyicumessageformat`; no PyICU native build) before writing anything. One bad message aborts the whole load with `InvalidMessageError` naming the key and file.
  - 6. Keep internal status codes out of the display text: the loader rejects a default text that equals a snake_case code (matches `^[a-z0-9]+(_[a-z0-9]+)+$`) or equals its own key.
- **acceptance**:
  - The loader is idempotent.
  - Invalid ICU fails with the key name.
  - Tenant B cannot write platform rows.
  - Every seeded default traces to blueprint text; nothing is extracted from AIP.
- **tests** (pytest; integration uses testcontainers-python Postgres with the real roles):
  - **e2e**:
    - None; covered in later tasks.
  - **integration**:
    - Load twice. Expected: the first run reports `inserted == N` (N = keys across `config/terms/en-AU/*.json`), the second reports `inserted == 0, updated == 0`, and `SELECT count(*) FROM term_key` is unchanged.
    - As `aip_app` with `app.tenant_id` = tenant B, inserting a `term_override` row with `tenant_id = PLATFORM_TENANT_ID` fails the WITH CHECK. Setting `app.tenant_id` to `PLATFORM_TENANT_ID` as `aip_app` and inserting also fails.
    - As `aip_app` with tenant B set, `SELECT text FROM term_key WHERE key = 'inspection.status.completed'` returns "Completed" (platform rows are readable).
    - After load, the keys `inspection.status.completed`, `access.method.mewp` and `access.method.ladder` exist as separate rows.
  - **unit**:
    - Loader rejects `'{count, plural, one {# item}'` (unbalanced) with an error naming the key.
    - Loader rejects `{"inspection.status.in_progress": {"text": "in_progress"}}` as an internal code.
