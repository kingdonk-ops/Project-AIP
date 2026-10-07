# Page specs for `punchlist`

#### Punch/defects register `/punch` (Punch list & defects liability)

All punch items and DLP defects.

- **layout**: Table with list/map/drawing toggle and grouping.
- **sections**:
  - Filters (phase, area, party, status)
  - Grouped table with photo thumbs
  - Bulk bar
- **actions**:
  - Create
  - Assign
  - Change due date
  - Verify selected
  - Export per area
  - Add to transmittal
- **access**: Project members; contractors see items assigned to their company

#### Create punch item `/punch/new` (Punch list & defects liability)

Log a snag with photo and pin.

- **layout**: Form; mobile quick-capture variant.
- **sections**:
  - Description, asset
  - Drawing pin
  - Photos
  - Category, priority
  - Responsible party, due
- **actions**:
  - Save
  - Add pin
  - Capture photo
- **access**: Project members with raise permission

#### Punch item detail `/punch/:id` (Punch list & defects liability)

Fix, verify and close.

- **layout**: Header with workflow bar; tabs.
- **sections**:
  - Summary
  - Photos
  - Location (tree path and pin)
  - Verification record
  - Status history
  - Escalation to NCR
  - DLP details
  - Retention linkage
  - Comments
  - Audit trail
- **actions**:
  - Mark fixed
  - Verify (not assignee)
  - Reject/reopen
  - Escalate to NCR
  - Close
- **access**: Responsible party, independent verifier, managers

#### Verification queue `/punch/verification` (Punch list & defects liability)

Items awaiting verification.

- **layout**: Queue with preview.
- **sections**:
  - Ready-for-verification list
  - Evidence preview
- **actions**:
  - Verify
  - Reject
  - Next
- **access**: Verifiers

#### Defects liability `/punch/dlp` (Punch list & defects liability)

DLP periods and post-handover defects.

- **layout**: Dashboard plus table.
- **sections**:
  - DLP periods with start/end
  - Open defects by contractor
  - Ending-soon alerts
  - Retention eligibility
- **actions**:
  - Create DLP
  - Assign defect
  - Export
  - Flag retention release
- **access**: Project and commercial managers

#### Walkdown mode (mobile) `/m/walkdown` (Punch list & defects liability)

Rapid offline snag capture while walking an area.

- **layout**: Full-screen map/drawing with floating capture button.
- **sections**:
  - Area plan with pins
  - Quick capture sheet
  - Session list
- **actions**:
  - Drop pin
  - Photo
  - Voice note
  - Assign later
  - Finish walkdown
- **access**: Inspectors and walkdown participants

#### Punch settings `/settings/punch` (Punch list & defects liability)

Terms, categories and rules.

- **layout**: Settings cards.
- **sections**:
  - Term labels
  - Categories and priorities
  - Verification rule
  - DLP defaults
  - Retention gating
  - Export layouts
- **actions**:
  - Edit
  - Save
- **access**: Tenant admin
