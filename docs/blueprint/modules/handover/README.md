# Handover, data books & submissions (`handover`)

- **Group:** Handover & asset lifecycle
- **Phase:** P2

What it is
Handover, data books & submissions turns asset inspection evidence into handover packages, client data books (MDR) and authority submissions. It sits in the Handover & asset lifecycle group, suggested phase P2. It is not built in AIP yet; the ITP/MDR documentation goal behind AIP and the brief targets this module directly. The differentiator against Procore, Autodesk Construction Cloud, Dalux, Fieldwire, Oracle Aconex and Bentley ProjectWise/AssetWise is live evidence at asset level: inspections, NDT and CUI records and calibration certificates assembled automatically per asset, rather than document collation and self-declared status.

What it does
Builds a controlled, auditable package from the asset tree, ITP records, certificates and documents. It provides a closeout checklist per project and per asset subtree that shows real closure status from live evidence (punch lists, inspections, NCRs, certificates). It compiles a client data book / MDR per asset or system, and produces structured submissions (XML, CSV, Excel, PDF index) from versioned templates with field mappings. Each submission is frozen as an immutable snapshot with a hash manifest. The review cycle with the approving authority or client (for example Rio Tinto) is tracked with comments and responses. Evidence is live-linked, so reopening an NCR flips the related item back to open. On acceptance it emits a handover event that starts the defects liability period, creates service assets and sets the retention milestone.

Features
- Closeout checklist per project bound to evidence, with percent complete by system or area
- Completeness engine: compares the required ITP and document list per asset class against actual signed records and shows gaps by subtree
- Data book / MDR generation per asset or system with index; auto-assembly from the asset tree with hyperlinked index, certificates, weld maps, NDT reports and coating records
- Client-specific MDR structure templates as configuration: folder numbering, document codes, naming rules
- Submission templates as configuration: schema, field mappings, validation rules, terminology labels per tenant
- Export formats: CSV, Excel, PDF index, JSON, generic XML mapper
- Asset register handover export mapped to client EAM import formats (CSV/Excel templates with field mapping)
- Baseline condition snapshot per asset at handover (wall loss, coating condition, CUI findings) carried into service as the first reference for future inspection intervals and trend analysis
- Immutable snapshot + SHA-256 manifest + signer; corrections issued as new revisions
- Resubmission tracking with a diff of changed documents between pack revisions
- Authority/client review cycle: submissions, comments, responses, approvals
- Validation report with click-through to fix the source record
- Retention release tied to verified closure

Interactions
- Asset hierarchy & registers: structure of the pack and asset subtree selection
- Inspections, ITPs & hold points: ITP evidence, outstanding inspections and NCRs
- Document library & control: certificates, reports, approved revisions and document status
- Report engine & published records: compiled PDFs; issued packages published via transmittals and record publishing
- E-signatures & tamper-evident records: sealed packs, signature requests and issue sign-off
- Punch list & defects liability: open items block closeout; acceptance starts the defects liability period
- Commissioning (certificates), requirements (contractual deliverables), approval routes or workflows (review and approval), notifications and deadlines (owner alerts and due dates), payment clock (retention milestone), users and projects (signers, roles, scope), audit events
- Emits submission.validated, submission.approved, submission.issued and submission.acknowledged; may send via connectors or a portal

Data
- CloseoutTemplate: configurable checklist
- CloseoutItem: requirement, asset_id, linked document, status, owner, evidence
- CloseoutPackage: version, issue date, signed-off state
- SubmissionTemplate: type, version, schema, mapping, rules, terminology labels per tenant
- SubmissionPackage: project_id, authority/contact, status, revision, hash
- SubmissionItem: source entity reference, asset_id, mapped values
- ValidationResult
- TransmissionLog: sent time, channel, acknowledgement, authority reference
- Baseline condition snapshot per asset and the hash manifest per snapshot

Pages
- Reports > Closeout and Handover: checklist tree with live evidence status per item and a package assembly button feeding the submission builder
- Checklist board with percent complete by system or area
- Item detail with evidence panel
- Package preview and export
- Template designer with field mapper
- Package builder: asset subtree selection with completeness checklist and gap view
- Validation report
- Issue and acknowledgement tracker, including resubmission diff view

Decisions and notes
- Owner accepted all six scout suggestions: completeness engine, data book auto-assembly, client MDR templates, EAM register export, baseline condition snapshot and resubmission diff.
- Lead programmer advice: treat as a later phase and define the first target format with Kaefer or Rio Tinto, validating against it. This is consistent with the P2 suggestion; the owner has not asked for the generic XML engine to be dropped, so see open questions.
- Terminology must be renamable per market.
- AGPL-licensed OpenConstructionERP is a feature reference only.

Open questions
- Build the generic XML mapper from the start (feature list) or first ship one validated Kaefer/Rio Tinto format (lead programmer)?
- What is the first target format and which EAM import format should the register export match?
- Is sending via connectors or a portal in scope for the first release, or is issue recorded manually in the transmission log?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
