# ADR 0017: Company systems stay outside the product; the tenant contract is the link

- **Status:** proposed: **owner to confirm**
- **Date:** 2026-10-10
- **Affects:** tenancy, ops, access matrix, docs/internal; ENT-01, ENT-02, TENANCY-05, OPS-12

## Context

ADR 0008 makes onboarding sales-led with contract billing and no payment provider, but nothing says where
quotes, contracts, invoices, support and compliance evidence live, or how a signed contract becomes a tenant.
A review of the plans also found three inconsistencies: the Super Admin column of the access matrix granted
`admin` on all tenant business modules while the account definition says "no standing access to tenant business
data"; operator pages were mixed with tenant-admin pages under `/admin/*`; and the repository is public while
holding the threat model and security reviews.

## Decision

1. **Company systems are separate from the product.** CRM, contracts and e-signature, accounting, support desk,
   website, status, trust centre and GRC run outside the product runtime, in their own AWS account, with staff
   signing in through the corporate identity provider, not the product's Keycloak. They share no database with it.
   The register is [`docs/internal/internal.md`](../internal/internal.md).
2. **The link is a small data contract, not shared code.** `tenant_subscription.contract_ref` is an opaque id
   assigned by the contracts system. It is required for terms `annual` and `multi_year`, optional for `trial`
   and `sandbox`, set by an operator at provisioning, and changed only by an operator with a reason.
   The product stores plan, term, seat limits, add-ons and renewal date; prices, invoices and payments stay in
   company systems. Usage flows out as monthly counts (`tenant_usage`) through an operator-only export for the
   true-up invoice. A contract webhook may pre-fill the provisioning wizard but never creates a tenant.
3. **Licences.** ADR 0011 still denies AGPL for what the product ships. Unmodified AGPL or GPL tools may run as
   separate internal services. None is embedded, linked or bundled into the product image or repository.
4. **The operator console is separate.** Platform-operator pages live only under `/platform/*`, served on their own
   origin and Keycloak realm, with WebAuthn and a network allowlist (OPS-12). Tenant-admin pages stay under
   `/settings/*`. Until OPS-12 is built, operator routes stay behind the operator principal check.
5. **No standing operator access to tenant data.** The Super Admin column of `05-access-matrix.md` is `admin` only on
   platform modules and `none` elsewhere. Operators reach tenant data only through the audited, tenant-approved,
   time-boxed support-access grant (TENANCY-06).
6. **Nothing sensitive in the public repository.** `docs/internal/` records structure and decisions only: no
   credentials, account ids, customer names, prices or contract terms.

## Consequences

- ENT-01 adds `contract_ref` rules; new ENT-02 adds the usage export and optional contract intake; TENANCY-05's
  wizard takes `contract_ref`; new OPS-12 builds the operator console origin.
- Owner actions: choose the company tools (OPEN-QUESTIONS 17 to 20), make the repository private (21), and settle
  IP ownership (22).
- Reversible: the contract link is one column and one export; swapping any company tool changes no product code.
