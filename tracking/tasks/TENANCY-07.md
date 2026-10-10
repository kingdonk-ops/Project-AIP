# TENANCY-07 — Offboarding, crypto-shred and deletion certificate

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | AUDIT-05, PLAN-R1, TENANCY-05 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Implement an offboarding workflow that respects legal hold and the shared-key-with-prefix decision.

- **depends on**:
  - TENANCY-05
  - DATABASE-06
- **files**:
  - migrations/versions/0170_offboarding.sql
  - apps/api/src/modules/tenancy/offboarding.service.ts
  - apps/worker/src/jobs/offboarding.job.ts
  - apps/api/src/modules/tenancy/deletion-certificate.ts
- **steps**:
  - 1. Migration for offboarding_runs (tenant_id, step, status, started_at, completed_at) and deletion_certificates (hash, issued_at, scope_summary).
  - 2. Steps in order: freeze the tenant (status offboarding), full export to the tenant prefix, legal-hold check, delete the tenant-prefixed objects, purge the non-held rows, issue the certificate.
  - 3. Block deletion with a clear list of holds if any are active, and carry the held data over as retained.
  - 4. The key step is behind an interface. Under the owner's shared-key decision it is a prefix deletion. A per-tenant KMS key schedule-deletion is a later adapter, and the open question is recorded in the ADR.
  - 5. Generate the certificate with a content hash and the list of retained held items.
- **acceptance**:
  - Offboarding stops before deletion if a hold exists and reports it.
  - The export completes before any deletion starts.
  - The certificate lists what was deleted and what was retained.
- **tests**:
  - **e2e**:
    - As operator, start offboarding for a test tenant that has an export. Expected: the progress screen shows each step, the certificate PDF is downloadable and the tenant's users can no longer log in.
  - **integration**:
    - Place a project hold, then run offboarding. Expected: the run halts at the legal-hold step and names the hold id, with no deletions.
    - Release the hold and run to the end. Expected: the tenant S3 prefix is empty, the tenant rows are purged and the status is offboarded.
    - Run offboarding for A while B has data. Expected: B's rows and objects are unchanged.
  - **unit**:
    - The step machine refuses 'delete' before 'export' is complete.
    - The certificate hash is stable for the same inputs.

## Added by ADR 0021 (2026-10-10)

- Offboarding exports the tenant's retained records (reports, sign-offs, photos, corrective actions, with manifests and hashes) to the customer before crypto-shred; the deletion certificate lists what was exported.
