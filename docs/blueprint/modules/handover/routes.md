# Page specs for `handover`

#### Closeout and Handover Overview `/projects/:pid/handover` (Handover, data books & submissions)

Live closeout status by system or area from evidence, entry point to package assembly

- **layout**: Split view: left asset/system checklist tree, right summary panel; KPI strip above
- **sections**:
  - KPI strip (percent complete, open punch, open NCRs, expiring certificates)
  - Checklist tree with live evidence status badges
  - Percent-complete by system/area chart
  - Package assembly call to action
- **actions**:
  - Filter by subtree/status
  - Open item detail
  - Start package build
  - Export checklist
- **access**: Project members with handover.view; Kaefer and client roles read-only per portal scope

#### Closeout Board `/projects/:pid/handover/board` (Handover, data books & submissions)

Kanban/percent view of systems or areas by closure state

- **layout**: Board with columns by status, toggle to grid of progress cards
- **sections**:
  - Group-by selector (system/area/discipline)
  - Cards with progress bars and blockers
  - Gap count chips
- **actions**:
  - Group/filter
  - Drill to subtree
  - Assign owner
- **access**: handover.view; assign requires handover.manage

#### Closeout Item Detail `/projects/:pid/handover/items/:itemId` (Handover, data books & submissions)

Show requirement, linked asset and evidence, and why it is open or closed

- **layout**: Two-column detail: header and metadata left, evidence panel right
- **sections**:
  - Requirement and asset link
  - Evidence panel (inspections, NCRs, certificates, documents)
  - Owner and due date
  - Activity tab
- **actions**:
  - Link/unlink evidence
  - Reassign owner
  - Open source record
  - Add comment
- **access**: handover.view; edit with handover.manage

#### Package Builder `/projects/:pid/handover/builder` (Handover, data books & submissions)

Select asset subtree and see completeness and gaps before building

- **layout**: Three-pane wizard: subtree selector, completeness checklist, gap view
- **sections**:
  - Asset tree with checkboxes
  - Template selector (MDR structure)
  - Completeness engine results by asset class
  - Gap list with click-through
- **actions**:
  - Select subtree
  - Choose template
  - Run completeness
  - Build draft package
- **access**: handover.manage

#### Package Preview and Export `/projects/:pid/handover/packages/:packageId` (Handover, data books & submissions)

Review compiled data book with hyperlinked index and export in chosen formats

- **layout**: Preview pane with index navigator left, document viewer right, action bar top
- **sections**:
  - Index tree with document codes
  - Document/PDF preview
  - Revision and diff selector
  - Hash manifest and signer panel
- **actions**:
  - Export CSV/Excel/PDF/JSON/XML
  - Freeze snapshot
  - Request signature
  - Send to submission
- **access**: handover.view; freeze/export with handover.issue

#### Validation Report `/projects/:pid/handover/submissions/:submissionId/validation` (Handover, data books & submissions)

List validation failures with click-through to fix the source record

- **layout**: Table with severity filters and detail drawer
- **sections**:
  - Summary counts
  - Results table (rule, record, message)
  - Source record drawer
- **actions**:
  - Open source record
  - Re-run validation
  - Export report
- **access**: handover.manage

#### Issue and Acknowledgement Tracker `/projects/:pid/handover/submissions` (Handover, data books & submissions)

Track submissions, review cycle, comments, responses and transmission log

- **layout**: Register table with detail side panel; tabs for Review and Transmission
- **sections**:
  - Submission register
  - Review comments and responses thread
  - Transmission log
  - Resubmission diff view
- **actions**:
  - Record issue/channel
  - Log acknowledgement
  - Respond to comment
  - Create new revision
  - Compare revisions
- **access**: handover.view; issue/acknowledge with handover.issue; client reviewers via portal

#### Template Designer and Field Mapper `/settings/handover/templates` (Handover, data books & submissions)

Configure closeout, MDR structure and submission templates and mappings

- **layout**: Designer with template list left, editor centre, mapping grid and sample preview right
- **sections**:
  - Template list and versions
  - Folder numbering and naming rules
  - Source-to-target field mapper
  - Validation rules
  - Terminology labels
- **actions**:
  - Create/clone template
  - Map fields
  - Test with sample asset
  - Publish version
- **access**: Tenant admin or handover.configure

#### Mobile Closeout Item `/m/handover/items/:itemId` (Handover, data books & submissions)

Field view of an item's status and evidence

- **layout**: Single-column cards with sticky action footer
- **sections**:
  - Status and requirement
  - Evidence list
  - Photo attach
- **actions**:
  - Attach evidence
  - Comment
- **access**: handover.view
