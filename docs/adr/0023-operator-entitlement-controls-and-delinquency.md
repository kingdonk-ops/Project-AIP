# ADR 0023: Operator entitlement controls and delinquency states

- **Status:** accepted (owner designs, 2026-10-10); points 1, 4, 7, 9, 12 adjust those designs and were confirmed by the owner on 2026-10-11
- **Date:** 2026-10-10
- **Affects:** tenancy (ENT-01, ENT-03, ENT-04), ADR 0008, ADR 0015, ADR 0010

## Context

The owner supplied two designs: a dynamic entitlements and metering engine with an operator console and per-client
overrides, and a non-payment grace and suspension engine. Much of the first is already ADR 0008 and ENT-01; the second is new.

## Decision

1. **Plans stay in code; overrides live in the database.** Plan limits are versioned, reviewed and tested code. Operators
   change one customer's limits through overrides (value, reason, optional expiry, audit). Changing a plan's numbers is a
   release. The owner's design stored plan limits in editable tables, which would let a commercial change skip review and tests.
2. **Gate types and actions.** Boolean, numeric and configuration gates. A numeric gate says what happens at the limit:
   block, warn, or allow and record the overage for the invoice. Storage and database size warn at 80% and 95%; at 100%
   new uploads are restricted, never reads, exports or finishing work already started.
3. **Responses and speed.** 403 `LIMIT_REACHED` carries the gate, limit and current use. A per-tenant entitlement version makes
   a change apply at once, with tenant-prefixed cache keys (TENANCY-02).
4. **Precedence** is plan, add-on, tenant override, project toggle (ADR 0008). A global kill switch is a release flag
   (ARCH-08), checked first and kept separate. The design's list put it last.
5. **Expiry.** Expired overrides are ignored at evaluation and removed nightly with an audit entry.
6. **Operator console** (ENT-04, on the operator origin of OPS-12): the plan matrix (read-only) and a tenant override
   console. No customer names go in this repository.
7. **Not entitlements:** offline timers are a safety policy for everyone (ADR 0010), not a plan feature; embedded Power BI
   is replaced by the `reporting_feed` add-on (ADR 0008 C). The design tiered both.
8. **Billing state is separate from the tenant lifecycle status** (ADR 0015). States: `good_standing`; `past_due` (a
   banner for admins, full operation); `restricted` (people who manage billing can sign in and read, export and pay;
   every other change and every other user is refused with 403 `TENANT_RESTRICTED`); `suspended` (the existing
   `TENANT_SUSPENDED`, no sign-in). Restriction is by permission, not role names.
9. **A person moves the state, never a payment event.** Invoices are issued from Xero and there is no payment provider
   (ADR 0008), so nothing can fire automatically; and locking field crews on an industrial site over a late invoice or a
   disputed purchase order is a safety and relationship risk. A default grace of 14 days raises a reminder to the operator,
   who moves the state with a reason, after the notice the contract requires. Every move is audited.
10. **Operator levers:** extend the grace (date and reason), choose `restricted` or `suspended`, grant a time-limited feature
    bridge (for example report export), restore to good standing. Platform operators only, on the operator console.
11. **A billing state never purges data.** Offboarding (ADR 0022) is a separate path that starts on termination.
12. **Field devices.** Unsynced records are never deleted (ADR 0010). Proposed: while `restricted`, sync still accepts
    records signed before the restriction time (work already done) and refuses new ones.

## Consequences

ENT-01 gains the gate actions, the version and the sweeper; ENT-03 adds the billing state and its enforcement; ENT-04
adds the operator pages; ADR 0015 gains the billing-state mapping.
