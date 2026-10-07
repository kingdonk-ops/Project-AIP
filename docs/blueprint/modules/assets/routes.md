# Page specs for `assets`

#### Asset tree and register `/assets` (Asset hierarchy & registers)

Browse and manage the hierarchy with open-item counts.

- **layout**: Collapsible left tree panel and main list or detail area, with a top scope bar and scope chip.
- **sections**:
  - Tree with open-item counts
  - Context menu
  - Asset table: name, tag number, item type, status, criticality, open items
  - Filters: item type, category, status, criticality
- **actions**:
  - Add item or module
  - Bulk add (pattern ###, up to 100)
  - Drag to reparent or reorder
  - Sort
  - Import
  - Move
  - Change status
  - Print labels
  - Export subtree
- **access**: asset.view within project and subtree scope; edit needs asset.edit.

#### Create or edit asset `/assets/new` (Asset hierarchy & registers)

Add an asset using a generated form.

- **layout**: Slide-over or full-page form.
- **sections**:
  - Parent tree picker
  - Item type
  - Name, tag number (conflict-checked)
  - Category, criticality, status
  - GPS map point
  - Attributes generated from item type, including CUI fields
- **actions**:
  - Save
  - Save and add another
  - Cancel
- **access**: asset.create.

#### Asset detail `/assets/:id` (Asset hierarchy & registers)

One asset's attributes and full history across projects.

- **layout**: Header with breadcrumb path and tabbed body.
- **sections**:
  - Header: name, tag, internal tag, status, criticality
  - Attributes
  - History timeline
  - Inspections and ITPs
  - Issues and NCRs
  - Documents and P&ID links
  - Certificates and calibration
  - Child assets and components
  - Lineage
  - Projects in scope
  - Location map
  - Labels and tags
  - Activity
- **actions**:
  - Edit
  - Reparent
  - Merge or split
  - Retag
  - Print label
  - Link document
  - Raise issue
  - Start inspection
- **access**: asset.view; actions per permission and scope.

#### Register page `/registers/:contentType` (Asset hierarchy & registers)

Flat lists for Staff, Vehicles, Equipment, Consumables and WPS, generated from configuration.

- **layout**: DataTable with filters and a detail drawer.
- **sections**:
  - Config-driven columns
  - Used in column
  - Expiry indicators
  - Filters and saved views
- **actions**:
  - Add
  - Edit
  - Used-in lookup
  - Import
  - Export
- **access**: Per content type view and edit permissions.

#### Import and export `/assets/import` (Asset hierarchy & registers)

Async import with preview, conflict detection and rollback.

- **layout**: Stepper: upload, map, preview, commit, then batch history.
- **sections**:
  - Upload and template mapping
  - Validation preview with duplicates and tag conflicts
  - Commit progress
  - Batch history and rollback
  - Export options
- **actions**:
  - Map columns
  - Commit
  - Roll back batch
  - Export Excel/CSV/JSON
- **access**: asset.import; export needs asset.export.

#### Label sheet generation `/assets/labels` (Asset hierarchy & registers)

Bulk QR/RFID labels from the tree.

- **layout**: Split view with a selection tree and a label template preview.
- **sections**:
  - Subtree selection
  - Label template
  - Preview
  - Generated sheets
- **actions**:
  - Choose template
  - Generate PDF
  - Download
- **access**: asset.labels.

#### Asset settings `/admin/assets/settings` (Asset hierarchy & registers)

Tenant configuration for tags, scales and inspection schedules.

- **layout**: Sectioned settings form.
- **sections**:
  - Tag number format
  - Criticality and CUI corrosion scales
  - Status sets
  - RBI schedule per asset class
  - Import mapping templates
  - Label templates
  - Level terminology
- **actions**:
  - Edit
  - Save
  - Test tag format
- **access**: Tenant admin or asset admin.

#### Mobile scan and asset `/m/scan` (Asset hierarchy & registers)

Scan a QR/barcode/RFID tag to open an asset in the field.

- **layout**: Full-screen camera with a bottom sheet asset summary.
- **sections**:
  - Scanner
  - Asset summary
  - Quick actions
  - Offline indicator
- **actions**:
  - Scan
  - Open asset
  - Start inspection
  - Raise issue
  - Take photo
- **access**: Internal field users with assets in their synced scope.
