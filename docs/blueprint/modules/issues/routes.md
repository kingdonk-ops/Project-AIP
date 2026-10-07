# Page specs for `issues`

#### Issue register `/issues` (Issues, NCRs & corrective actions)

List issues and NCRs.

- **layout**: Data table with pipeline filter; toggle to board.
- **sections**:
  - Status pipeline filter
  - Filters (type, severity, asset, responsible)
  - Table
- **actions**:
  - Create
  - Assign
  - Change severity
  - Export
  - Add to NCR
- **access**: Project members by scope; subcontractors only items scoped to them

#### Issue board `/issues/board` (Issues, NCRs & corrective actions)

Kanban by workflow status.

- **layout**: Kanban columns with swimlane option.
- **sections**:
  - Columns per status
  - Cards with severity and due
- **actions**:
  - Drag to transition (where permitted)
  - Open card
  - Filter
- **access**: Same as register

#### Raise issue `/issues/new` (Issues, NCRs & corrective actions)

Manual issue creation.

- **layout**: Form (dialog on mobile).
- **sections**:
  - Title, type, severity
  - Asset
  - Description
  - Responsible and due
  - Attachments with markup
- **actions**:
  - Save
  - Attach photo
  - Cancel
- **access**: Any project member with raise permission

#### Issue detail `/issues/:id` (Issues, NCRs & corrective actions)

Assess, fix, verify and close.

- **layout**: Header with workflow bar; tabs.
- **sections**:
  - Summary
  - Source inspection link
  - Assessment
  - Corrective actions
  - Evidence
  - Comments and subcontractor responses
  - Asset history
  - Audit trail
- **actions**:
  - Assess
  - Assign
  - Start
  - Mark ready for verification
  - Verify
  - Reopen
  - Close
  - Escalate to NCR
- **access**: Responsible, verifier (independent), managers

#### NCR detail `/ncrs/:id` (Issues, NCRs & corrective actions)

Root cause, disposition and CAPA.

- **layout**: Detail with NCR panel tabs.
- **sections**:
  - Classification
  - Root cause analysis
  - Disposition
  - CAPA
  - Cost impact
  - ITP step hold
  - Related inspections
- **actions**:
  - Set disposition
  - Add CAPA
  - Apply/lift hold
  - Verify
  - Close
- **access**: Quality managers; assigned owners; subcontractor response via portal

#### CAPA board `/issues/capa` (Issues, NCRs & corrective actions)

Track corrective and preventive actions.

- **layout**: Board/list with overdue highlighting.
- **sections**:
  - Actions by status
  - Overdue
- **actions**:
  - Update status
  - Reassign
  - Add evidence
- **access**: Action owners, quality managers

#### Issue settings `/settings/issues` (Issues, NCRs & corrective actions)

Types, severities, rules and SLAs.

- **layout**: Settings tabs.
- **sections**:
  - Types and severities
  - Auto-raise rules
  - Workflow and required fields
  - SLA and reminders
  - NCR categories and dispositions
  - Terminology
- **actions**:
  - Edit
  - Save
- **access**: Tenant admin; quality manager
