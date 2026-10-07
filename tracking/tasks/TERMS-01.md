# TERMS-01 — Terms schema, default en-AU dictionary and loader

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Create the dictionary tables and seed the platform default.

- **files**:
  - backend/app/modules/terms/models.py
  - backend/migrations/versions/xxxx_terms_tables.py
  - backend/app/modules/terms/defaults/en-AU.json
  - backend/app/modules/terms/loader.py
  - backend/tests/terms/test_loader.py
- **steps**:
  - 1. Write the migration for term_key, term_override, term_pack, term_pack_version, glossary_entry, term_alias and locale_settings, with RLS that permits reading platform rows.
  - 2. Add models.
  - 3. Extract the current hard-coded labels from AIP (inspection statuses, ITP, hold point, RFI as hold point, access methods MEWP and Ladder) into en-AU.json keys.
  - 4. Write an idempotent loader that upserts keys by key.
  - 5. Validate every ICU message parses.
  - 6. Keep internal status codes out of the display text.
- **acceptance**:
  - The loader is idempotent.
  - Invalid ICU fails with the key name.
  - Tenant B cannot write platform rows.
- **tests**:
  - **e2e**:
    - None; covered in later tasks.
  - **integration**:
    - Load twice: the key count is unchanged.
    - The app role as tenant B inserting a row with the platform tenant id is denied.
    - The keys inspection.status.approved and access.method.mewp exist after load.
  - **unit**:
    - Loader rejects '{count, plural, one {# item}' (unbalanced) naming the key.
