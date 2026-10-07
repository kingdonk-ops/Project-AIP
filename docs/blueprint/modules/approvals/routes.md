# Page specs for `approvals`

#### Approvals inbox `/approvals` (Workflow & approvals engine)

Everything waiting for the user's decision.

- **layout**: Table with filter bar and a right-hand preview pane.
- **sections**:
  - Filters (type, due, delegated to me, overdue, project, value band)
  - Inbox table (record, type, requested by, step, due, value, age)
  - Inline preview
  - Batch action bar
- **actions**:
  - Approve
  - Reject
  - Delegate
  - Open record
  - Preview
  - Batch approve
- **access**: Any user with an approval step assigned directly, by role, by team or by delegation; commercial items visible to involved parties only

#### Approval detail and instance timeline `/approvals/:instanceId` (Workflow & approvals engine)

Show route progress, decision history and guards for one instance.

- **layout**: Record preview on the left, route visualisation and timeline on the right.
- **sections**:
  - Record summary and preview
  - Route visualisation
  - Current step and approvers
  - Decision history (hash-chained)
  - Guards and qualification checks
  - Delegation
  - Stamp preview
  - Audit
- **actions**:
  - Approve
  - Reject
  - Delegate
  - Reassign
  - Recall
  - Resubmit
  - Re-authenticate on critical steps
- **access**: Participants and users with approvals.view on the record; reassign and recall need approvals.manage or requester

#### Workflow definitions `/settings/workflows` (Workflow & approvals engine)

List versioned definitions per record type and project.

- **layout**: Table with status and in-flight counts, plus preset gallery entry.
- **sections**:
  - Definitions table (name, record type, project, version, status, updated by, in flight)
  - Preset gallery
- **actions**:
  - Create from preset
  - Edit as new version
  - Simulate
  - Activate
  - Duplicate
  - View history
  - Archive
- **access**: approvals.design, tightly restricted; edits audited

#### Workflow template designer `/settings/workflows/:id/edit` (Workflow & approvals engine)

Design states, transitions, guards and side effects, with dry run.

- **layout**: Canvas state diagram in the centre, property panel on the right, simulator drawer at the bottom.
- **sections**:
  - State and transition canvas
  - Transition properties (role, guard, side effects)
  - Guard rule picker
  - Critical transition flags
  - Dry-run simulator with sample records
  - Version notes
- **actions**:
  - Add state or transition
  - Set guard
  - Simulate
  - Save as draft
  - Activate new version
- **access**: approvals.design; activation may need a second approver

#### Route templates `/settings/approval-routes` (Workflow & approvals engine)

Define ordered or parallel approver steps and threshold bands.

- **layout**: Table and step builder form.
- **sections**:
  - Route table (name, entity, steps, bands, active)
  - Step builder (approver user/role/team, order, due, qualification guard)
  - Escalation settings
- **actions**:
  - Create
  - Edit
  - Activate or deactivate
  - Simulate
- **access**: approvals.design

#### Authority matrix and delegation manager `/settings/authority-matrix` (Workflow & approvals engine)

Maintain value limits by role and entity and manage delegations.

- **layout**: Two tabs: matrix grid and delegations list.
- **sections**:
  - Authority matrix (role, entity, limit, currency)
  - Delegations (from, to, dates, scope)
  - Out-of-office cover
- **actions**:
  - Add limit
  - Edit
  - Create delegation
  - End delegation
- **access**: approvals.admin for matrix; users manage their own delegations

#### Mobile approvals `/approvals/mobile` (Workflow & approvals engine)

Approve or reject from the field with step-up authentication.

- **layout**: Mobile card list with detail sheet and PIN or MFA prompt.
- **sections**:
  - Pending cards
  - Detail sheet with preview
  - Step-up prompt
- **actions**:
  - Approve
  - Reject
  - Delegate
  - Re-authenticate
- **access**: Assigned approvers; device and credential policy applies

#### Approval settings `/settings/approvals` (Workflow & approvals engine)

Configure critical transitions, escalation, delegation rules and stamps.

- **layout**: Settings form.
- **sections**:
  - Critical transitions needing re-authentication
  - Escalation timings
  - Delegation rules
  - Parallel or sequential defaults
  - Who can edit definitions
  - Stamp templates
  - Terminology labels
- **actions**:
  - Save
  - Reset
- **access**: Tenant admin with approvals.admin
