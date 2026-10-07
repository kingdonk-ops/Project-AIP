# Transmittals & correspondence (`transmittals`)

- **Group:** Documents & records
- **Phase:** P2

What it is
Transmittals & correspondence is the formal, auditable record of which document revisions were sent to whom, when and why, together with the letters, emails, notices and memos exchanged on a project. It sits in Documents & records (suggested phase P2). It is not built in AIP yet. It replaces file_transmittals. It is positioned as the contractor or inspector's own controlled record, not a competitor to client platforms such as Aconex, Procore, ACC, Asite, Newforma or ProjectWise, and it imports external transmittal references rather than trying to replace them.

What it does
Transmittals lock the exact document versions issued, record recipients, reason, acknowledgements and responses, and chase overdue ones. The correspondence register logs inbound and outbound items with parties, threads and cross-references. Both feed change and claims evidence. Contractual notices carry time bars that create tasks and warn before expiry. Differentiators against the market are asset-level linkage, tenant-configurable terminology, hash-evidenced export, and permission-aware retrieval of correspondence for change intelligence and claims evidence.

Features
- Transmittal with auto number, recipients, reason, document revisions and acknowledgement tracking
- Numbering patterns, reason codes (for information, for review, for construction and similar) and statuses renamable per tenant via the terminology dictionary
- Recipient lists and distribution groups by role, company or package (reads file_distribution lists)
- Document picker that locks the exact revisions sent; issued records are immutable
- Asset-linked transmittal lines: each line carries an asset node and the inspection or data-book item it supports, so users can ask what was sent to the client about a given unit or line
- Hash-evidenced issue receipt: PDF transmittal cover with per-file SHA-256 values, plus downloadable proof of delivery and acknowledgement log
- Reissue and supersede chain showing which transmittal replaced which, with recipients who have not acknowledged the new revision highlighted
- Overdue chasers for unacknowledged transmittals
- External recipients use a portal link with click-through confirmation, without needing a full licence
- Import of external transmittals (CSV or forwarded email) as read-only records linked to local documents
- Correspondence register: letters, emails, notices, memos; inbound/outbound; filters; threads
- Cross-references to documents, RFIs, changes/variations and assets
- Templates for common notices, with merge fields
- Contract notice clock: clause library with time bars (days from trigger event) that creates tasks and warns before expiry
- Flag an item as a contractual notice; assign a response
- Restricted access for commercial items so subcontractors cannot see other parties' notices

Interactions
- Document library & control: what was sent; issuing locks the version
- Contacts & companies: recipients; also reads users
- Inbound capture & connectors (inbound_email, inbound_capture): inbound emails create correspondence items automatically
- Claims evidence pack (basic): correspondence cross-links and transmittal proofs feed evidence
- Change orders, variations & MOC (basic): notices and correspondence link to changes
- Deadlines and tasks: notice and overdue events create tasks
- Notifications: receive transmittal.issued and transmittal.overdue
- Change intelligence: consumes correspondence.received and notice.due
- Terminology dictionary: renamable codes, numbering and statuses

Data
- Transmittal: auto number, project, purpose/issue reason, sender, date, due response date, status, superseded-by link
- Line: document and version, asset node, inspection or data-book item, file SHA-256
- Recipient: contact, organisation
- Acknowledgement/Response: recipient, time, response text, portal confirmation
- CorrespondenceItem: type, direction in/out, parties, subject, date, response required by, thread id, contract clause or notice flag, commercial restriction flag
- Attachment: document id
- Cross-reference: RFI, variation, asset, document
- Clause library entry: clause, time bar in days, trigger event
- External transmittal import: source reference, read-only flag, linked local documents
- Events: transmittal.issued, transmittal.overdue, correspondence.received, notice.due

Pages
- Transmittal register
- Compose wizard: select files, recipients, purpose; document picker and recipient lists
- Transmittal detail with acknowledgement tracker and supersede chain
- Recipient view with acknowledge and respond (portal for externals)
- Correspondence register with filters
- Correspondence item detail with thread and links
- Notice tracker with due dates
- Clause library and notice template admin
- External transmittal import

Actions: issue, acknowledge, respond, reissue, overdue chase, log, link, flag as contractual notice, assign response.

Decisions and notes
- Owner accepted all six feature suggestions: asset-linked lines, hash-evidenced receipt, contract notice clock, external import, renamable terminology, and reissue/supersede chain.
- Issued records are immutable and lock the document version sent.
- Position as the controlled record with import of external references; do not try to match Aconex's network effect.
- The correspondence differentiator depends on reliable capture.
- Terminology must be renamable per market (first customer Kaefer on Rio Tinto remediation work).

Open questions
- None recorded from advisor conflicts. Competitor feature depth for InEight was flagged as uncertain by the researcher and is unverified.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
