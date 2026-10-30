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
- 2026-10-13 — **Web hosting on AWS:** web apps run as nginx containers on Fargate behind one ALB with host-based routing, not S3 + CloudFront, because more sites (portal, operator console, marketing) will share the platform. → ADR 0026 (supersedes ADR 0004's Delivery bullet), OPS-07, OPS-09.
- 2026-10-10 — **Confirmations:** target date for "Kaefer live" 2027-03-31 with offline operation out of R1, and the four offline-timer adjustments (ADR 0007, ADR 0010); the lighter company set CRM + DocuSeal + Xero; Microsoft 365 Business Premium; Amazon SES in Sydney; included database size 5 GB, 20 GB and 100 GB for Essentials, Professional and Enterprise; the three role-specification adjustments (ADR 0020). The owner reports code ownership confirmed (keep the written confirmation on file).
- 2026-10-11 — **Decisions (items 20, 23, 26 to 30):** error tracking is our own sink (OPS-05) plus CloudWatch in Sydney, no hosted Sentry; `security@` mailbox on Microsoft 365 once the domain records are confirmed, owner is the named security owner while solo; 7-year retention, two audit streams, chain checkpoints and Glacier Instant Retrieval confirmed (ADR 0021); offboarding lifecycle confirmed, archive plan post-R1, sealed bundle plus standalone viewer, lawyer to finalise wording (ADR 0022); hosted lightweight CRM (HubSpot Free or Starter, or Attio), Twenty not self-hosted; ADR 0023 points 1, 4, 7, 9, 12 confirmed; "24) confirm" covered items 23, 26 and 27; ADR 0008 adjustment D confirmed (no on-premises deployment; siloed deployment only on contract, after R1).
- 2026-10-14 — **UI modernization guide (items 32, 34, 35):** keep ADR 0018's nav groups (DESIGN-06); build Home / My Work alongside R1 (DESIGN-12); the mobile bottom bar goes with the offline field app, and the web app keeps the drawer. The owner also asked for a per-user choice of side panel or full page for record details, set in profile settings. → docs/reviews/10, DESIGN-13.
- 2026-10-14 — **High-contrast status chips (item 33):** solid chips in the outdoor high-contrast theme; tinted chips only in the standard theme. → DESIGN-09.
- 2026-10-13 — **Time zones:** UTC everywhere internally, local time only at presentation; future scheduled events keep wall-clock time plus the IANA zone; calendar-day expiry (membership `valid_to`) is checked against one reference zone, UTC (the current behaviour), confirmed by the owner. → ADR 0025.
- 2026-10-09 — **LGPL exceptions:** owner confirmed the `psycopg` and `psycopg-pool` LGPL-3.0 exceptions (required by Procrastinate, imported unmodified; expire 2027-04-06). → ADR 0016.

Nothing blocks M0 now.

## Needed before P0-core exit / R1

### Company systems and compliance ([ADR 0017](../docs/adr/0017-company-systems-and-contract-link.md), [`docs/internal/internal.md`](../docs/internal/internal.md))

21. **Make the `Project-AIP` repository private.** It is public today and holds the threat model, security reviews and Keycloak realm config. Private repositories use GitHub Actions minutes, so check Settings, Billing and plans first.
31. Confirm ADR 0024's adjustments to the remote un-block specification: no Super Admin default, refused uploads quarantined (not dropped), a second approver when signed work is on the tablet, a separate revoke-device action for lost tablets, and browser storage in place of the native Android pieces.

### UI modernization guide ([`docs/reviews/10-ui-modernization-guide.md`](../docs/reviews/10-ui-modernization-guide.md))

36. **Company name at sign-up:** today tenants are provisioned by the operator (ADR 0017) and the first admin is invited (TENANCY-05); there is no self-service sign-up. The company name typed at provisioning becomes the header name, and the tenant admin can edit it later. Is that what "when the tenant admin registers" means, or do you want self-service sign-up (a larger change: payment, verification and abuse controls)?
37. **How many colours:** the specs use two company colours (the accent for buttons, links and focus, and an optional header colour). Is that enough, or do you need a logo upload too (planned with tenant branding) or a second accent?

### R1 gate (PLAN-R1, 2026-10-18)

Copied from the R1 modules' README "Open questions". Questions already settled by an ADR or P0 work are listed at
the end and recorded in [ADR 0036](../docs/adr/0036-r1-module-decisions.md); the numbered ones need you. A task
marked `blocked` on the board waits for its question; the others only shape later stubs.

38. ~~**item_types, inheritance:** can a child item type remove or override inherited attributes, or only add?~~ Answered 2026-10-30: add and tighten only. A child may add attributes, make optional ones required, narrow tolerances and options, convert units within a dimension and change display fields; it may never remove or loosen an inherited attribute ([ADR 0039](../docs/adr/0039-owner-answers-item-types-witness-root-cause.md)). Inheritance stays after R1.
39. ~~**item_types, schema changes:** how are existing assets and completed inspections handled when a type's schema changes?~~ Answered 2026-10-30: assets stay pinned to their version, completed inspections never migrate, and moving assets is an explicit step behind a migration preview with impact counts and inheritance conflicts (ADR 0039). The preview stays after R1.
40. **item_types, neutral states:** which fixed set of neutral lifecycle states do custom status sets map to (advisors suggest a fixed enum in code)? Blocks ITEMTYPES-05.
41. ~~**item_types, starter packs:** ship starter packs with the product, keep them as owner-curated per-tenant imports, or both?~~ Answered 2026-10-30: both. A tenant starts blank, has the operator provision packs for it, or self-selects industry-standard packs shipped with the product (ADR 0039). ITEMTYPES-06 is unblocked.
42. ~~**Client sign-off route in R1.**~~ Answered 2026-10-18: the client portal is in R1 (ADR 0036). INSPECTIONS-05 is unblocked and the PORTAL rows are on the board.
43. ~~**inspections, witness notification:** which competitors natively notify customers of witness points?~~ Answered 2026-10-30: ITPpro and others do. The system notifies the client inspector (an in-system user) with the notice period and records it as a documented control; third-party inspectors outside the system are notified by QA as today (ADR 0039).
44. ~~**eligibility, grace periods and verification:** per-type grace periods, and checking licences against issuing registers?~~ Answered 2026-10-30: no grace periods; each certificate type is set to ignore, notify or hard stop, and has its own extra fields picked through "Add qualification" on the profile. Discipline qualifications are hard stops. No register checks (ADR 0039).
45. ~~**scope_work, access methods:** reconcile the access-method list before it is seeded.~~ Already answered in `docs/blueprint/01-decisions.md`: split MEWP and Ladder, tenant-editable list (ADR 0036). SCOPEWORK-06 is not blocked.
46. ~~**issues, root cause:** is the default root-cause method 5-why or fishbone?~~ Answered 2026-10-30: both are available; the tenant admin picks the default in settings or on first use (ADR 0039). ISSUES-06 is unblocked.
47. ~~**report_engine, sealing:** PAdES with AWS KMS-held keys, or hash and manifest only?~~ Answered 2026-10-30: PAdES with a KMS-held key, on top of the sha256 and manifest R1 records (ADR 0039). After R1.
48. ~~**report_engine, external signing:** DocuSign or Adobe Sign, or in-app attestations only?~~ Answered 2026-10-30: in-app only. Approving a report adds the approver's signature and digital lock to the PDF, and AIP verifies PDFs and files (ADR 0039).
49. **report_engine, immutable storage:** S3 Object Lock for sealed outputs (MinIO with object lock on Coolify), or hash and manifest only?
50. **data_io, restore:** is a restore or import-from-export path built at all (with a conflict report), given the hostile-data and cross-tenant risks?
51. **data_io, full exports:** dual approval for every full export, or a single approval?
52. **data_io, scheduled exports:** are scheduled exports to storage in scope?
53. **data_io, project scope:** is project-scoped export in scope alongside tenant scope?
54. **AIP sample export:** please provide a sample export of Kaefer's current records (format, tables or sheets, typical volumes) on synthetic or approved data, as ADR 0007 plans. Blocks DATAIO-04 (and DATAIO-06 behind it).
55. ~~**portal, witness notice.**~~ Answered 2026-10-18: the notice period and waiver rule are project settings (PROJECTS-04, PORTAL-06; ADR 0036).
56. ~~**R1 date with the portal.**~~ Answered 2026-10-18: 2027-03-31 still holds (ADR 0036).

Also from the portal README: the identity approach for portal users is answered (username, password and second step via Keycloak, ADR 0010 addendum part 2, ADR 0036), and staging is answered by the R1 slice in ADR 0036.

Settled (ADR 0036): assets ltree vs closure table (ltree, ADR 0002); assets phasing of risk-based scheduling and P&ID linkage (after R1, ADR 0007); item_types expression language (JSONLogic); forms builder foundation (no designer in R1); forms CEL vs JSONLogic (JSONLogic); inspections state machine (approvals engine, APPROVALS-01/02/05); eligibility reminder mechanism (Procrastinate, OPS-13, OPS-17); issues cost impact (not in R1).

## Also waiting on the owner

- Coolify API key: owner decided (2026-10-08) to keep the key that was pasted in chat for now. Rotate it before any
  real customer data goes onto Coolify; store the replacement only as GitHub Actions secrets (`COOLIFY_TOKEN`,
  `COOLIFY_WEBHOOK`).
- In GitHub branch protection for `main`, mark the `boundaries` check (ARCH-03) as required.
- Optional: add repository secrets `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD` (from `cosign generate-key-pair`) so CI image signatures use a real key instead of a throwaway one.
