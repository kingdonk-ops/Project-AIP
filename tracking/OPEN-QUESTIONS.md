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
- 2026-10-09 — **LGPL exceptions:** owner confirmed the `psycopg` and `psycopg-pool` LGPL-3.0 exceptions (required by Procrastinate, imported unmodified; expire 2027-04-06). → ADR 0016.

Nothing blocks M0 now.

## Needed before P0-core exit / R1

2. **Confirm the "Kaefer live" date.** Proposed 2027-03-31 (ADR 0007, with milestones). Change it if the business needs earlier.
7. What maximum offline period is acceptable for field devices? (Provisional hold-point release before sync is allowed, see Answered.)
9. Retention periods per record type, and who is the named security owner?
10. Team size: solo or hiring? (Sets agent parallelism and realistic dates.)

### Company systems and compliance ([ADR 0017](../docs/adr/0017-company-systems-and-contract-link.md), [`docs/internal/internal.md`](../docs/internal/internal.md))

17. CRM, contracts and invoicing: lighter set (CRM + DocuSeal + Xero, recommended for launch) or one console (ERPNext + Frappe CRM)? Is Xero acceptable for AU GST and BAS?
20. Corporate IT and the remaining undecided services: Microsoft 365 Business Premium (Entra, Intune MDM) or Google Workspace? Transactional email (SES) and error tracking (self-hosted Sentry or CloudWatch RUM)?
21. **Make the `Project-AIP` repository private.** It is public today and holds the threat model, security reviews and Keycloak realm config. Private repositories use GitHub Actions minutes, so check Settings, Billing and plans first.
22. Intellectual property: get written confirmation of who owns the code before incorporating or selling, and check the employment agreement's IP and outside-work clauses (legal advice, not repository work).
23. Confirm ADR 0008 adjustments A to D (no row caps, one audit log for all plans, Power BI only as the customer-owned reporting feed, no on-premises deployment).

## Also waiting on the owner

- Coolify API key: owner decided (2026-10-08) to keep the key that was pasted in chat for now. Rotate it before any
  real customer data goes onto Coolify; store the replacement only as GitHub Actions secrets (`COOLIFY_TOKEN`,
  `COOLIFY_WEBHOOK`).
- In GitHub branch protection for `main`, mark the `boundaries` check (ARCH-03) as required.
- Optional: add repository secrets `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD` (from `cosign generate-key-pair`) so CI image signatures use a real key instead of a throwaway one.
