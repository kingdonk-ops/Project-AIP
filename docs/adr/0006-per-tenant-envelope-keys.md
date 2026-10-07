# ADR 0006: Per-tenant KMS envelope keys

- **Status:** proposed: reverses the decision "Shared key with tenant prefixes". **Owner to confirm**
- **Date:** 2026-10-07
- **Affects:** tenancy, data_io, documents, signing, security; TENANCY-02, TENANCY-07

## Context

The security, SaaS, data and enterprise reviewers all flagged the shared key as incompatible with
crypto-shred offboarding (TENANCY-07), per-tenant export encryption, future customer-managed keys and
the IRAP / Rio Tinto vendor-risk story. Per-tenant data keys cost very little on AWS KMS.

## Decision

- One KMS key per environment wraps **one data key per tenant** (envelope encryption). S3 uses SSE-KMS
  with a `tenant_id` encryption context.
- Crypto-shred deletes the tenant's wrapped data key, **only after** a legal-hold check passes. Legal hold always wins.
- Tenant key prefixes for Redis, queues, S3 and search (TENANCY-02) remain as a second isolation layer.
- Customer-managed keys (BYOK) are a later Enterprise option.

## Consequences

TENANCY-07 and data_io exports use the tenant data key. Dev/Coolify uses a local KMS stub.
