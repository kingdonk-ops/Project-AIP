# Enterprise readiness specialist review

Scope: what Kaefer procurement, Rio Tinto third-party/vendor security and IT, and a future AU government buyer will demand before signing and during rollout. Sources: INDEX, 00-brief, 01-decisions, 02-advisor-summaries, 05-access-matrix, 06-build-order, module READMEs (security, tenancy, identity, audit, signing, documents, handover, data_io, integrations, ops, ai_gov, design) and the P0 task specs in `tracking/tasks/`.

## Verdict

**The security engineering is strong. Commercial and contractual readiness is mostly missing, and the blueprint contradicts itself in places a vendor-security reviewer will notice.**

- **Strong (above typical seed-stage SaaS):** FORCE RLS with fail-closed tenant context, generated isolation and IDOR tests, a hash-chained audit log anchored to S3 Object Lock, legal hold that overrides purge, a deny-by-default policy layer, quarantine-only uploads, signed images and SBOM, tenant export with manifest, offboarding with a deletion certificate, AI off by default behind a data-flow register, and quarterly access reviews and restore tests recorded as evidence.
- **Missing or not specified:**
  - Contract artefacts: DPA, sub-processor register with change notice, SLA numbers, support model, incident-notification terms, insurance, exit terms.
  - Corporate (non-product) ISMS controls: HR screening, endpoint/MDM, training, Essential Eight.
  - AWS account-level security baseline.
  - A DR posture beyond a single region.
  - Federation of client organisations, such as Rio Tinto staff signing in with Rio's own IdP.
- **Contradictions a reviewer will find:**
  - Identity: Keycloak (decision, P0 exit criteria) vs WorkOS (identity README, access matrix, ops cost).
  - Keys: "shared key with tenant prefixes" vs per-tenant KMS crypto-shredding (tenancy, ai_gov compliance pack).
  - AI: "direct model vendor API" vs Bedrock Sydney with zero retention.
  - Backups: "in-region copies only" (ops) vs "cross-region copy" (data_io).
  - Task stack: SECURITY and OPS tasks use Python paths and arq, TENANCY and DATABASE tasks use NestJS paths.
  - ADRs: `docs/adr/` is referenced as the conflict resolver but does not exist.
- **Sequencing:** SOC 2 Type I during the pilot is achievable, but only if the evidence clock starts in P0. The build order puts "SOC 2 Type I evidence collection is running" in the **P2** exit criteria, which is too late.
- **Pilot readiness:** not ready. About 10 non-code items (legal, process, vendor) are on the pilot critical path and none have a task.

## Buyer-readiness checklist

