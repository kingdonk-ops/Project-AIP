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
- 2026-10-09 — **LGPL exceptions:** owner confirmed the `psycopg` and `psycopg-pool` LGPL-3.0 exceptions (required by Procrastinate, imported unmodified; expire 2027-04-06). → ADR 0016.

Nothing blocks M0 now.

## Needed before P0-core exit / R1

1. One AWS KMS key per tenant instead of a shared key (ADR 0006)?
2. MVP cut and a target date for "Kaefer live" (ADR 0007). Does Kaefer's current system keep running until then,
   and will you provide an export of Kaefer's existing records for the R1 import?
3. Commercial model (ADR 0008): which user classes are billable seats (field PIN, portal, subcontractor)? Is
   Kaefer one tenant with regional organisations, or several tenants?
4. AI provider: the decision says "direct model vendor API", but the ai_gov module assumes Bedrock Sydney with zero retention. Which?
5. Does Rio Tinto (or Kaefer IT) contractually require a siloed deployment, a pen test, per-tenant keys or
    an IdP connection for Rio staff?
6. Will you buy Vanta/Drata rather than build the control catalogue, breach register and access review in-app?
7. What maximum offline period is acceptable for field devices?
8. Client Reviewer has many `approve` cells in the access matrix, but the portal decision is "read-only plus
    witness and counter-sign". Trim the matrix?
9. Retention periods per record type, and who is the named security owner?
10. Team size: solo or hiring? (Sets agent parallelism and realistic dates.)
11. **Shared field tablets and PINs:** if workers share a device and a PIN, one could sign off in another's name. Accept this risk, require one device per worker, or require a passkey (fingerprint/face) for critical actions? (threat model, ADR 0010)

### Tablet hand-over signing ([review 09](../docs/reviews/09-tablet-handover-signing.md))

Recommendation: the client picks their name and enters their own PIN on the inspector's tablet. PIN only counts as a
light check (`aal1`), so it is enough for witness points. To release a **hold point**, the client also taps their own
security key or scans a QR code with their phone, unless the client has agreed in writing that PIN only is fine. If
the client isn't set up, the inspector records a witness note and the client confirms later in the portal.

12. Do Rio Tinto client reps carry a phone on the work front, and would they accept a FIDO key on their lanyard if we
    (or Kaefer) supply it?
13. For hold points, is PIN-only acceptable if Rio Tinto agrees in writing for a project, or must it always be the
    client's own key/phone (or later confirmation)?
14. Offline: may a hold be provisionally released on a PIN-only client signature before sync, or must the crew wait?
15. Is a photo of the client at signing acceptable (privacy notice, Rio site camera rules)?
16. Which tablets does Kaefer use (Android with NFC, or iPad), and are they under MDM so we can use kiosk/screen pinning?

### Company systems and compliance ([ADR 0017](../docs/adr/0017-company-systems-and-contract-link.md), [`docs/internal/internal.md`](../docs/internal/internal.md))

17. CRM, contracts and invoicing: lighter set (CRM + DocuSeal + Xero, recommended for launch) or one console (ERPNext + Frappe CRM)? Is Xero acceptable for AU GST and BAS?
18. Support desk, status page, trust centre and website: accept the candidates in the register (Zammad, Upptime, Astro and Starlight)?
19. Compliance tool (extends Q6): open-source Comp AI, or buy Vanta/Drata? Drop HIPAA from the framework list (no health data) and aim for SOC 2 Type I, then ISO 27001, plus the Privacy Act and NDB scheme?
20. Corporate IT and the remaining undecided services: Microsoft 365 Business Premium (Entra, Intune MDM) or Google Workspace? Transactional email (SES) and error tracking (self-hosted Sentry or CloudWatch RUM)?
21. **Make the `Project-AIP` repository private.** It is public today and holds the threat model, security reviews and Keycloak realm config. Private repositories use GitHub Actions minutes, so check Settings, Billing and plans first.
22. Intellectual property: get written confirmation of who owns the code before incorporating or selling, and check the employment agreement's IP and outside-work clauses (legal advice, not repository work).

## Also waiting on the owner

- Coolify API key: owner decided (2026-10-08) to keep the key that was pasted in chat for now. Rotate it before any
  real customer data goes onto Coolify; store the replacement only as GitHub Actions secrets (`COOLIFY_TOKEN`,
  `COOLIFY_WEBHOOK`).
- In GitHub branch protection for `main`, mark the `boundaries` check (ARCH-03) as required.
- Optional: add repository secrets `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD` (from `cosign generate-key-pair`) so CI image signatures use a real key instead of a throwaway one.
