# AUDIT-03 — Chain verifier CLI + S3 Object Lock anchoring job

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`audit`](../../docs/blueprint/modules/audit/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | AUDIT-01, OPS-02, OPS-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/audit/README.md`](../../docs/blueprint/modules/audit/README.md)
3. ADRs: 0003 (BullMQ job classes, handlers re-enter `withTenant`), 0006 (per-tenant KMS, SSE-KMS), 0004 (`infra/terraform`)
4. Only if the step needs it: the `audit_anchors` table in [`data-model.md`](../../docs/blueprint/modules/audit/data-model.md); risk #6 and ADR recommendation 5 in [`docs/reviews/01-security.md`](../../docs/reviews/01-security.md)

## Spec

Make tamper evidence independent of the platform. A scheduled job writes each tenant's chain heads to an S3 bucket with Object Lock, and a standalone verifier CLI recomputes a chain from an export or a read-only connection and checks it against those anchors.

- **files**:
  - db/migrations/<timestamp>_audit_anchors.sql
  - apps/api/src/modules/audit/jobs/anchor.job.ts
  - apps/api/src/modules/audit/anchor.service.ts
  - apps/api/src/modules/audit/verifier/cli.ts
  - apps/api/src/modules/audit/verifier/verify.ts
  - apps/api/src/modules/audit/verifier/build.mjs
  - apps/api/src/modules/audit/tests/
  - infra/terraform/modules/audit-anchor/main.tf (the only file outside the module)
- **steps**:
  - 1. Write an append-only migration for `audit_anchors`: id, tenant_id, stream, through_seq, head_hash, s3_bucket, s3_key, s3_version_id, retain_until, anchored_at and created_at. Index (tenant_id, stream, through_seq). Insert is allowed for aip_audit_writer only. Apply the same REVOKE and trigger as AUDIT-01, with FORCE RLS.
  - 2. In infra/terraform/modules/audit-anchor, define a dedicated bucket with `object_lock_enabled = true`, default retention in GOVERNANCE mode (COMPLIANCE only after the retention schedule is approved, controlled by a variable), versioning, SSE-KMS, public access blocked, and a bucket policy denying `s3:DeleteObject*`, `s3:PutObjectRetention` (except by a break-glass role) and `s3:BypassGovernanceRetention`. The anchor writer IAM role has `s3:PutObject` only. Wire it into `infra/terraform/envs/staging` as one module block. A separate AWS account is recommended; record it as a stub follow-up if the landing zone is not ready.
  - 3. In anchor.service.ts and anchor.job.ts, register the job type `audit.anchor` with OPS-02's BullMQ handler registry and a repeatable schedule (`AUDIT_ANCHOR_INTERVAL`, default 1h). For each tenant and stream whose head moved since the last anchor, the job re-enters `withTenant`, reads `audit_chain_heads`, and PUTs `anchors/<tenant_id>/<stream>/<through_seq>.json` = `{spec:1, tenant_id, stream, through_seq, head_hash_hex, anchored_at}` with `ObjectLockMode` and `RetainUntilDate = now + AUDIT_ANCHOR_RETENTION_DAYS` (default 2555). It then inserts the `audit_anchors` row with the returned VersionId and emits `audit.anchor_published`. Enumerating tenants uses the narrow cross-tenant path defined for the dispatcher (ADR 0002 roles), not aip_app without context.
  - 4. Fail closed. At job start, call `GetObjectLockConfiguration`. If Object Lock is not enabled, the job fails with `ANCHOR_BUCKET_NOT_LOCKED`, writes nothing and raises an alert. A PUT failure retries with backoff and never inserts a row without a VersionId.
  - 5. In verifier/verify.ts, the logic is pure and imports only `chain-hash.ts`. `verifyChain(rows, anchors?)` walks rows ordered by seq, recomputes each hash, and checks seq continuity, prev_hash linkage and every anchor's head_hash at through_seq. It returns `{ok, checked, firstBreak?:{seq, reason:'hash_mismatch'|'seq_gap'|'prev_mismatch'|'anchor_mismatch'}}`.
  - 6. In verifier/cli.ts, the CLI is `aip-audit-verify --file rows.jsonl [--anchors dir|s3://bucket/prefix] [--tenant id] [--stream audit|security]`, or `--db <readonly url> --tenant <id>`, which connects as aip_readonly and sets the tenant. It exits 0 when OK, 2 on a chain break (printing the first break), and 1 on usage or IO errors. build.mjs uses esbuild to bundle it into one dependency-free `dist/aip-audit-verify.mjs` that runs on Node 22 with no repo checkout. Add `pnpm audit:verify` at the root.
- **acceptance**:
  - After a run, each tenant with new entries has exactly one new locked object and one `audit_anchors` row. Deleting the object as the app role is denied.
  - The bundled CLI verifies an exported chain on a machine with only Node 22, and detects any single-byte change in any row.
  - The job refuses to run against a bucket without Object Lock.
- **tests**:
  - **unit**:
    - verifyChain on the 3-row golden fixture returns `{ok:true, checked:3}`.
    - Flipping one character of row 2's payload returns `firstBreak:{seq:2, reason:'hash_mismatch'}`. Removing row 2 returns `{seq:3, reason:'seq_gap'}`.
    - An anchor `{through_seq:3, head_hash:'00…'}` against a valid chain returns `anchor_mismatch` at seq 3.
    - The anchor key builder gives `anchors/<uuid>/audit/120.json` for through_seq 120.
  - **integration** (Testcontainers Postgres and a MinIO container with an object-lock bucket):
    - Append 10 entries for tenant A, then run the job. Expected: 1 object with retention mode GOVERNANCE, 1 anchor row with through_seq 10, and a non-null s3_version_id. Run it again with no new entries. Expected: no new object.
    - Run the job against a bucket created without object lock. Expected: the job fails with `ANCHOR_BUCKET_NOT_LOCKED`, and 0 anchor rows exist.
    - DeleteObject on the anchor version without bypass. Expected: AccessDenied.
    - `aip-audit-verify --db <readonly url> --tenant A --anchors s3://…` exits 0. After the owner disables the trigger in the test DB and edits one row, it exits 2 and prints the seq.
  - **e2e**:
    - In staging, after the scheduled run, `aws s3api get-object-retention` on the newest kaefer-demo anchor shows Mode GOVERNANCE and a RetainUntilDate about 7 years ahead. Running the bundled CLI on a fresh machine against a JSONL export exits 0.