| Requirement | Coverage | Needed by | Notes |
|---|---|---|---|
| Vendor security questionnaire answers (CAIQ v4 / SIG Lite / Rio TPRM form) | partial | pilot | "Trust pack" accepted in security README, but no task, owner or pre-filled CAIQ. |
| Security whitepaper + architecture/data-flow diagram | partial | pilot | Accepted as a feature but not tasked. |
| SOC 2 Type I report | partial | pilot (or letter of engagement + bridge) | Sequenced, but the evidence start is gated at P2. Rio will usually accept "Type I in progress + pen test + questionnaire" for a pilot. |
| SOC 2 Type II | partial | GA (+12 mo latest) | Needs a 3–6 month observation window started right after Type I. |
| ISO 27001 certificate | partial | GA (UK/gov buyers) | No ISMS scope, Statement of Applicability, internal audit or management-review tasks. |
| IRAP (PROTECTED) | partial | later | Needs AGSVA-cleared privileged staff, ISM mapping, an IRAP-assessed IdP. Keycloak self-hosted helps; WorkOS does not. |
| Essential Eight maturity statement | missing | GA | AU enterprises and government ask for it; it covers corporate endpoints, not the product. |
| SSO SAML/OIDC per tenant | covered | pilot | Provider contradiction (Keycloak vs WorkOS) must be closed. |
| SCIM provisioning/deprovisioning | partial | pilot | Keycloak has no native SCIM server, so it needs an extension or custom endpoint. The "within minutes" target is undefined. |
| SSO for client orgs inside a tenant (Rio users in Kaefer tenant) | missing | pilot | The portal relies on magic links. Rio security may refuse bearer links for its staff and require Entra ID federation per organisation. |
| MFA, session policy, IP allow-list | covered | pilot | SECURITY-07. Idle/absolute timeouts are not set yet. |
| Audit log export / SIEM streaming | partial | pilot (export), GA (stream) | Signed export and SIEM forwarding are specified. Format (JSON/CEF), delivery (S3 or API) and audit-log retention period are not. |
| Data residency AU (incl. backups, logs, support access, email, error tracking) | partial | pilot | Primary data is pinned to Sydney. Sub-processor locations (WorkOS, email, Sentry, AI vendor) and offshore support access are undecided. |
| DPA + Privacy Act/APP terms + privacy policy | missing | pilot | The data map and NDB runbook exist; the contract document does not. |
| Sub-processor register + 30-day change notice | partial | pilot | Listed in the trust pack only. |
| Breach / incident notification (contractual 24–72 h) | partial | pilot | NDB clock (SECURITY-04) is regulatory only. There is no customer-notification SLA and no general incident response plan or tabletop exercise. |
| SLA / uptime commitment + service credits | missing | GA (pilot: target only) | A status page is accepted but there are no numbers. |
| RPO/RTO published and evidenced | partial | pilot | Restore tests exist (OPS-08). No target values and no DR exercise. |
| Multi-region / out-of-region DR | missing | GA | Single region only. Melbourne (ap-southeast-4) keeps AU residency. |
| Backup isolation (separate account, Vault Lock) | missing | GA | Covers ransomware and insider risk; IRAP assessors look for it. |
| AWS org baseline (multi-account, CloudTrail org trail, GuardDuty, Security Hub, Config) | missing | pilot | Not in OPS-07. This is core SOC 2 CC7 evidence. |
| Independent pen test + retest letter | covered | pilot | Release block on open highs. Specify CREST-accredited, tenant-isolation and portal scope, annual cadence. |
| Vulnerability disclosure (security.txt / VDP) | missing | GA | Cheap and expected. |
| Insurance (cyber, PI, public liability) | missing | pilot | Kaefer and Rio contractor terms typically require certificates of currency. Confirm the limits. |
| Support model (hours, severities, response times, escalation, AU business hours) | missing | pilot | Needed for the pilot SOW and onboarding runbook. |
| Customer onboarding / admin training / UAT sandbox | partial | pilot | UAT sandbox accepted (ops). No admin guide or runbook. |
| Data export (self-service) | covered | pilot | data_io register export plus tenant export with manifest. |
| Exit: post-termination export window, deletion certificate | partial | GA | The deletion certificate exists. The contract window (e.g. 90 days) is missing. Crypto-shred is weakened by the shared-key decision. |
| Customer-managed keys (BYOK) | missing | later | Mining and government buyers ask. Depends on per-tenant KMS. |
| Records retention schedule per record type | partial | pilot | Undefined, yet it blocks Object Lock compliance mode (signing open question). |
| Legal hold | covered | pilot | DATABASE-06, audit hold register. |
| Tamper-evident signatures / verification | covered | GA | Signing is P2. External e-sign is deferred; check Kaefer's contract signature standard. |
| Integration: CSV/Excel import/export, EAM register export | covered | pilot | data_io P1; handover EAM export P2. |
| Integration: public API + webhooks | covered | GA | P3. Pull a read-only API forward if Rio wants a Power BI feed. |
| Integration: SAP PM / Maximo | partial | later | Per-customer delivery, not core. Decide and price it. |
| Integration: Aconex / SharePoint / Teams / Power BI | missing | GA | Teams is in scope. Aconex and SharePoint are open questions, and they are the most likely asks on Rio projects. Procore is not addressed. |
| Accessibility WCAG 2.2 AA + conformance report (VPAT/ACR) | partial | GA | The design module targets 2.2 AA. No ACR or audit task. |
| AI data handling statement | partial | GA | Off by default, but the provider decision contradicts AU residency. |
| Vendor viability / source-code escrow | missing | GA (on request) | Rio may ask about a small-vendor key-person risk. |

## Top risks

