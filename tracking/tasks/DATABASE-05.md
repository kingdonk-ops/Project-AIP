# DATABASE-05 — Append-only grants and time partitioning

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Make evidence tables immutable to the app role and manage partitions automatically.

- **depends on**:
  - DATABASE-03
- **files**:
  - migrations/versions/0120_append_only_grants.sql
  - migrations/versions/0121_partition_responses_audit.sql
  - apps/worker/src/jobs/partition-manager.ts
- **steps**:
  - 1. REVOKE UPDATE, DELETE and TRUNCATE on inspection_responses, audit_log and sync_operations from the app role.
  - 2. Convert those tables and activity to monthly range partitions on the occurred or created timestamp, using expand and contract with a copy.
  - 3. Write the partition manager job that creates the next 3 months and alerts when creation fails.
  - 4. Add a partition_interval setting per table.
  - 5. Verify the inspection_current_responses view still returns the latest value per field.
- **acceptance**:
  - UPDATE and DELETE as app fail with permission denied.
  - The partition for next month exists at all times.
  - No data is lost in the conversion.
- **tests**:
  - **e2e**:
    - Submit an inspection response, then query inspection_current_responses. Expected: the latest value is returned and the history endpoint lists both entries.
  - **integration**:
    - As app: UPDATE inspection_responses SET value='x'. Expected: permission denied.
    - Insert a row dated next month before the manager runs. Expected: it fails or goes to default, and after the manager runs, inserts succeed.
    - Compare the row count and a checksum before and after the conversion. Expected: identical.
  - **unit**:
    - The partition name builder returns 'audit_log_2025_07' for 2025-07-15.
    - The manager computes a missing-partition list [2025_08, 2025_09] given only 2025_07 exists.
