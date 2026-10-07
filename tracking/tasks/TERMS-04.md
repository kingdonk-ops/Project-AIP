# TERMS-04 — Pack import, diff, dry-run, apply and rollback

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | PLAN-R1, TERMS-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Manage terminology packs as versioned data with preview and rollback.

- **depends on**:
  - TERMS-02
- **files**:
  - backend/app/modules/terms/packs.py
  - backend/tests/terms/test_packs.py
  - backend/app/modules/terms/packs_builtin/au-mining.json
- **steps**:
  - 1. Define the pack JSON schema (code, name, version, entries key to locale to text).
  - 2. import_pack validates keys against term_key, rejecting unknown keys, and stores a sha256.
  - 3. diff(version_a, version_b) lists added, changed and removed keys.
  - 4. dry_run(pack, tenant) lists the keys that would change and the surfaces where they appear (UI, email, PDF, export).
  - 5. apply sets active_version_id and emits terms.pack.activated.
  - 6. rollback re-activates the prior version.
- **acceptance**:
  - An unknown key is rejected.
  - The dry run changes no data.
  - Rollback restores previous effective text.
- **tests**:
  - **e2e**:
    - Admin imports au-mining.json, reviews the diff, applies it, and the status chip labels change.
  - **integration**:
    - Import, then dry-run: effective text unchanged.
    - Apply then resolve gives the new text; rollback then resolve gives the old text.
    - Importing the same hash twice does not create a second version.
  - **unit**:
    - diff of {a:'X'} against {a:'Y',b:'Z'} gives 1 changed and 1 added.
    - A pack with a bad ICU message is rejected.
