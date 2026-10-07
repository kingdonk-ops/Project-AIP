# Page specs for `components`

#### Material and certificate passports `/quality/passports` (Traceability graph: components, materials & certificates)

Search-first register of material passports.

- **layout**: Prominent search bar with a DataTable and filters.
- **sections**:
  - Search by heat, batch, certificate or serial
  - Table: passport no., material, certificate type, certificate no., heat/batch, supplier, status, used count, valid until
  - Filters: certificate type, status, supplier
- **actions**:
  - Create via certificate upload
  - Quarantine batch
  - Request OCR review
  - Link document
  - Export
- **access**: traceability.view; create and quarantine need specific permissions.

#### New passport with OCR review `/quality/passports/new` (Traceability graph: components, materials & certificates)

Upload a scanned certificate and review extracted fields.

- **layout**: Split view with the document viewer on the left and the extracted-fields form on the right.
- **sections**:
  - Upload
  - Extracted fields with confidence
  - Cross-check results
  - Material details
- **actions**:
  - Correct fields
  - Save passport
  - Reject
  - Request second review
- **access**: passport.create; reviewers need passport.review.

#### Passport detail `/quality/passports/:id` (Traceability graph: components, materials & certificates)

Certificate, genealogy and quarantine for one heat or batch.

- **layout**: Header with tabs and a certificate viewer.
- **sections**:
  - Summary
  - Certificate viewer and OCR cross-check
  - Traceability graph
  - Forward genealogy
  - Backward genealogy
  - Validity snapshots
  - Linked inspections, ITPs, NCRs
  - Documents
  - Quarantine history
  - Activity
- **actions**:
  - Quarantine
  - Release quarantine
  - Export evidence pack
  - Link usage
- **access**: traceability.view; actions per permission.

#### Traceability graph view `/trace/:type/:id` (Traceability graph: components, materials & certificates)

Interactive chain for an asset, task, batch, person or instrument.

- **layout**: Full-width graph canvas with a filter panel and node detail drawer, plus a table fallback.
- **sections**:
  - Graph canvas
  - Filters by type and depth
  - Node details with validity snapshot
  - Table view
- **actions**:
  - Expand node
  - Filter
  - Open record
  - Export graph
  - Start impact analysis
- **access**: Permission-aware; nodes outside the user's scope are shown masked or hidden.

#### Weld map and joint register `/quality/weld-map` (Traceability graph: components, materials & certificates)

Track joints with welder, WPS, batch and NDT metrics.

- **layout**: Toggle between table and drawing overlay, with a filter bar.
- **sections**:
  - Joint table: welder, WPS, consumable batch, NDT percentage and status, repair count, rejection rate
  - Drawing view with clickable joints
  - Analytics tab: repair rate by welder, WPS and batch
- **actions**:
  - Filter
  - Open joint
  - Export
  - Create inspection request
- **access**: weld.view; edit by weld.edit.

#### Inspection request queue `/quality/inspection-requests` (Traceability graph: components, materials & certificates)

Work the queue of MIR, WIR, IR and hidden-works requests.

- **layout**: Queue table with a status board toggle.
- **sections**:
  - Queue with SLA indicators
  - Acceptance criteria panel
  - Linked records
- **actions**:
  - Assign
  - Accept or reject
  - Open inspection
  - Export
- **access**: Inspectors and QA with request permissions.

#### Quarantine impact report `/quality/quarantine/:id` (Traceability graph: components, materials & certificates)

Show every affected component, task and inspection.

- **layout**: Summary banner and grouped affected-items tables.
- **sections**:
  - Trigger (heat, batch or instrument)
  - Affected components
  - Affected tasks
  - Affected inspections
  - NCRs raised
  - Evidence pack
- **actions**:
  - Raise NCRs
  - Notify owners
  - Release
  - Export report
  - Generate evidence pack
- **access**: quarantine.manage; view for QA.

#### Mobile traceability lookup `/m/trace/:id` (Traceability graph: components, materials & certificates)

Check batch, welder or instrument validity in the field.

- **layout**: Single-column cards with a scan button.
- **sections**:
  - Scan or search
  - Validity status
  - Linked records
- **actions**:
  - Scan
  - Link to task
  - Flag problem
- **access**: Internal field users with synced scope.
