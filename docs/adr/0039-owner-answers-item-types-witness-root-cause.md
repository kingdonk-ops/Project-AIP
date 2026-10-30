# ADR 0039: Owner answers on item-type inheritance, schema changes, starter packs, witness notification, root-cause method, report signing, qualification enforcement, asset states, locked storage and report revisions

- **Status:** accepted
- **Date:** 2026-10-30
- **Affects:** item_types (inheritance after R1, ITEMTYPES-06), inspections (INSPECTIONS-03, PORTAL-06), issues (ISSUES-06), report_engine (sealing and signing after R1), eligibility
  (ELIGIBILITY-01, ELIGIBILITY-02),
  ITEMTYPES-05, uploads and documents (locked storage)

## Context

[OPEN-QUESTIONS.md](../../tracking/OPEN-QUESTIONS.md) "R1 gate" lists the questions PLAN-R1 copied from the R1 module
READMEs ([ADR 0036](0036-r1-module-decisions.md)). On 2026-10-30 the owner answered #38 to #41, #43, #44 and #46 to #49.
#50 to #54 stay open.

## Decision

### #38 Item-type inheritance: bounded overrides, tighten only

A child item type (`item_types.parent_type_id`) inherits every attribute of its parent. The rule is that **an asset of
a child type must still be valid as an asset of the parent type**, so reports, rules and templates written against the
parent keep working for every child.

| A child type may | Rule |
|---|---|
| Add attributes | Always |
| Make an optional attribute required | Tighten only; never required → optional |
| Narrow the tolerance (min/max/target) | Must stay inside the parent's range |
| Change the unit | Same dimension only (mm ↔ in), converted |
| Restrict dropdown options | A subset of the parent's options |
| Change label, help text, default value or order | Display only, always allowed |

A child type may **not** remove an inherited attribute, loosen any rule, or change an attribute's key or field type.
If a child needs to drop an attribute, the attribute belongs lower in the hierarchy: move it from the parent into the
children that need it, or make the child a sibling.

- Overrides live in the child version's `attribute_schema` (for example an `overrides` block keyed by attribute key);
  `inheritance.py` resolves the effective schema up the parent chain.
- Publishing a child version is refused unless every override tightens the parent's published rule.
- No cycles; at most 3 levels below a root type.
- The type editor shows own, inherited and overridden attributes, with the parent's value next to an override.

This extends the advisors' "add-only with overrides of required, unit and tolerance" with the tighten-only rule and safe
overrides for options and display fields.

### #39 Schema changes: pinned versions plus a migration preview

- Assets stay pinned to the item-type version they were created or last migrated on (`item_type_version_id`, already
  in R1 via ITEMTYPES-02 and ASSETS-02). Publishing a new version changes no existing asset.
- Completed inspections are never migrated; they keep the form revision and type version they were completed against.
- Moving assets to a newer version is an explicit admin step behind a migration preview with impact counts (assets
  affected, values that fail the new rules). A parent change that a child's override no longer tightens shows as a
  conflict in that preview, not as a silent failure.

### #40 Neutral asset states

The fixed neutral states that custom asset status sets map to are, in order: **draft, scoped, planned, in progress,
on hold, completed, cancelled**. They are an enum in code; tenants rename and add their own statuses, and each maps to
exactly one of these. Gates, dashboards and reports use the neutral state. This unblocks ITEMTYPES-05.

### #41 Starter packs: three ways to start

A tenant can start in any of three ways, and mix them:

1. **Blank slate:** no packs; the tenant builds its own types.
2. **Provisioned for them:** the operator installs and tailors packs on the tenant's behalf (owner-curated per-tenant
   content, through the operator console of [ADR 0017](0017-company-systems-and-contract-link.md)).
3. **Self-selected:** the tenant admin picks industry-standard packs (NDT/CUI, welding, insulation, coating) shipped
   with the product as platform rows ([ADR 0028](0028-platform-tenant-rows.md)), previews and installs them.

Installed packs become ordinary tenant-owned types the tenant can edit; `starter_pack_installs` records what was
applied. This unblocks ITEMTYPES-06.

### #43 Witness notification: the system notifies in-system witnesses

- When a witness point is booked, the system notifies the **client inspector** (a portal user on the project) with the
  project's notice period (`witness_notice_hours`). The notification is recorded on the witness point, so it becomes a
  documented control rather than a QA phone call or email that leaves no record.
- A **third-party inspector** who is not a user in the system is not notified by it; QA notifies them outside the
  system as today.
- Other systems (ITPpro and others) notify witnesses too; this is parity plus an audit record, not a differentiator.

### #44 Qualifications: enforcement per type, fields per type

