# ADR 0006: One AWS KMS key per tenant

- **Status:** accepted (owner confirmed 2026-10-10). This reverses the decision "Shared key with tenant prefixes".
- **Date:** 2026-10-07 (revised: the first version's app-held data keys could not crypto-shred S3 objects)
- **Affects:** tenancy, data_io, documents, signing, uploads, security; TENANCY-02, TENANCY-07, UPLOADS-01

## Context

Reviewers flagged the shared key as incompatible with crypto-shred offboarding, per-tenant exports and the
IRAP / Rio Tinto story. The stack review ([08](../reviews/08-stack-decision.md)) found a flaw in the first fix.
SSE-KMS encrypts S3 objects under the KMS key named in each request. A data key held by the app plays no
part in that, so deleting it leaves the tenant's files readable.

## Decision

- **One customer-managed KMS key per tenant**, created at provisioning. The cost is about USD 1 per month per tenant.
- **Uploads:** presigned PUTs set `x-amz-server-side-encryption-aws-kms-key-id` to the tenant's key. A bucket policy per
  tenant prefix rejects any other key.
- **Field-level encrypted columns:** data keys are wrapped by the same tenant key.
- **Crypto-shred:** legal-hold check → schedule key deletion (7–30 day window) → deletion certificate. Legal hold always wins.
- **Documented limits:** RDS rows are deleted, not shredded. Automated backups age out within PITR retention
  (≤ 35 days). Manual snapshots follow a purge procedure.
- **Every tenant gets its own KMS key, on every plan** (owner, 2026-10-10). The cost is small and one code path is
  simpler to audit than a keyed tier and an unkeyed tier. Plans differ by entitlements (ADR 0008), never by whether
  isolation controls exist. All tenants share one database cluster, protected by row-level security (ADR 0015);
  a siloed deployment is an Enterprise option built only when a contract requires it.
- Tenant key prefixes for Redis, queues, S3 and search remain as a second isolation layer. BYOK is a later Enterprise option.

## Consequences

TENANCY-05 provisioning creates the key. UPLOADS-01 enforces it. Dev and Coolify use LocalStack KMS.
