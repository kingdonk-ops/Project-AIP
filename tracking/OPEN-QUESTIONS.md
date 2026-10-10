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
- 2026-10-10 — **Confirmations:** target date for "Kaefer live" 2027-03-31 with offline operation out of R1, and the four offline-timer adjustments (ADR 0007, ADR 0010); the lighter company set CRM + DocuSeal + Xero; Microsoft 365 Business Premium; Amazon SES in Sydney; included database size 5 GB, 20 GB and 100 GB for Essentials, Professional and Enterprise; the three role-specification adjustments (ADR 0020). The owner reports code ownership confirmed (keep the written confirmation on file).
- 2026-10-11 — **Decisions (items 20, 23, 26 to 30):** error tracking is our own sink (OPS-05) plus CloudWatch in Sydney, no hosted Sentry; `security@` mailbox on Microsoft 365 once the domain records are confirmed, owner is the named security owner while solo; 7-year retention, two audit streams, chain checkpoints and Glacier Instant Retrieval confirmed (ADR 0021); offboarding lifecycle confirmed, archive plan post-R1, sealed bundle plus standalone viewer, lawyer to finalise wording (ADR 0022); hosted lightweight CRM (HubSpot Free or Starter, or Attio), Twenty not self-hosted; ADR 0023 points 1, 4, 7, 9, 12 confirmed; "24) confirm" covered items 23, 26 and 27; ADR 0008 adjustment D confirmed (no on-premises deployment; siloed deployment only on contract, after R1).
- 2026-10-09 — **LGPL exceptions:** owner confirmed the `psycopg` and `psycopg-pool` LGPL-3.0 exceptions (required by Procrastinate, imported unmodified; expire 2027-04-06). → ADR 0016.

Nothing blocks M0 now.

## Needed before P0-core exit / R1


### Company systems and compliance ([ADR 0017](../docs/adr/0017-company-systems-and-contract-link.md), [`docs/internal/internal.md`](../docs/internal/internal.md))

21. **Make the `Project-AIP` repository private.** It is public today and holds the threat model, security reviews and Keycloak realm config. Private repositories use GitHub Actions minutes, so check Settings, Billing and plans first.
31. Confirm ADR 0024's adjustments to the remote un-block specification: no Super Admin default, refused uploads quarantined (not dropped), a second approver when signed work is on the tablet, a separate revoke-device action for lost tablets, and browser storage in place of the native Android pieces.

## Also waiting on the owner

- Coolify API key: owner decided (2026-10-08) to keep the key that was pasted in chat for now. Rotate it before any
  real customer data goes onto Coolify; store the replacement only as GitHub Actions secrets (`COOLIFY_TOKEN`,
  `COOLIFY_WEBHOOK`).
- In GitHub branch protection for `main`, mark the `boundaries` check (ARCH-03) as required.
- Optional: add repository secrets `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD` (from `cosign generate-key-pair`) so CI image signatures use a real key instead of a throwaway one.
