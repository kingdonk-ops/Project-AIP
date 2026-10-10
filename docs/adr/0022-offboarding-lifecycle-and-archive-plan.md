# ADR 0022: Offboarding lifecycle (30-day export, 90-day purge) and an optional archive plan

- **Status:** accepted (owner position, 2026-10-10); the contract wording and points 3 to 5 need the owner's and a lawyer's confirmation
- **Date:** 2026-10-10
- **Affects:** tenancy (TENANCY-07), ADR 0021 point 6, ADR 0015 statuses, ADR 0008 plans, docs/internal; resolves OPEN-QUESTIONS 26 in part

## Context

ADR 0021 sets what we keep for active tenants. It did not say what happens when a customer leaves. The owner's position:
the long statutory retention duty belongs to the customer, who holds the records; the platform's duty is a clear way to
take the data out, then secure destruction. Holding every former customer's records for 7 years would add storage cost,
legal discovery exposure and privacy risk (Australian Privacy Principle 11.2 requires personal information to be destroyed or
de-identified once no longer needed). This is not legal advice; the Privacy Act does not use the controller and processor
terms, and a lawyer must confirm how the contract allocates the duty.

## Decision

1. **ADR 0021's schedule applies to active tenants.** It stops users deleting evidence early. After termination the
   customer's own retention duty is met from the export, unless they buy the archive plan (point 4).
2. **Lifecycle, counted from the termination date:**

   | Days | Tenant status | What happens |
   |---|---|---|
   | 0 to 30 | `terminating` | Full use of the tool, a banner, and self-serve export at no charge: a ZIP of the sealed PDF reports, original photos with metadata, and CSV or JSON of every register (punchlists, assets, sign-off times). A custom, hand-made dump is billed as professional services. |
   | 30 to 90 | `quarantined` | No user logins (403 `TENANT_QUARANTINED`). Data intact, tenant key still active. An operator can reactivate the tenant, which may carry an administrative fee set in the company systems. |
   | 90 | `offboarded` | The purge job deletes every row of the tenant, deletes the tenant's file prefixes, disables the tenant's KMS key and schedules its deletion (the minimum wait is 7 days), then issues the deletion certificate. |

3. **A legal hold stops the sequence** at any step and the purge waits for its release (ADR 0006, AUDIT-05).
4. **Backups.** Database backups roll off within 35 days of the purge (ADR 0006); the certificate states that date, so
   the true end of the data is the purge day plus up to 35 days. Tenant files are unreadable from the key's deletion.
5. **The platform keeps a deletion record** (tenant id, dates, row and object counts, hashes, the certificate), with no
   business data, for 7 years.
6. **Archive plan (backlog, not R1): a sealed archive bundle and a separate viewer** (owner design, 2026-10-10). A customer
   who must keep records after leaving buys the `archive` plan. At conversion the tenant's data is exported from the
   shared database into a **sealed bundle** held with the reports and files in S3 Glacier Instant Retrieval under the tenant's
   KMS key: a single SQLite file (a stable, openable format) plus CSV and JSON copies, the sealed PDF reports, the photos and
   a manifest with a schema version and hashes. The tenant's rows are then purged from the shared cluster (same purge job
   as point 2), so an archived tenant adds nothing to the database size. The tenant row stays with status `archived`.
   - **Archive area.** A separate origin and sign-in for one or two auditor seats (local accounts with the second step,
     ADR 0005), like the client portal and operator console. A simple read-only viewer opens the bundle with a layout
     similar to the main system (built from `@aip/ui`): registers, records, reports, photos, search and export.
   - Isolation is by file, per tenant, not by row-level security. The viewer must read every bundle schema version it has
     ever produced, so compatibility tests keep old bundles from the fixtures.
   - Project-scoped access is not kept: every archive seat sees the whole bundle.
   - Ending the archive subscription starts the lifecycle in point 2 again.
   - Price: storage plus the viewer and sign-in; it no longer has to cover database growth. Prices are set in the company
     systems. The export and purge are the same work TENANCY-07 already needs, so the new work is the bundle format and
     the viewer.
7. **Contract wording** must match the timeline: the customer has 30 days after termination to export; production data
   is deleted by day 90 after termination; the provider is not a records keeper unless an archive plan is active. A draft
   for the lawyer is in `docs/internal/internal.md`. The wording the owner supplied said deletion "within 90 days after
   the 30-day window", which would be day 120; the timeline above is day 90.

## Consequences

ADR 0021 point 6 is replaced by this ADR. TENANCY-07 is rewritten around these statuses. ADR 0015 gains the statuses
`terminating` (allowed, with a banner) and `quarantined` (403). An `archive` plan code is reserved in ADR 0008.
