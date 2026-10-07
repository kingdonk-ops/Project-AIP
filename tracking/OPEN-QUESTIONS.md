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

## Blocking M0 (owner asked for advice; recommendation given 2026-10-07, awaiting OK)

1. **Frontends:** recommended **Vite for all three apps** (web, offline field app, portal). The offline field app
   must start with no signal and re-sync later; Vite serves it as static files with a service worker, and all
   three apps share one sync/offline package. Next.js's server tier doesn't help offline sync. (ADR 0004)
2. **Sign-in:** recommended **Keycloak handles all staff sign-in** (company SSO, email + password, MFA, passkeys),
   while the backend issues its own session cookie (instant logout/revocation) and builds only what Keycloak
   doesn't do well: field-worker PIN/device login, portal magic links, and the SCIM endpoint. This replaces the
   in-app passwords/MFA in the current ADR 0005 and shrinks IDENTITY-04.

## Needed before P0-core exit / R1

3. One AWS KMS key per tenant instead of a shared key (ADR 0006)?
4. MVP cut and a target date for "Kaefer live" (ADR 0007). Does Kaefer's current system keep running until then,
   and will you provide an export of Kaefer's existing records for the R1 import?
5. Commercial model (ADR 0008): which user classes are billable seats (field PIN, portal, subcontractor)? Is
   Kaefer one tenant with regional organisations, or several tenants?
6. AI provider: the decision says "direct model vendor API", but the ai_gov module assumes Bedrock Sydney with zero retention. Which?
7. Does Rio Tinto (or Kaefer IT) contractually require a siloed deployment, a pen test, per-tenant keys or
    an IdP connection for Rio staff?
8. Will you buy Vanta/Drata rather than build the control catalogue, breach register and access review in-app?
9. Can field-PIN users sign hold points? What maximum offline period is acceptable?
10. Client Reviewer has many `approve` cells in the access matrix, but the portal decision is "read-only plus
    witness and counter-sign". Trim the matrix?
11. Retention periods per record type, and who is the named security owner?
12. Team size: solo or hiring? (Sets agent parallelism and realistic dates.)
