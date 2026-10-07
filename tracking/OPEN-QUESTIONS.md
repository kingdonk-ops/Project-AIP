# Open questions for the owner

Distilled from the specialist reviews in [`docs/reviews/`](../docs/reviews/). Answer inline. Each answer
becomes an ADR update. **Bold** questions block M0.

## Blocking M0

0. **TypeScript rebuild or continue the Python AIP backend?** The stack review
   ([08](../docs/reviews/08-stack-decision.md)) recommends a 5-day audit of the AIP code first, with
   "continue Python backend + TypeScript frontends" as the default if it passes. Also decide on its other
   changes: Postgres job queue instead of BullMQ, Vite for all three frontends instead of Next.js, and
   one KMS key per tenant (ADR 0006 as written can't crypto-shred S3 data).
1. **Confirm the stack reconciliation:** Kysely + forward-only SQL migrations (ADR 0002) and BullMQ (ADR 0003)
   replace the "Alembic" and "arq/Celery" decision text?
2. **Identity split (ADR 0005):** Keycloak only brokers SSO, and the app issues every session and builds its
   own SCIM server? Or drop Keycloak and do SAML in-app?
3. **M0 deploy target:** is an AWS account (ap-southeast-2) ready for staging now, or Coolify demo first?
4. **AIP source access:** can agents read the AIP repo, schema and lifecycle specs? If not, the "golden test"
   tasks (e.g. APPROVALS-05) need written specs from you.

## Needed before P0-core exit / R1

5. Per-tenant envelope keys instead of a shared key (ADR 0006)?
6. MVP cut and a target date for "Kaefer live" (ADR 0007). Does AIP keep serving Kaefer until then, and is
   its Coolify database backed up today?
7. Field app as a separate Vite PWA rather than a Next.js route (ADR 0004)?
8. Commercial model (ADR 0008): which user classes are billable seats (field PIN, portal, subcontractor)? Is
   Kaefer one tenant with regional organisations, or several tenants?
9. AI provider: the decision says "direct model vendor API", but the ai_gov module assumes Bedrock Sydney with zero retention. Which?
10. Does Rio Tinto (or Kaefer IT) contractually require a siloed deployment, a pen test, per-tenant keys or
    an IdP connection for Rio staff?
11. Will you buy Vanta/Drata rather than build the control catalogue, breach register and access review in-app?
12. Can field-PIN users sign hold points? What maximum offline period is acceptable?
13. Client Reviewer has many `approve` cells in the access matrix, but the portal decision is "read-only plus
    witness and counter-sign". Trim the matrix?
14. Retention periods per record type, and who is the named security owner?
15. Team size: solo or hiring? (Sets agent parallelism and realistic dates.)
