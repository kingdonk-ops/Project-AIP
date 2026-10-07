# Page specs for `prefab`

#### Unit Register `/projects/:pid/prefab/units` (Prefab & off-site manufacture)

Register of units with status pipeline

- **layout**: Register table with pipeline header chips
- **sections**:
  - Pipeline status chips
  - Unit table
  - Filters by type and destination
- **actions**:
  - Register unit
  - Bulk import
  - Filter
  - Export
- **access**: prefab.view; create with prefab.manage

#### Create/Edit Unit `/projects/:pid/prefab/units/new` (Prefab & off-site manufacture)

Register or revise a unit and generate ITP from stage template

- **layout**: Form with side summary
- **sections**:
  - Type, mark, revision
  - Destination asset picker
  - Stage template preview
  - BOM lines
- **actions**:
  - Save
  - Generate ITP
  - Revise
- **access**: prefab.manage

#### Unit Detail `/projects/:pid/prefab/units/:unitId` (Prefab & off-site manufacture)

Stage register, holds, BOM, shipment and handover checklist for one unit

- **layout**: Tabbed detail
- **sections**:
  - Stages and hold points
  - BOM and certificates
  - Shipment
  - Receipt
  - Handover checklist
  - Activity
- **actions**:
  - Release for dispatch
  - Release for install
  - Raise NCR
  - Print QR label
- **access**: prefab.view; gates require prefab.release and pass certificate checks

#### Production and Sequence Board `/projects/:pid/prefab/board` (Prefab & off-site manufacture)

Show units by production stage and sequence dependencies

- **layout**: Kanban by stage
- **sections**:
  - Stage columns
  - Unit cards with hold/NCR flags
  - Sequence dependency indicators
- **actions**:
  - Advance stage (if gates pass)
  - Filter
  - Open unit
- **access**: prefab.view

#### Delivery and Install Tracker `/projects/:pid/prefab/delivery` (Prefab & off-site manufacture)

Track shipments, ETA, receipt and installation

- **layout**: Table with map-free status timeline
- **sections**:
  - Shipments
  - Receipt status
  - Installation slots
- **actions**:
  - Create shipment
  - Record status event
  - Assign install slot
- **access**: prefab.view; manage with prefab.manage

#### Off-site Delivery Inspection List and Report `/projects/:pid/prefab/reports/delivery-inspection` (Prefab & off-site manufacture)

Per-delivery inspection list and generated report

- **layout**: List with report preview panel
- **sections**:
  - Delivery selector
  - Inspection list with results and photos
  - Report preview
- **actions**:
  - Generate report
  - Export PDF
  - Raise NCR
- **access**: prefab.view; generate with prefab.report

#### Handover Completeness View `/projects/:pid/prefab/handover` (Prefab & off-site manufacture)

Confirm documents, MDR and files handed over per unit

- **layout**: Matrix of units by required document
- **sections**:
  - Completeness matrix
  - Missing items list
- **actions**:
  - Link document
  - Mark handed over
  - Export
- **access**: prefab.view; edit with prefab.manage

#### Stage Templates and Unit Types `/settings/prefab/stage-templates` (Prefab & off-site manufacture)

Configure unit types, stages and ITP templates

- **layout**: List with editor
- **sections**:
  - Unit types
  - Stage sequence
  - ITP and gate bindings
- **actions**:
  - Create/edit
  - Publish
- **access**: prefab.configure

#### Mobile Scan and Receipt `/m/prefab/receive` (Prefab & off-site manufacture)

Scan QR, perform receipt inspection offline

- **layout**: Full-screen scanner then checklist
- **sections**:
  - Scanner
  - Receipt checklist
  - Damage photos
- **actions**:
  - Scan
  - Record result
  - Auto-raise NCR
  - Sync
- **access**: Field roles with prefab.receive
