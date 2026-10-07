# Page specs for `transmittals`

#### Transmittal register `/transmittals` (Transmittals & correspondence)

List all transmittals with acknowledgement and overdue state.

- **layout**: Table with filter bar and row action menu.
- **sections**:
  - Filters (status, purpose, recipient, date, overdue, asset)
  - Register table (number, date, purpose, recipients, documents, status, response due, acknowledged, superseded by)
- **actions**:
  - Compose
  - Open
  - Reissue
  - Chase
  - Download cover
  - Download proof
  - Export register
- **access**: transmittals.view; compose needs transmittals.issue

#### Compose transmittal wizard `/transmittals/new` (Transmittals & correspondence)

Select document revisions, recipients and reason, then issue.

- **layout**: Stepper: documents, recipients, details, review.
- **sections**:
  - Document picker locking revisions
  - Per-line asset picker
  - Recipients and groups
  - Purpose, response due and message
  - Review with SHA-256 list
- **actions**:
  - Save draft
  - Issue
  - Cancel
- **access**: transmittals.issue; documents limited by user's scope

#### Transmittal detail `/transmittals/:id` (Transmittals & correspondence)

Show an issued transmittal with acknowledgements and supersede chain.

- **layout**: Header with status, tabs for lines, recipients and chain, and activity panel.
- **sections**:
  - Header and purpose
  - Lines (document, revision, asset, hash)
  - Recipients and acknowledgements
  - Supersede chain
  - Proof of delivery
  - Linked records
  - Audit
- **actions**:
  - Chase
  - Reissue
  - Download cover
  - Download proof
  - Record response
- **access**: transmittals.view; issued records immutable

#### Recipient acknowledgement (portal) `/t/:token` (Transmittals & correspondence)

Let external recipients view files and confirm receipt without a full licence.

- **layout**: Minimal portal page with file list and click-through confirmation.
- **sections**:
  - Transmittal summary
  - File list with hashes
  - Acknowledgement text
  - Response box
- **actions**:
  - Download files
  - Acknowledge
  - Respond
- **access**: Named external recipient via scoped single-use link; POST confirmation

#### Correspondence register `/correspondence` (Transmittals & correspondence)

Log and search letters, emails, notices and memos.

- **layout**: Table with filters and thread view in a right drawer.
- **sections**:
  - Filters (type, direction, party, date, notice, status)
  - Register table (ref, type, direction, subject, parties, date, response by, notice, status)
  - Thread preview
- **actions**:
  - Log item
  - Assign response
  - Flag as notice
  - Export
- **access**: correspondence.view; commercial items restricted to involved parties

#### Log correspondence `/correspondence/new` (Transmittals & correspondence)

Create an inbound or outbound item, optionally from a template.

- **layout**: Form with attachments and link panel.
- **sections**:
  - Type, direction, subject, parties, date
  - Template and merge fields
  - Attachments from library
  - Cross-references (RFI, variation, asset, document)
  - Commercial restriction flag
- **actions**:
  - Save
  - Send (outbound)
  - Attach
  - Cancel
- **access**: correspondence.create

#### Correspondence detail `/correspondence/:id` (Transmittals & correspondence)

Show an item with its thread, links and response status.

- **layout**: Main thread column with side panel of links.
- **sections**:
  - Header
  - Thread
  - Attachments
  - Cross-references
  - Response assignment
  - Audit
- **actions**:
  - Reply
  - Assign response
  - Link record
  - Flag as contractual notice
- **access**: correspondence.view subject to restriction rules

#### Notice tracker `/notices` (Transmittals & correspondence)

Track contractual notices and time bars.

- **layout**: Table sorted by days remaining with traffic-light state, plus calendar toggle.
- **sections**:
  - Notice table (clause, trigger event, due date, days left, owner, status)
  - Overdue banner
- **actions**:
  - Create task
  - Assign owner
  - Mark issued
  - Open correspondence
- **access**: transmittals.notices; commercial restrictions apply

#### External transmittal import `/transmittals/import` (Transmittals & correspondence)

Import external transmittal references as read-only records.

- **layout**: Upload wizard with column mapping and preview.
- **sections**:
  - Upload CSV or forwarded email
  - Column mapping
  - Match to local documents
  - Preview and confirm
- **actions**:
  - Upload
  - Map columns
  - Import
  - Cancel
- **access**: transmittals.import

#### Clause library, templates and settings `/settings/transmittals` (Transmittals & correspondence)

Administer clauses, notice templates, numbering, codes and chasers.

- **layout**: Tabbed settings.
- **sections**:
  - Numbering patterns
  - Reason codes and statuses
  - Distribution groups
  - Chaser schedule
  - Portal acknowledgement text
  - Clause library
  - Notice templates with merge fields
  - Commercial restriction rules
  - Inbound email mapping
  - Terminology labels
- **actions**:
  - Add clause
  - Edit template
  - Save
  - Test merge
- **access**: transmittals.admin

#### Mobile transmittals `/m/transmittals` (Transmittals & correspondence)

Check what was sent and acknowledge or respond on a phone.

- **layout**: Mobile list and detail with file preview.
- **sections**:
  - Received and sent list
  - Detail with lines
  - Acknowledge action
- **actions**:
  - Open
  - Acknowledge
  - Respond
- **access**: Recipients and transmittals.view holders
