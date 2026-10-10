# Open questions for the owner

Distilled from the specialist reviews in [`docs/reviews/`](../docs/reviews/). Answer inline. Each answer
becomes an ADR update. **Bold** questions block M0.

## Answered

- 2026-10-07 — **Backend language:** Python backend allowed; the AIP repository is not used. → ADR 0001
  (Python backend + TypeScript frontends), ADR 0002 (SQLAlchemy + Alembic), ADR 0003 (Procrastinate),
  ADR 0004 (layout), ADR 0006 (per-tenant KMS key).
- 2026-10-07 — **Job queue:** Postgres-based. → ADR 0003 (Procrastinate).
- 2026-10-07 — **M0 deploy target:** start on Coolify (synthetic data only). → ADR 0007, task OPS-11; AWS staging moves to wave 7.
- 2026-10-07 — **OCR licence:** no licensing; open source or AWS only. → ADR 0009 (Tesseract + pypdfium2 + pikepdf; Textract optional).
- 2026-10-07 — **Frontends:** Vite for all three apps. → ADR 0004.
- 2026-10-07 — **Sign-in:** Keycloak handles all staff sign-in; backend issues sessions and builds field PIN, portal links, SCIM. → ADR 0005 rev 2.
- 2026-10-07 — **Sign-off assurance:** one quick check at signing (passkey, company device + PIN, code, or company MFA); per-tenant minimum; supervisor countersign fallback. Field-PIN users can sign on a registered device. → ADR 0010, task IDENTITY-07.
- 2026-10-08 — **Licence policy:** any free licence is fine; no paid commercial licences (build it ourselves instead). → ADR 0011 accepted.
- 2026-10-08 — **Provenance log:** initialled by the owner (KK).
- 2026-10-08 — **Security scanning and signing:** ADR 0013 accepted (free scanners, expiring vulnerability exceptions, key-based cosign without public logs).
- 2026-10-10 — **Company systems and navigation:** owner accepted ADR 0017 (company systems outside the product, `contract_ref` link, separate operator console, no standing operator data access) and ADR 0018 (domain groups and job-area menu, no module merges). Tool choices remain open (items 17 to 20).
- 2026-10-10 — **KMS keys:** one AWS KMS key per tenant, on every plan; all tenants share one database cluster with row-level security; siloed deployment is an Enterprise option built only on contract. → ADR 0006 accepted.
- 2026-10-10 — **Kaefer's current system** keeps running until cutover; the owner handles the data import later. A penetration test is needed before the first non-pilot customer; Rio Tinto and Kaefer require no siloed deployment, pen test, per-tenant keys or IdP connection at the start. → ADR 0007 notes (target date still to confirm, item 2).
- 2026-10-10 — **Commercial model:** Kaefer is one tenant with regional organisations containing projects; three plans (Essentials, Professional, Enterprise) with full-user and reviewer seats, project, storage and API limits; prices stay outside the repository. → ADR 0008 accepted (plan structure), ENT-01, ENT-02.
- 2026-10-10 — **AI provider:** both a direct vendor API and Bedrock Sydney, Bedrock Sydney as the default. → ADR 0019.
- 2026-10-10 — **Client Reviewer:** read-only on system data (assets, documents, inspections, consumables), plus sign-off of hold points, witness points and reports; the tenant admin can change the permissions. → access matrix, ACCESS-02.
- 2026-10-10 — **Shared tablets and hold-point signing (items 11 to 16):** one tablet per worker with username and password sign-in; clients use their own phones, no physical security keys; PIN-only hold-point release is a project setting needing a written agreement; provisional release offline is allowed; the photo at signing is an optional setting; Kaefer uses unmanaged Android tablets with NFC. → ADR 0010 addendum, IDENTITY-07.
- 2026-10-10 — **Compliance and company tools:** use Comp AI (open source) for compliance, drop HIPAA; accept the candidates for support, status, trust centre, website and help pages. → `docs/internal/internal.md`.
- 2026-10-10 — **Pricing adjustments and roles:** meter seats, projects, file storage and database size in GB (extra blocks of 20 GB); no 30-day audit tier; customer-owned Power BI as a paid `reporting_feed` add-on; clients sign off in the client portal with username and password; role management per the owner's specification. → ADR 0008 (A to C), ADR 0010 addendum, ADR 0020, ACCESS-02.
- 2026-10-10 — **Offline limits, retention, team (items 7, 9, 10):** offline timers revised on the same day to two clocks (14 days idle; 72 and 120 hours from the oldest unsynced provisional sign-off, 24-hour sync grace) with provisional hold-point sign-off; retention schedule of 7 years for reports, photos, sign-offs and punchlists, life of asset plus 3 years for asset data, 3 years for the security audit trail; solo developer with at most two build streams; milestones 6 to 8, 12 to 14 and 20 to 24 weeks. → ADR 0010 addendum (part 3, revised), ADR 0021, ADR 0007.
- 2026-10-10 — **Data retention after a customer leaves:** the customer's own retention duty is met from their export; 30 days to export, quarantine to day 90, then purge with a deletion certificate; an optional read-only archive plan. → ADR 0022 (replaces ADR 0021 point 6), TENANCY-07 rewritten.
- 2026-10-09 — **LGPL exceptions:** owner confirmed the `psycopg` and `psycopg-pool` LGPL-3.0 exceptions (required by Procrastinate, imported unmodified; expire 2027-04-06). → ADR 0016.

