# TESTING-05 — Migration up-down-up test

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | TESTING-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Prove every Alembic migration is reversible and repeatable on every PR.

- **depends on**:
  - TESTING-01
- **files**:
  - backend/tests/migrations/test_up_down_up.py
  - scripts/snapshot_migration_check.sh
- **steps**:
  - 1. On a clean container, run upgrade head, then dump the schema (pg_dump -s).
  - 2. Run downgrade base, then upgrade head, then dump again.
  - 3. Assert the two dumps are identical after normalising.
  - 4. Add snapshot_migration_check.sh, which restores a snapshot path from an env var and runs upgrade head with timing output.
  - 5. Wire the script as a release-only CI job.
- **acceptance**:
  - A migration with a broken downgrade fails the PR.
  - The snapshot script fails if upgrade takes longer than the configured limit (default 15 min).
- **tests**:
  - **e2e**:
    - The release workflow runs the snapshot check on the staging snapshot and uploads the timing artefact.
  - **integration**:
    - Full up-down-up passes on the current migrations.
    - A fixture migration with an empty downgrade makes the dumps differ, so the test fails.
  - **unit**:
    - Schema dump normaliser strips comments and ordering noise: two equal schemas produce equal output.
