# ADR 0021: Retention schedule by record type

- **Status:** accepted (owner schedule, 2026-10-10); points 2 to 6 are adjustments the owner has not yet confirmed
- **Date:** 2026-10-10
- **Affects:** audit (AUDIT-01, AUDIT-02, AUDIT-05), ops (OPS-06), tenancy (TENANCY-07), offline; resolves OPEN-QUESTIONS 9

## Decision

1. **Schedule.** These are platform defaults. A tenant may lengthen them; shortening needs an operator-approved contract
   exception. A legal hold (AUDIT-05) always stops deletion.

   | Record type | Keep for | Handling |
   |---|---|---|
   | Inspection reports and hold-point sign-offs | 7 years | Sealed report and manifest move to a read-only archive after 2 years |
   | Asset metadata and drawing markup | life of the asset plus 3 years | Active tables; archived when the asset is decommissioned |
   | Inspection photos and media | 7 years | Standard storage for 12 months, then S3 Glacier Instant Retrieval |
   | Corrective actions and punchlists | 7 years | Kept with the parent inspection |
   | Security, sign-in and role-change audit trail | 3 years | Append-only; removed after 36 months unless on legal hold |
   | Offline device caches | 30 days after sync at most | Purged on the server's acknowledgement |

2. **Two audit streams.** The security stream (`security_audit_events`, AUDIT-02) keeps 3 years. Domain audit entries
   that evidence a sign-off belong to the record they prove and keep 7 years. The owner's schedule listed only the 3-year
   rule; applied to everything it would delete sign-off evidence at year 3.
3. **Removing old audit entries without breaking the hash chain.** The chain is sealed in monthly segments, each
   segment's closing hash is stored in a checkpoint, and verification can start from any checkpoint, so old segments can
   be removed and the remainder still verifies.
4. **AWS services only.** The schedule said "Glacier/Coldline"; Coldline is a Google service. Photos use S3 Glacier
   Instant Retrieval, which opens in milliseconds, so a 5-year-old report still shows its photos. Deep Archive is not
   used for anything people open.
5. **Deletion at the end of life is done by a retention job, not an S3 expiry rule,** so legal holds are honoured and the
   OPS-06 guard against expiry rules on evidence stays in force.
6. **Offboarding.** When a contract ends the customer receives an export of the retained records, then the tenant is
   crypto-shredded (ADR 0006). Retention duties after that rest with the customer's export. S3 Object Lock is not used for
   tenant evidence in the live bucket because it would block crypto-shred; backups in the separate backup account keep
   their vault lock (OPS-10).
7. The 7-year figure is the owner's reading of statutory and contractual warranty needs. Check it against the Kaefer and
   Rio Tinto contracts; pressure equipment and similar assets can require longer.

## Consequences

OPS-06 renders these tiers; AUDIT-01 adds segment checkpoints; AUDIT-02 keeps the two streams; AUDIT-05 adds the retention
job and legal-hold override; TENANCY-07 exports before shredding.
