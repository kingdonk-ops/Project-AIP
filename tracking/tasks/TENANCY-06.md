# TENANCY-06 — Quotas and support-access grants

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TENANCY-05, TENANCY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Limit noisy neighbours and make support access customer-approved and time-boxed.

- **depends on**:
  - TENANCY-05
  - TENANCY-02
- **files**:
  - migrations/versions/0160_quotas_support_access.sql
  - apps/api/src/modules/tenancy/quota.service.ts
  - apps/api/src/modules/tenancy/support-access.service.ts
  - apps/api/src/modules/tenancy/quota.guard.ts
- **steps**:
  - 1. Migration for tenant_usage (tenant_id, metric, period, value) and support_access_grants (tenant_id, requested_by, approved_by, starts_at, expires_at, ticket_ref, revoked_at).
  - 2. The quota guard uses Redis counters from the key builders for API calls, with a 429 response and a Retry-After header. Storage and job quotas are checked on enqueue and upload.
  - 3. Emit notification events at 80% and 100%.
  - 4. Support access requires tenant admin approval and has a maximum duration setting. Every use writes an audit event and sets a banner flag in the context.
  - 5. Expire grants automatically.
- **acceptance**:
  - One tenant exceeding its limit does not slow others.
  - Support access without an approval is refused.
  - An expired grant stops working at its expiry time.
- **tests**:
  - **e2e**:
    - As tenant admin, approve a support request. Expected: the support user sees a banner while acting and the access history lists the session. Revoke it. Expected: the next support request returns 403.
  - **integration**:
    - Set the API quota to 10/min and send 11 requests as A and 1 as B. Expected: A's 11th gets 429 with Retry-After, and B's request gets 200.
    - Request support access, approve it for 1 hour and use it. Expected: an audit row with the ticket_ref exists.
    - Advance the clock by 61 minutes. Expected: 403.
  - **unit**:
    - The quota check at 80/100 returns warn and at 101/100 returns block.
    - A grant duration above the max throws.