1. **The evidence clock starts too late.** SOC 2 evidence collection is in the P2 exit criteria. Any Type I date during the pilot needs the controls operating from P0: policies, risk assessment, change management, access reviews, monitoring.
2. **A pilot on unhardened infrastructure.** The current Kaefer AIP runs on Coolify with the Postgres **not backed up**, per the ops README. If Rio data is already there, this is a live exposure that a vendor review would fail. Fix it now (OPS-08) and do not let pilot data touch Coolify.
3. **Identity contradiction and the SCIM gap.**
   - The P0 exit criteria commit to Keycloak SCIM deprovisioning, but Keycloak has no first-party SCIM server.
   - Running Keycloak also puts patching, HA and backup in audit scope.
   - Client-org federation (Rio Entra ID) is not designed.
4. **The shared encryption key weakens offboarding and BYOK claims.**
   - With one shared key, the "crypto-shred + deletion certificate" promise reduces to "deleted rows and prefixes".
   - Per-tenant KMS keys cost a few dollars a month each.
5. **Contract artefacts have no owner.** DPA, SLA, support terms, insurance and sub-processor list are pilot blockers in procurement, independent of the code, and procurement often runs 8–12 weeks.
6. **Single-region DR.** Multi-AZ RDS does not cover a regional event or account compromise. Rio and government buyers ask for a tested RTO.
7. **Contradictory text in the blueprint.** Reviewers who receive architecture docs will flag Python vs TypeScript task paths, WorkOS vs Keycloak, and Bedrock vs direct API. Without ADRs, the "single source of truth" claim fails.
8. **Integration expectations.** Rio projects commonly run Aconex/SharePoint document control. Without an export or transmittal path, AIP becomes a second CDE, which reviewers resist.

## Recommended decisions / ADRs

- **ADR: Identity provider final.**
  - Keep Keycloak (residency, IRAP), choose the SCIM extension (or build `/scim/v2`), run it HA on ECS with its own DB, and remove WorkOS references.
  - Add an organisation-level IdP federation so the Rio org signs in via Rio's IdP.
- **ADR: Per-tenant KMS keys (supersede "shared key with tenant prefixes").** This enables crypto-shred, makes BYOK possible later, and allows a clean deletion certificate.
- **ADR: AI provider = Bedrock ap-southeast-2 (supersede "direct model vendor API").** Otherwise record which vendor and region and accept the residency exception in writing.
- **ADR: Recovery targets.**
  - Pilot: RPO ≤ 15 min (PITR), RTO ≤ 8 h.
  - GA: RPO ≤ 15 min, RTO ≤ 4 h, with AWS Backup copies to ap-southeast-4 (Melbourne, AU residency kept) in a separate backup account with Vault Lock.
  - Fix the ops/data_io wording conflict.
- **ADR: AWS landing zone.** Organizations/Control Tower with separate accounts for prod, staging, security/log-archive and backup, plus an org CloudTrail, GuardDuty, Security Hub (CIS/AFSBP), Config and IAM Identity Center with MFA.
- **ADR: Compliance sequencing (revised).**
  - Pick Vanta or Drata now and start one control set mapped to SOC 2, ISO 27001 and ISM.
  - Type I point-in-time date set at pilot go-live; Type II window (6 months) starts the next day.
  - Run the ISO 27001 Stage 1 audit roughly 6 months after Type I and Stage 2 soon after, reusing the same evidence.
  - IRAP only on a funded government opportunity, but hire or clear privileged staff with that in mind.
- **ADR: Retention schedule per record type** (e.g. inspection evidence and signed records: contract + DLP + 7 years minimum; audit logs ≥ 7 years). This is needed before Object Lock compliance mode is enabled.
- **ADR: SAP/Maximo/Aconex are paid per-customer connectors**, built on the P3 API and webhook platform. Core ships CSV/Excel/EAM templates plus an outbound document export.
- **ADR: Reconcile task specs to the TypeScript stack.** Rewrite the SECURITY-* and OPS-02 paths and the arq references, and create `docs/adr/`.

## Tasks to add

