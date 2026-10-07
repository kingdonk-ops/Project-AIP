# Page specs for `eligibility`

#### Compliance register `/compliance` (Certificates, competency & calibration gate)

All certificates, calibrations, permits and use-by items.

- **layout**: Data table with RAG status column and filters.
- **sections**:
  - Filters (type, owner, status, flag)
  - Table
  - Summary counts by flag
- **actions**:
  - Add certificate
  - Export
  - Send renewal reminder
  - Mark superseded
  - Assign renewal owner
- **access**: Compliance admins, supervisors; people see their own

#### Expiring-soon feed `/compliance/expiring` (Certificates, competency & calibration gate)

Prioritised expiries grouped by window and owner.

- **layout**: Grouped list with date buckets; suppressed items hidden.
- **sections**:
  - Red/amber groups
  - Owner and project grouping
  - Suppression indicator toggle
- **actions**:
  - Open
  - Remind
  - Assign renewal owner
  - Export
- **access**: Supervisors, project managers, compliance admins

#### Add certificate `/compliance/new` (Certificates, competency & calibration gate)

Create a certificate for an owner entity.

- **layout**: Form with document upload.
- **sections**:
  - Type, owner, number
  - Issued/expiry
  - Issuer
  - Document
- **actions**:
  - Save
  - Save and add another
  - Cancel
- **access**: Compliance admins; owners may submit for approval

#### Certificate detail `/compliance/:id` (Certificates, competency & calibration gate)

Status, history and reliance.

- **layout**: Header with RAG chip; tabs.
- **sections**:
  - Summary
  - Linked document preview
  - Renewal/supersede history
  - Reminder history
  - Items relying on this certificate
  - Availability and suppression state
  - Eligibility result
  - Audit trail
- **actions**:
  - Edit
  - Supersede
  - Replace document
  - Request override
- **access**: Compliance admins, owner, supervisors

#### Competency matrix `/compliance/matrix` (Certificates, competency & calibration gate)

People vs template/category requirements.

- **layout**: Matrix grid with colour cells and sticky headers.
- **sections**:
  - Filters (team, project, discipline)
  - Matrix
  - Gap summary
- **actions**:
  - Drill into person
  - Export
  - Assign training
- **access**: Supervisors, quality managers

#### Override requests `/compliance/overrides` (Certificates, competency & calibration gate)

Audited override approvals.

- **layout**: Queue table with approval drawer.
- **sections**:
  - Pending requests
  - Reason and scope
  - Decision history
- **actions**:
  - Approve
  - Reject
  - Set max duration
- **access**: Approver role (quality manager)

#### Person qualifications `/people/:id/qualifications` (Certificates, competency & calibration gate)

Credentials per person.

- **layout**: Profile tab.
- **sections**:
  - Certificates list
  - Discipline gating status
- **actions**:
  - Add
  - Renew
- **access**: The person, supervisors, admins

#### Compliance settings `/settings/compliance` (Certificates, competency & calibration gate)

Types, windows and block rules.

- **layout**: Settings cards.
- **sections**:
  - Certificate types
  - Amber/red windows
  - Hard-block per type
  - Override policy
  - Suppression rule
  - Discipline gating
- **actions**:
  - Edit
  - Save
- **access**: Tenant admin
