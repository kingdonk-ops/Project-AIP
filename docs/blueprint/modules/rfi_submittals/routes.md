# Page specs for `rfi_submittals`

#### RFI register `/rfis` (RFIs & submittals)

List RFIs with ageing and asset-subtree filters.

- **layout**: DataTable with a filter bar and saved views; the title uses the tenant label (RFI, TQ, Query).
- **sections**:
  - Filters (subtree, status, discipline, ball-in-court)
  - Table with ageing column
  - Disambiguation prefix versus Request for Inspection
- **actions**:
  - Raise
  - Export
  - Bulk assign
  - Open
- **access**: rfi.view; external parties see only items shared with them

#### RFI form `/rfis/new` (RFIs & submittals)

Create or edit an RFI.

- **layout**: Form with an attachment and photo markup panel.
- **sections**:
  - Question
  - Discipline, asset(s) and package
  - Drawing and document references
  - Due date
  - Cost and schedule impact flags
  - Attachments with markup
- **actions**:
  - Save draft
  - Raise
  - Cancel
- **access**: rfi.create

#### RFI detail `/rfis/:id` (RFIs & submittals)

Track the question, response thread and outcome.

- **layout**: Header with WorkflowBar, main thread, right rail with references and CommentPanel.
- **sections**:
  - Question and response thread
  - Drawing cross-references
  - Impact estimate
  - Linked inspections affected
  - Activity
- **actions**:
  - Assign
  - Respond
  - Accept or reject
  - Close
  - Convert to variation candidate
- **access**: Parties on the RFI; respond needs rfi.respond; convert needs change.create

#### Submittal register `/submittals` (RFIs & submittals)

List submittals with type, review status and ageing.

- **layout**: DataTable with filters and an ageing column.
- **sections**:
  - Filters by type, spec, status and asset subtree
  - Table with revision and required-by date
  - Overdue indicators
- **actions**:
  - Create
  - Import from spreadsheet (if enabled)
  - Export
  - Open
- **access**: submittal.view

#### Review workspace `/submittals/:id/review` (RFIs & submittals)

Review a submittal beside the document viewer.

- **layout**: Split view: document viewer left, review form and code selector right.
- **sections**:
  - Viewer with markup
  - Review steps and reviewer
  - Outcome code selector
  - Linked gate effects
- **actions**:
  - Review
  - Return with code
  - Resubmit
  - Close
- **access**: Assigned reviewers; submit by owning party

#### Resubmission comparison `/submittals/:id/compare` (RFIs & submittals)

Compare revisions of a submittal.

- **layout**: Side-by-side with a revision picker and a change summary.
- **sections**:
  - Revision selector
  - Document diff
  - Review history
- **actions**:
  - Select revisions
  - Download comparison
- **access**: submittal.view

#### Asset-node panel `/assets/:id/rfis-submittals` (RFIs & submittals)

Show open RFIs and submittals on an asset and their effect on pending inspections.

- **layout**: Tab on the asset node with a gate impact banner.
- **sections**:
  - Open RFIs
  - Open submittals
  - Blocking gates on inspections and tasks
- **actions**:
  - Open item
  - Raise RFI for this asset
- **access**: Asset view permission

#### Response-time analytics `/rfis/analytics` (RFIs & submittals)

Analyse response times by party, discipline and area.

- **layout**: Dashboard with charts and a filter bar.
- **sections**:
  - Response time by party
  - By discipline and asset area
  - Ageing distribution
- **actions**:
  - Filter
  - Export
- **access**: rfi.analytics or project manager

#### RFI and submittal settings `/admin/rfi-submittals` (RFIs & submittals)

Configure labels, numbering, review codes, submittal types and gate rules.

- **layout**: Settings tabs.
- **sections**:
  - Label and numbering
  - Review codes and accepted flags
  - Submittal types and approval routes
  - Gate rules
  - Overdue thresholds
- **actions**:
  - Edit
  - Add code or type
  - Add gate rule
- **access**: Tenant admin or module admin