Nothing blocks M0 now.

## Needed before P0-core exit / R1

2. **Confirm the "Kaefer live" date.** Proposed 2027-03-31 if offline stays out of R1, about late May 2027 if offline is in (item 25). Change it if the business needs earlier.

### Company systems and compliance ([ADR 0017](../docs/adr/0017-company-systems-and-contract-link.md), [`docs/internal/internal.md`](../docs/internal/internal.md))

17. CRM, contracts and invoicing: lighter set (CRM + DocuSeal + Xero, recommended for launch) or one console (ERPNext + Frappe CRM)? Is Xero acceptable for AU GST and BAS?
20. Corporate IT and the remaining undecided services: Microsoft 365 Business Premium (Entra, Intune MDM) or Google Workspace? Transactional email (SES) and error tracking (self-hosted Sentry or CloudWatch RUM)?
21. **Make the `Project-AIP` repository private.** It is public today and holds the threat model, security reviews and Keycloak realm config. Private repositories use GitHub Actions minutes, so check Settings, Billing and plans first.
22. Intellectual property: get written confirmation of who owns the code before incorporating or selling, and check the employment agreement's IP and outside-work clauses (legal advice, not repository work).
25. **Is offline operation required for "Kaefer live"?** ADR 0007 keeps it out of R1. Also confirm the four adjustments to the offline timers in ADR 0010 (part 3): a 7-day online check for new signing, controls for unmanaged tablets, evidence-pending photos, and the web-app storage limits.
26. Security contact: create the `security@` mailbox on the company domain (the owner suggested `project-aip.io`; confirm that domain is registered and yours) and confirm the owner is the named security owner while solo. Confirm the 7-year retention against the Kaefer and Rio Tinto contracts, and the ADR 0021 adjustments (two audit streams, chain checkpoints, Glacier Instant Retrieval).
27. Confirm the offboarding lifecycle in ADR 0022 (30-day export, quarantine to day 90, purge, certificate; backups up to 35 days later) and have a lawyer finalise the contract wording and the Privacy Act position. Is the `archive` plan wanted before R1 (proposed: backlog)? The owner chose a sealed bundle plus a separate viewer over keeping rows in the shared database (ADR 0022 point 6).
23. Confirm ADR 0008 adjustment D (no on-premises deployment; a siloed deployment only on contract, after R1). Adjustments A to C were accepted on 2026-10-10.
24. Included database size per plan (the owner's example is 20 GB for Professional): what for Essentials and Enterprise? Also confirm the three adjustments to the role specification in ADR 0020 (project owners cannot edit tenant-wide roles; operators change tenant roles only inside a support-access grant; the offline permission grace has limits).

## Also waiting on the owner

- Coolify API key: owner decided (2026-10-08) to keep the key that was pasted in chat for now. Rotate it before any
  real customer data goes onto Coolify; store the replacement only as GitHub Actions secrets (`COOLIFY_TOKEN`,
  `COOLIFY_WEBHOOK`).
- In GitHub branch protection for `main`, mark the `boundaries` check (ARCH-03) as required.
- Optional: add repository secrets `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD` (from `cosign generate-key-pair`) so CI image signatures use a real key instead of a throwaway one.
