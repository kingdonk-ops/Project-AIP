# Page specs for `temporary_works`

#### Temporary works register `/projects/:projectId/temporary-works` (Temporary works register)

List temporary works items with stage chips for design, check, permit to load, in use and permit to strike.

- **layout**: DataTable with stage chips on each row, filters and a board toggle by stage.
- **sections**:
  - Filters (category, risk class, stage, status, site, overdue inspection)
  - Table (TW no., description, category, risk class, asset, designer, checker, stage, status, next inspection)
  - Stage board view
  - Bulk action bar
- **actions**:
  - Register item
  - Open
  - Submit design
  - Request check
  - Issue permit to load
  - Record inspection
  - Request permit to strike
  - Assign coordinator
  - Export
- **access**: tw.view. Register needs tw.manage. Stage actions are role-gated by the workflow.

#### Register or edit TW item `/projects/:projectId/temporary-works/new` (Temporary works register)

Create an item, assign a designer, independent checker and coordinator, and link scopes.

- **layout**: Form with an asset picker, plus an inline competency check beside each person field.
- **sections**:
  - Description, category and risk class
  - Asset and location
  - Designer (competency checked)
  - Independent checker (must differ from designer)
  - TW Coordinator
  - Linked scopes
- **actions**:
  - Save
  - Cancel
- **access**: tw.manage. The designer and checker rule is enforced server-side.

#### TW item detail `/projects/:projectId/temporary-works/:twId` (Temporary works register)

Run an item through the full BS 5975 style lifecycle with evidence at each stage.

- **layout**: Header with stage chips and the WorkflowBar. The body is tabbed with a competency status rail on the right.
- **sections**:
  - Summary and stage chips
  - Design brief
  - Design and calculations
  - Independent check
  - Permit to load
  - Inspections in use
  - Permit to strike
  - Linked scopes and ITP holds
  - Competency status
  - Documents
  - Audit trail
- **actions**:
  - Submit design
  - Request or complete check
  - Issue permit to load
  - Record inspection
  - Request permit to strike
  - Issue permit to strike
  - Attach document
  - Link scope
- **access**: Designer, checker, coordinator and supervisors by role. Permit issue needs the coordinator competency. Designer and checker cannot be the same person.

#### Permits register `/projects/:projectId/temporary-works/permits` (Temporary works register)

List permits to load and permits to strike.

- **layout**: DataTable with filters.
- **sections**:
  - Filters (type, status, issuer, date)
  - Permit table (permit no., type, TW item, issued by, date, status)
- **actions**:
  - Open permit
  - Create permit
  - Export
- **access**: tw.view. Issue needs tw.permit.issue.

#### Permit form `/projects/:projectId/temporary-works/permits/:permitId` (Temporary works register)

Complete and sign a permit to load or permit to strike.

- **layout**: Form page built from a permit template, with a sign-off panel and the hold status.
- **sections**:
  - Permit details
  - Conditions checklist
  - Sign-off panel
  - Hold flag effect on linked ITP steps and tasks
- **actions**:
  - Sign
  - Issue
  - Reject
  - Cancel permit
- **access**: Coordinator and authorised approvers by workflow role

#### Inspection schedule and overdue `/projects/:projectId/temporary-works/inspections` (Temporary works register)

See upcoming and overdue periodic inspections, such as weekly scaffold tags.

- **layout**: Calendar and list toggle, with overdue items highlighted.
- **sections**:
  - Calendar
  - Due and overdue list
  - Failed inspections
- **actions**:
  - Open inspection
  - Reschedule
  - Record inspection
  - Export
- **access**: tw.view. Recording needs inspection.execute with the right competency.

#### Temporary works settings `/settings/temporary-works` (Temporary works register)

Configure categories, risk classes, competencies, separation rule, workflows and frequencies.

- **layout**: Settings page with sections.
- **sections**:
  - Categories and risk classes
  - Required competencies per role
  - Designer and checker separation rule
  - Permit workflows
  - Inspection frequencies
  - Hold-release behaviour
  - Notification recipients
- **actions**:
  - Edit and save
  - Edit workflow
- **access**: Tenant admin or tw.settings.manage

#### Mobile TW inspection `/m/temporary-works/:twId/inspect` (Temporary works register)

Record a periodic inspection or scaffold tag check on site, offline-capable.

- **layout**: Mobile checklist screen with the item header, pass or fail controls and a bottom submit bar.
- **sections**:
  - Item header with permit status
  - Inspection checklist
  - Photo capture
  - Competency warning
  - Sync status
- **actions**:
  - Answer checks
  - Capture photo
  - Submit inspection
  - Raise issue
- **access**: Assigned inspectors who hold the required competency