- **Discipline qualifications** (for example RT, MT, PT, UT, welding inspection, QA, QC, painting) gate the
  inspections and tasks of that discipline: a missing or expired one is a hard stop.
- **General qualifications** (for example working at heights, confined space, rope access, first aid) are listed on
  the person's profile with licence number, expiry date and an uploaded copy.
- Each certificate type has an **enforcement** setting chosen when the type is created: `ignore`, `notify` (warn and
  record, do not block) or `hard_stop`. This replaces per-type grace periods. Overrides of a hard stop stay with
  ELIGIBILITY-03.
- Each certificate type can define **its own extra fields**, the way item types do. On a profile, "Add qualification"
  opens a selector of types; choosing one shows the standard fields (number, issued, expiry, copy) plus that type's
  fields. The fields use the item_types field-type registry.
- No automatic checks against issuing registers for now. **QA owns verification**: they make sure qualifications and
  data are in the system and valid. QA can name one or more verifiers (for example the storeman or an admin). A
  verifier is notified when something that needs verifying enters the system, and records who verified it and when.
  If it is not verified within **3 days**, QA is notified that the verification is overdue.

### #46 Root-cause method: both, tenant chooses the default

Both 5-why and fishbone are available. The tenant admin sets the default in settings, or is asked on first use (the
first time a root cause is recorded); the default can be changed later. This unblocks ISSUES-06.

### #47 and #48 Report sealing and signing: in-app approval signs the PDF

The system itself signs and verifies PDF reports and files; there is no DocuSign or Adobe Sign step.

- People do not sign a PDF by hand. They **approve** the report in AIP through the approvals engine (with the step-up
  authentication it already enforces), and that approval adds their signature block and a digital lock to the PDF.
- The lock is a PAdES signature made with a key held in AWS KMS (the key never leaves KMS), with a trusted timestamp so
  it stays valid after the signing certificate expires. Each approver's signature is applied in turn; a change after
  any signature breaks it visibly in a PDF reader.
- The sha256 hash and manifest R1 already records stay underneath, so non-PDF files are covered and existing reports
  stay verifiable.
- AIP offers verification: upload or open a PDF or file and the system reports whether it matches a sealed original,
  who approved it and when.
- Hash-only reports stay for now ([ADR 0036](0036-r1-module-decisions.md)). **Signed PDFs are required once
  production is live on AWS**, so signing must land before the AWS go-live. The demo on Coolify
  has no KMS and needs a software key or a placeholder signer there. A certificate from a trusted provider is needed
  for readers to show a trusted signature without a warning.

### #49 Locked storage, and how reports are revised

- **Production (AWS):** signed and completed reports go to S3 with Object Lock in **governance** mode for the
  retention period ([ADR 0021](0021-retention-schedule.md)). Nobody can change or delete them in normal use, but a
  named, audited permission can delete them, so a tenant's files can still be purged when it leaves the service
  ([ADR 0022](0022-offboarding-lifecycle-and-archive-plan.md)) or under a legal instruction.
- **Demo (Coolify):** hash and manifest only.
- **Completed reports are locked** and added to the documents list of their inspection.
- **Revising a report:** information can still be changed after completion, but only by superseding. The corrected
  inspection gets a new **revision number**; each change needs a written explanation, which stays part of the
  inspection. When the revision is completed, its report is either sent out again (emailed) or added as a new version
  of the same document. The old report stays locked, is stamped **Superseded**, and only the new revision shows as
  current.
- The inspection template has a setting for whether the change explanations are printed at the back of the report.

## Consequences

- ITEMTYPES-05, ITEMTYPES-06 and ISSUES-06 move from `blocked` to `todo`; their full specs follow these answers.
- Inheritance and the migration preview stay after R1 ([BACKLOG.md](../../tracking/BACKLOG.md)); when they are pulled
  in, their tasks follow #38 and #39 above.
- INSPECTIONS-03 and PORTAL-06 record the witness notification on the point; PROJECTS-04 already carries
  `witness_notice_hours`.
- The item_types, inspections, issues and report_engine READMEs mark these questions answered.
- ELIGIBILITY-01 adds `certificate_types.enforcement`; ELIGIBILITY-02 blocks only on `hard_stop` types. Per-type
  fields and the "Add qualification" selector, the verifier workflow (notify verifiers, 3-day overdue alert to QA)
  and discipline gating are eligibility work after R1.
- Report revisions (revision number, required change explanation, Superseded stamp, template setting for printing
  explanations) shape INSPECTIONS and REPORTS work; locked storage is part of the AWS production setup.
- PAdES signing on approval and the verification page go to the backlog as report_engine work, required before the
  AWS production go-live.
