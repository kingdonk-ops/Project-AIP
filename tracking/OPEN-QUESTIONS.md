# Open questions for the owner

Distilled from the specialist reviews in [`docs/reviews/`](../docs/reviews/). Answer inline. Each answer
becomes an ADR update. **Bold** questions block M0.

## Answered

- 2026-10-07 — **Backend language:** Python backend allowed; the AIP repository is not used. → ADR 0001
  (Python backend + TypeScript frontends), ADR 0002 (SQLAlchemy + Alembic), ADR 0003 (Procrastinate),
  ADR 0004 (layout), ADR 0006 (per-tenant KMS key).

## Blocking M0

1. **Job queue:** OK to use Procrastinate (Postgres) instead of the "Redis queue (arq or Celery)" in your original
   decisions? (ADR 0003; the stack review recommends it so jobs commit atomically with data.)
2. **Frontends:** OK to build the desktop web app with Vite instead of Next.js? (ADR 0004.) With a Python API,
   Next.js's server tier adds little.
3. **Identity split (ADR 0005):** Keycloak only brokers SSO, and the FastAPI backend issues every session and
   runs its own SCIM server?
4. **M0 deploy target:** is an AWS account (ap-southeast-2) ready for staging now, or Coolify demo first?

## Needed before P0-core exit / R1

5. One AWS KMS key per tenant instead of a shared key (ADR 0006)?
6. MVP cut and a target date for "Kaefer live" (ADR 0007). Does Kaefer's current system keep running until then,
   and will you provide an export of Kaefer's existing records for the R1 import?
7. Commercial model (ADR 0008): which user classes are billable seats (field PIN, portal, subcontractor)? Is
   Kaefer one tenant with regional organisations, or several tenants?
8. AI provider: the decision says "direct model vendor API", but the ai_gov module assumes Bedrock Sydney with zero retention. Which?
9. Does Rio Tinto (or Kaefer IT) contractually require a siloed deployment, a pen test, per-tenant keys or
    an IdP connection for Rio staff?
10. Will you buy Vanta/Drata rather than build the control catalogue, breach register and access review in-app?
11. Can field-PIN users sign hold points? What maximum offline period is acceptable?
12. Client Reviewer has many `approve` cells in the access matrix, but the portal decision is "read-only plus
    witness and counter-sign". Trim the matrix?
13. Retention periods per record type, and who is the named security owner?
14. Team size: solo or hiring? (Sets agent parallelism and realistic dates.)
15. **OCR licence:** OCRmyPDF depends on Ghostscript (AGPL). Accept it in the isolated OCR sandbox image
    (never linked into the API), buy a commercial Ghostscript licence, or use AWS Textract (Sydney) instead? (STACK-04)
