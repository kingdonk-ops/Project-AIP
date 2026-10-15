# UPLOADS-07 — Enforce per-tenant SSE-KMS on the presigned upload

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | TENANCY-05, UPLOADS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md)
3. ADRs: [0006](../../docs/adr/0006-per-tenant-envelope-keys.md) (SSE-KMS per tenant),
   [0004](../../docs/adr/0004-repository-layout.md) (module boundaries)

## Spec

Wire the tenant's KMS key into the UPLOADS-01 presigned POST so SSE-KMS with the tenant encryption
context is required for every upload (ADR 0006: "UPLOADS-01 enforces it").

Discovered during UPLOADS-01 (tag: harden). ADR 0006 says the presigned upload must set the
tenant's KMS key and that TENANCY-05 provisions it. At the time UPLOADS-01 landed, TENANCY-05 was
not done and the tenancy published interface (`TenantView`) deliberately exposes no key reference,
so uploads could not read the key without breaking the module boundary (cross-module table access
is forbidden). UPLOADS-01 therefore built the full SSE-KMS presign policy (`build_post_policy`,
unit-tested) behind a `_resolve_kms_key_ref` seam that returns `None` for now, so uploads already
enforce the key, size and content type — only the SSE-KMS conditions are omitted until a key source
exists. This task closes that gap.

- **files**:
  - `apps/api/aip/modules/uploads/service.py` (replace the `_resolve_kms_key_ref` stub)
  - `apps/api/aip/modules/tenancy/api.py` (TENANCY-05/this task: expose the tenant KMS key ref to
    callers that need it, without widening `TenantView`)
- **steps**:
  - 1. Add a tenancy published-interface function that returns the current tenant's KMS key
    reference inside `with_tenant` (e.g. `tenant_kms_key_ref(conn)`), keeping it off `TenantView`.
  - 2. Have `uploads` call it from `_resolve_kms_key_ref`, so the presign requires
    `x-amz-server-side-encryption: aws:kms`, the tenant's key id, and the ADR 0006 encryption
    context. Fail closed when a tenant has no key (reject the session rather than presign without
    SSE-KMS) once every live tenant is provisioned.
- **acceptance**:
  - A presigned POST for a provisioned tenant includes the SSE-KMS conditions, and an upload that
    omits or changes the encryption headers is refused by the store (LocalStack KMS in tests).
  - No cross-module table access: uploads reads the key only through the tenancy interface.
- **tests**:
  - **unit**:
    - `_resolve_kms_key_ref` returns the tenancy-provided key; `build_post_policy` then carries the
      SSE-KMS conditions (already covered by UPLOADS-01's policy unit test).
  - **integration**:
    - LocalStack S3 + KMS: a presigned POST without the SSE-KMS headers is rejected; with them the
      object is stored under `aws:kms` with the tenant key and encryption context.
  - **e2e**:
    - Covered by the UPLOADS-01 presign journey once the demo tenants are KMS-provisioned.
