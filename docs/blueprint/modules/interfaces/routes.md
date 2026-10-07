# Page specs for `interfaces`

#### Interface list `/interfaces` (Interface management)

List interface points with ageing and status.

- **layout**: DataTable with filters and saved views.
- **sections**:
  - Filters (package, party, status, asset subtree)
  - Table with need date and days late
  - Escalation level
- **actions**:
  - Raise
  - Agree
  - Deliver
  - Accept
  - Escalate
  - Export
- **access**: interfaces.view; party-scoped visibility applied

#### Interface matrix `/interfaces/matrix` (Interface management)

Show who provides what to whom by package or contractor.

- **layout**: Grid of provider by receiver with counts and drill-down.
- **sections**:
  - Matrix grid
  - Status colouring
  - Drill-down list
- **actions**:
  - Drill into cell
  - Change grouping
  - Export
- **access**: interfaces.view

#### Ageing heat-map `/interfaces/heatmap` (Interface management)

Show overdue and at-risk interfaces by package pair.

- **layout**: Heat-map with a threshold legend and a side list.
- **sections**:
  - Heat-map
  - Thresholds
  - At-risk list
- **actions**:
  - Filter
  - Open interfaces
  - Export report
- **access**: Project managers and interfaces.view

#### Create or edit interface `/interfaces/new` (Interface management)

Raise an interface point, optionally from a template.

- **layout**: Form.
- **sections**:
  - Template picker
  - Provider, receiver and deliverable
  - Asset node and scope task
  - Need date
  - Blocked-by relations
- **actions**:
  - Save
  - Raise
  - Cancel
- **access**: interfaces.create

#### Interface detail `/interfaces/:id` (Interface management)

Manage the lifecycle, evidence and two-party sign-off.

- **layout**: Header with status stepper and WorkflowBar, main body, right rail with CommentPanel.
- **sections**:
  - Agreement
  - Evidence (photos, certificates, inspection records, documents)
  - Linked RFIs and submittals
  - Blocked tasks
  - Escalation history
  - Acceptance attestations
- **actions**:
  - Agree
  - Deliver
  - Accept and sign (provider and receiver)
  - Escalate
  - Attach evidence
- **access**: Provider and receiver parties; others read-only per visibility rules

#### Templates and escalation ladder `/admin/interfaces` (Interface management)

Configure interface templates, escalation levels and timings.

- **layout**: Settings tabs.
- **sections**:
  - Templates with default providers, receivers and lead times
  - Escalation ladder levels and roles
  - Heat-map thresholds
  - Status labels
- **actions**:
  - Add or edit template
  - Edit ladder
  - Set thresholds
- **access**: interfaces.admin
