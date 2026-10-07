# OPS-08 — Backup and restore-test harness with recorded evidence

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Back up the Kaefer AIP Postgres with PITR and record quarterly restore tests as evidence.

- **depends on**:
  - OPS-07
- **files**:
  - scripts/restore-test.sh
  - backend/app/modules/ops/backups.py
  - backend/tests/ops/test_restore_evidence.py
  - infrastructure/coolify/backup.md
- **steps**:
  - 1. Configure WAL archiving or pg_basebackup to S3 or RustFS for the existing Coolify Postgres, as an interim measure.
  - 2. restore-test.sh restores the latest backup to a scratch instance and runs row-count and checksum queries.
  - 3. The script posts the result (duration, row counts, pass or fail, artefact hash) to the restore-test API.
  - 4. The API writes an append-only restore_test_records row.
  - 5. Add a notification when the last test is older than 95 days.
  - 6. Document the procedure and the RPO/RTO measured.
- **acceptance**:
  - A restore test record exists with the measured duration.
  - A failed restore creates a failed record and an alert.
  - The overdue alert fires after 95 days.
- **tests**:
  - **e2e**:
    - Run restore-test.sh against a fixture backup in docker-compose: exits 0 and the record appears on /admin/ops/backups.
  - **integration**:
    - POST a restore result: a row is created and cannot be updated by the app role.
    - The job over a seeded record dated 100 days ago raises a notification.
  - **unit**:
    - is_overdue(last=96 days ago) is true; 90 days is false.
