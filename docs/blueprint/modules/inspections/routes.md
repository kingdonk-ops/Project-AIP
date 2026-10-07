# Page specs for `inspections`

#### Inspection register `/inspections` (Inspections, ITPs & hold points)

Cross-asset list of inspections, ITPs and RFIs.

- **layout**: Data table with saved views; optional board toggle by status.
- **sections**:
  - Filters (kind, status, asset, discipline, assignee, due)
  - Table
  - Bulk bar
- **actions**:
  - Create
  - Assign
  - Approve
  - Reject/resend
  - Reschedule
  - Export
  - Open review queue
- **access**: Project members by scope; bulk approve limited to reviewer roles

#### Create inspection `/inspections/new` (Inspections, ITPs & hold points)

Instantiate a template against an asset.

- **layout**: Wizard dialog.
- **sections**:
  - Select asset (tree picker)
  - Select template and pinned revision
  - Assignee (competency-aware)
  - Due date and booking
- **actions**:
  - Create draft
  - Assign
  - Cancel
- **access**: Inspectors, supervisors, coordinators

#### Inspection detail `/inspections/:id` (Inspections, ITPs & hold points)

Full-page execution and review.

- **layout**: Header with workflow bar; main answers column; right rail for sign-off and links.
- **sections**:
  - Header (number, asset, revision, status)
  - Eligibility banner
  - Questions and append-only answers
  - ITP steps with point types
  - Sign-off chips with auth strength
  - Linked tasks and downstream blocks
  - Evidence and instruments
  - Issues raised
  - Bookings
  - Related inspections by discipline
  - Review history
  - Report
  - Audit trail
- **actions**:
  - Autosave
  - Discard
  - Submit
  - Approve/reject
  - Release hold point
  - Sign
  - Re-inspect
  - Raise issue
  - Generate report
- **access**: Assignee, reviewers per workflow stage, client reviewer when enabled

#### Review queue `/inspections/review` (Inspections, ITPs & hold points)

Step through items awaiting review.

- **layout**: Split view with next/previous.
- **sections**:
  - Queue list
  - Inspection preview
  - Decision panel
- **actions**:
  - Approve
  - Reject with reason
  - Next/previous
  - Skip
- **access**: Inspector, supervisor and client reviewers by stage

#### ITP progress `/itps/:id` (Inspections, ITPs & hold points)

Step-by-step ITP status for an asset or work package.

- **layout**: Vertical step timeline with point-type badges.
- **sections**:
  - Steps (hold, witness, review, surveillance)
  - Linked tasks
  - Notice periods and bookings
  - Sign-offs
- **actions**:
  - Release hold
  - Acknowledge witness
  - Book inspection
  - Waive (with override)
- **access**: Authorised releasers and witnesses; others read-only

#### Scheduling calendar `/inspections/calendar` (Inspections, ITPs & hold points)

Customer/inspector bookings.

- **layout**: Month/week/agenda calendar with side filters.
- **sections**:
  - Bookings
  - Invitations status
  - Notice-period warnings
- **actions**:
  - Create booking
  - Reschedule
  - Cancel
  - Send reminder
  - Accept/decline invite
- **access**: Schedulers, inspectors; clients see their own bookings

#### Inspection programmes `/inspections/programmes` (Inspections, ITPs & hold points)

Recurring and triggered inspection plans.

- **layout**: Table with detail drawer.
- **sections**:
  - Programmes (frequency, next due, trigger)
  - Generated inspections
- **actions**:
  - Create
  - Edit
  - Pause
  - Run now
- **access**: Quality managers, schedulers

#### Create/edit programme `/inspections/programmes/new` (Inspections, ITPs & hold points)

Define triggers and targets.

- **layout**: Form page.
- **sections**:
  - Template and asset scope
  - Frequency and triggers (calendar, cert expiry, issue, ad hoc)
  - Lead time and assignment rules
- **actions**:
  - Save
  - Preview next dates
- **access**: Quality managers

#### Inspection settings `/settings/inspections` (Inspections, ITPs & hold points)

Workflow and point-type configuration.

- **layout**: Settings tabs.
- **sections**:
  - Workflow stages per kind
  - Point types and notice periods
  - Sign-off rules
  - Overrides
  - Auto-raise rules
  - Terminology
- **actions**:
  - Edit
  - Save
- **access**: Tenant admin; quality manager

#### ITP step execution (mobile) `/m/inspections/:id/step/:stepId` (Inspections, ITPs & hold points)

Execute a step with evidence and signature on device.

- **layout**: Full-screen step view.
- **sections**:
  - Eligibility banner
  - Acceptance criteria
  - Evidence capture
  - Signature
- **actions**:
  - Pass/fail
  - Capture
  - Sign
  - Request hold release
- **access**: Eligible assigned inspector