| ID | Title | Phase | Why |
|---|---|---|---|
| SECURITY-09 | Select Vanta/Drata, connect AWS/GitHub/IdP, set auditor and Type I date | P0 | Starts the evidence clock; currently gated at P2. |
| SECURITY-10 | ISMS policy set (IS, access, change, IR, BCP/DR, vendor, HR, acceptable use, crypto, data retention) approved and versioned | P0 | SOC 2 / ISO baseline; corporate scope, not product. |
| SECURITY-11 | Corporate controls: MDM, endpoint EDR, staff background checks, security training, Essential Eight self-assessment | P0 | Auditors and Rio test the company, not just the code. |
| SECURITY-12 | Incident response plan, customer notification SLA (≤ 48 h), annual tabletop with recorded evidence | P0 | Contract term plus SOC 2 CC7. Extends SECURITY-04. |
| SECURITY-13 | Trust pack: CAIQ v4 pre-fill, whitepaper, data-flow diagram, sub-processor list, pen-test summary | P1 | Rio TPRM questionnaire turnaround. |
| SECURITY-14 | CREST pen test (app, API, portal, tenant isolation, PWA), retest letter, findings tracker | P1 (before pilot) | Accepted gate; needs scope and vendor. |
| SECURITY-15 | security.txt + vulnerability disclosure policy | P2 | GA expectation. |
| SECURITY-16 | WCAG 2.2 AA audit and Accessibility Conformance Report | P2 | Government buyers. |
| OPS-09 | AWS landing zone: multi-account, org CloudTrail, GuardDuty, Security Hub, Config, IAM Identity Center | P0 | Missing from OPS-07; core monitoring evidence. |
| OPS-10 | Isolated backup account, AWS Backup Vault Lock, copy to ap-southeast-4, annual DR rebuild-from-IaC exercise | P1 | RTO evidence; ransomware resilience. |
| OPS-11 | SLO definitions, status page, uptime reporting per month | P1 | Evidence for the SLA before committing to it. |
| OPS-12 | Support model: severity matrix, hours, on-call rota, ticketing, escalation runbook | P1 | Pilot SOW. |
| IDENTITY-xx | Keycloak SCIM endpoint with deprovision time target test (≤ 15 min) | P0 | P0 exit criterion has no implementation path. |
| IDENTITY-xx | Per-organisation IdP federation (client org SSO into tenant) | P1 | Rio staff in the portal and reviewer roles. |
| TENANCY-08 | Per-tenant KMS key provisioning and crypto-shred test under legal hold | P0 | Follows the key ADR; amends TENANCY-07. |
| AUDIT-xx | Customer audit-log export API + S3/SIEM stream (JSON schema, retention setting) | P1 | Rio IT and SOC asks. |
| LEGAL-01 | MSA, DPA (APP + UK GDPR-ready), SLA schedule, support schedule, exit/export clause (90 days) | P1 (before pilot contract) | Procurement blocker. |
| LEGAL-02 | Insurance: cyber, PI, public liability certificates at the limits the Kaefer/Rio flow-down requires | P1 | Procurement blocker. |
| LEGAL-03 | Retention schedule per record type, signed off with Kaefer | P1 | Unblocks Object Lock compliance mode. |
| INTEGRATIONS-xx | Aconex/SharePoint document export (transmittal package) discovery with Kaefer | P2 | Avoids a "second CDE" objection. |

(Also missing: P0 task specs for identity, access, audit, approvals, uploads, projects and design, although the P0 exit criteria depend on them.)

## Questions for the owner

1. Is any Rio Tinto or Kaefer production data in the Coolify-hosted AIP today? If so, when does it move, and can backups start this week?
2. Who is the contracting party for the pilot (Kaefer only, or Rio as a named beneficiary)? Has Rio's third-party risk team been engaged, and which questionnaire or form will they use?
3. Will Rio Tinto staff sign in (reviewers, hold-point witnesses)? If so, must they use Rio's IdP?
4. What target date and budget do you have for the SOC 2 Type I report, and which platform (Vanta or Drata) and audit firm?
5. Will you reverse "shared key with tenant prefixes" to per-tenant KMS keys?
6. AI: Bedrock Sydney, or a direct vendor API (and from which region)? The second contradicts the AU-residency pitch.
7. What uptime, support hours and response times can you staff at pilot, and at GA?
8. What insurance do you currently hold, and what limits do Kaefer's subcontract flow-downs require?
9. Where will engineers and support staff be located? Offshore admin access affects residency claims and IRAP.
10. Retention: what does the Kaefer/Rio contract require for inspection and QA records after defects liability?
11. Which of Aconex, SharePoint, Power BI, SAP PM or Maximo does the Rio remediation project actually use, and which will Kaefer expect in year one?
12. Is a source-code escrow or step-in clause likely to be requested?
