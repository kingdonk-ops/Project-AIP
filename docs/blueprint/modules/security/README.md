# Security & compliance programme (`security`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
The security and compliance programme for the platform (Foundations & architecture, suggested phase P0). It owns the threat model, risk register, control set and evidence plan needed to pass customer security reviews (Kaefer, Rio Tinto) and to certify against SOC 2, ISO 27001, IRAP and the Privacy Act. It brings these into one place: identity assurance for four user classes, tenant isolation, one authorisation layer, hardened file processing, tamper-evident legal records, an AI data-flow register, backups and residency, and a secure software pipeline. Dev tooling is stripped from production builds.

What it does
- Maintains the threat model covering field PIN/magic links, external portal, inbound email/webhooks, legal records and AI.
- Maps every control once to SOC 2, ISO 27001, IRAP (ISM) and APP, with continuous evidence collection.
- Handles Privacy Act obligations: data map, NDB breach runbook with notification clock, retention rules per record type, and recording-consent rules for calls and meetings (state recording laws vary).
- Applies field-level masking for incident and health data, driven by data classification tags, and controls EXIF GPS on photos.
- Hardens uploads and file serving, secures the CI pipeline, and records quarterly access reviews and restore tests as audit evidence.
- Keeps a code provenance log showing OpenConstructionERP was used as a functional reference only (AGPL-3.0), with no copied code or schemas.
- Strips admin fixtures, architecture_map, module_builder, pipelines and the compliance DSL from production images, enforced by a test.
- Readiness also covers policies, vendor register, change control, logging and vulnerability management (severity SLAs and tracked exceptions).

Features
- Threat model covering field PIN/magic links, external portal, inbound email/webhooks, legal records and AI.
- Compliance sequence: Vanta or Drata, SOC 2 Type I during the pilot, ISO 27001 + SOC 2 Type II readiness, then IRAP assessor engagement.
- Privacy Act/APP data map, NDB breach runbook, retention rules per record type, recording-consent rules.
- Field-level masking for incident and health data; EXIF GPS control on photos.
- Upload hardening: quarantine bucket, ClamAV, magic-byte checks, size and decompression caps, sandboxed converters.
- Separate file-serving domain, Content-Disposition attachment for active types, SVG/HTML sanitising.
- CI: SBOM, dependency and secrets scanning, Trivy image scan, signed images.
- Quarterly access reviews and restore tests recorded as SOC 2 evidence.
- Code provenance log for OpenConstructionERP (AGPL clean-room).
- Control-to-evidence matrix mapping each control to its automated test, CI job or screenshot source, showing which controls are specified but not yet proven (accepted).
- Trust pack: security whitepaper, sub-processor list, data-flow diagram and standard questionnaire answers (accepted).
- Data classification tags on fields and attachments (public, internal, sensitive, health); these drive masking and tell the AI layer what must never leave region (accepted).
- Bulk-export and anomalous-access alerts to tenant admins (accepted).
- Pre-production security gate: pen-test findings tracker with release block on open highs; pen test before first customer go-live (accepted).
- Customer IP allow-list and session policy settings per tenant (accepted).
- Configurable settings: framework mappings, evidence schedule, review cadence, masking rules, session timeout and MFA policy, breach notification contacts, vulnerability severity SLAs, recording-consent rules.
- Notifications: evidence overdue, access review due, restore test overdue, breach logged with NDB deadline approaching, open high pen-test finding at release, bulk export or anomalous access alert, provenance entry pending review.

Interactions
- Tenancy, organisations & data residency: isolation controls.
- Users, sign-in & SSO: authentication strength and deprovisioning.
- Upload & file processing pipeline: file pipeline hardening.
- E-signatures & tamper-evident records: tamper-evident records. Hash chaining and S3 Object Lock anchoring belong to audit and signing, awaiting owner decision.
- AI governance & data controls: AI data-flow register.
- Operations, hosting & deployment: pipeline and evidence. Coolify should hold no production or client data, and the Coolify-to-AWS move should use infrastructure as code so the audited environment is the one customers use.
- Testing & quality engineering: test runs provide control-testing evidence.

Data
- ControlRecord (control key, title, framework mappings as JSONB, owner, status specified/implemented/proven, evidence source), EvidenceItem, AccessReview, RestoreTestRecord, DataMapEntry, BreachIncident, ProvenanceEntry. Records carry tenant_id (operator tenant, or customer tenant in a siloed stack).
- Append-only tables (evidence, restore tests, provenance) have UPDATE/DELETE revoked for the app role.
- Reuses users, roles, user_roles, documents, audit_log.
- Existing AIP baseline (PRD section 12): OIDC, encryption at rest (Postgres, S3 SSE, SQLCipher), TLS 1.2+, named-user accountability on every write.
- Storage lifecycle: never auto-delete inspection evidence; Infrequent Access after 365 days; Glacier Instant after 7 years.
- Pen-test findings tracker; classification tag per field and attachment; tenant IP allow-list and session policy stored in tenant_settings.
- Control framework mappings, retention rules, masking policies, review cadence and breach templates are configuration, not code.

Pages
- Compliance dashboard (/security/compliance): framework coverage, evidence overdue, proven vs specified, programme timeline.
- Controls (/security/controls): catalogue with mapping editor and evidence history.
- Evidence (/security/evidence).
- Access reviews: quarterly workflow with keep/revoke and sign-off.
- Breach register: incident log, NDB assessment, notification clock, contacts.
- Data map and classification: tags and masking rules.
- Tenant admin settings for IP allow-list and session policy, and alert views.
- Admin-only endpoints for evidence, reviews and breach records.
- Docs: threat-model.md and provenance-log.md. Tests: permission matrix with deny-by-default generated from the catalogue; production build strip test.

Decisions and notes
- Owner accepted all six scout suggestions listed under Features.
- Settle AGPL and clean-room status in week 0, with legal advice, before schema design; record it in the repo. Single-tenant on-prem delivery would count as distribution if code were copied.
- Sequence: SOC 2 Type I with Vanta/Drata during the pilot; ISO 27001 and SOC 2 Type II next; IRAP afterwards. IRAP drives AWS Sydney, PROTECTED-level controls, ISM mapping and personnel security.
- Programme owns the threat model, risk register and evidence plan.
- Pen test before first customer go-live (security advisor, also in accepted gate).

Open questions
- IRAP timing: start the assessor engagement early (security advisor) or gate it on a funded government customer (tech stack advisor)? Owner has not decided.
- Order of ISO 27001 versus SOC 2 Type I: security advisor says both first; the stated plan is SOC 2 Type I in the pilot, then ISO 27001 + Type II. Confirm exact sequence.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
