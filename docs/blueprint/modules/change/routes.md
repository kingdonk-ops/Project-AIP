# Page specs for `change`

#### Change Register `/projects/:projectId/changes` (Change orders, variations & MOC (basic))

Register of all change records, using tenant-labelled types (change order, variation, MOC, discovered condition).

- **layout**: Toggle between a DataTable and a stage pipeline (notice, request, order, measured, final account).
- **sections**:
  - View toggle
  - Filters (type, status, asset, notice clock state)
  - Pipeline columns
  - Register table with time-bar warning chips
- **actions**:
  - Create change
  - Open
  - Filter
  - Export
  - Save view
- **access**: Project members with change.view. Commercial values need change.view_commercial_values.

#### Create Change `/projects/:projectId/changes/new` (Change orders, variations & MOC (basic))

Raise a change from a notice, instruction, RFI or inspection finding.

- **layout**: FormRenderer page, prefilled when launched from a source record.
- **sections**:
  - Type and source
  - Description
  - Asset picker
  - Time and cost impact
  - Contract reference and notice start event
  - Attachments and photos
- **actions**:
  - Save draft
  - Submit
  - Link source record
- **access**: Users with change.create

#### Change Detail `/projects/:projectId/changes/:id` (Change orders, variations & MOC (basic))

Full record with timeline, lines, notice clock, links and approvals.

- **layout**: Header with a WorkflowBar and notice clock badge. Tabs: Overview, Lines, Daywork, Links, Timeline, Approvals.
- **sections**:
  - Header and status
  - Notice clock panel
  - Change lines table (cost-code text fields)
  - Linked correspondence, diary, phone log and RFIs
  - Attachments
  - Timeline
  - Approval trail
- **actions**:
  - Edit
  - Submit
  - Approve
  - Reject
  - Add line
  - Generate confirmation letter
  - Advance stage
- **access**: change.view for viewing. Approval requires change.approve. Commercial values are redacted without permission.

#### Daywork Sheet Capture `/projects/:projectId/changes/:id/daywork/new` (Change orders, variations & MOC (basic))

Build a daywork sheet from field records and capture the client signature.

- **layout**: Stepper form that works on tablet and mobile.
- **sections**:
  - Source pull (crew, hours, consumables, plant)
  - Editable lines
  - Client signature pad
  - Summary
- **actions**:
  - Pull from diary and ledger
  - Edit lines
  - Capture signature
  - Submit
- **access**: Supervisors and site leads with change.daywork

#### MOC Detail `/projects/:projectId/moc/:id` (Change orders, variations & MOC (basic))

Management of change review, checklists and close-out gate.

- **layout**: Stage stepper (proposal, technical review, risk review, approval, implementation, close-out) with checklist panels.
- **sections**:
  - Stage stepper
  - Checklist by discipline (engineering, integrity, HSE)
  - Required reviewer roles and sign-off status
  - Open actions list (gate before close-out)
  - Linked documents
- **actions**:
  - Complete checklist item
  - Sign review
  - Raise action
  - Advance stage
  - Close out (blocked while actions are open)
- **access**: Required reviewers and MOC owners with change.moc

#### Change Settings `/settings/change` (Change orders, variations & MOC (basic))

Configure types, workflow, notice periods and MOC checklist templates.

- **layout**: Settings tabs.
- **sections**:
  - Change types and labels (via terminology keys)
  - Lifecycle workflow
  - Contract notice period configuration
  - MOC checklist templates per discipline
  - Confirmation letter template
- **actions**:
  - Add type
  - Edit notice period
  - Edit checklist template
  - Preview workflow
- **access**: Tenant or project admins with change.admin

#### Mobile Verbal Instruction and Discovered Condition `/m/changes/capture` (Change orders, variations & MOC (basic))

Quick field capture of a verbal instruction or a discovered condition with photos.

- **layout**: Mobile single-column form with a camera-first flow and offline queue.
- **sections**:
  - Type picker
  - Voice note or text
  - Photos
  - Asset picker
  - Instructing person
- **actions**:
  - Save draft change
  - Attach photo
  - Record voice note
  - Queue offline
- **access**: Field users with change.create
