# Page specs for `inventory`

#### Stock levels `/inventory` (Stock, consumables & materials)

Show live stock per item and location.

- **layout**: DataTable with location and status filters and a drawer.
- **sections**:
  - Filters (location, status, below reorder, use-by within, item type, project)
  - Stock table (item, unit, location, on hand, reserved, reorder point, batch count, earliest use-by, status, reminder state)
  - Below-reorder banner
- **actions**:
  - Add stock item
  - Receive
  - Issue
  - Transfer
  - Record waste
  - Adjust
  - Create requisition
  - Start count
  - Export
- **access**: inventory.view; movements need inventory.post.

#### Add stock item `/inventory/new` (Stock, consumables & materials)

Create a stock item from a consumable or material.

- **layout**: Form.
- **sections**:
  - Item picker
  - Unit and location
  - Reorder point
  - Use-by tracking
  - Opening quantity
- **actions**:
  - Save
  - Cancel
- **access**: inventory.manage.

#### Stock item detail `/inventory/items/:id` (Stock, consumables & materials)

See stock, batches and traceability for one item.

- **layout**: Header with on-hand summary and tabbed body.
- **sections**:
  - Item summary and unit
  - Stock by location
  - Batches with use-by and certificates
  - Movement history
  - Task issuances and application records
  - Traceability links
  - Reorder and requisitions
  - Use-by reminder status
  - Activity and audit
- **actions**:
  - Receive
  - Issue
  - Transfer
  - Waste
  - Adjust
  - Reverse movement
  - Open batch certificate
- **access**: inventory.view; reversal needs inventory.correct.

#### Movement ledger `/inventory/movements` (Stock, consumables & materials)

Append-only record of all movements.

- **layout**: DataTable with date range and type filters.
- **sections**:
  - Filters
  - Movements table (time, type, item, batch, quantity, from, to, task or asset, user, reference)
- **actions**:
  - Export
  - Open reference
  - Reverse (creates reversing entry)
- **access**: inventory.view.

#### Post movement `/inventory/movements/new` (Stock, consumables & materials)

Record a receipt, issue, transfer or waste.

- **layout**: Form or modal with scan support.
- **sections**:
  - Movement type
  - Item, batch, quantity, unit
  - From and to location
  - Task or asset reference
  - Reason code
  - Negative-stock warning
- **actions**:
  - Post
  - Cancel
- **access**: inventory.post; issue to task requires task access.

#### Reconciliation counts `/inventory/counts` (Stock, consumables & materials)

Run counts and approve variances.

- **layout**: List of sessions with a count sheet and variance view.
- **sections**:
  - Count sessions
  - Count sheet
  - Variance report vs tolerance
- **actions**:
  - Start count
  - Enter counts
  - Approve adjustments
  - Export variance
- **access**: inventory.count; approval needs inventory.correct.

#### Batches and use-by `/inventory/batches` (Stock, consumables & materials)

Track batch and heat numbers, expiry and certificates.

- **layout**: DataTable with an expiry timeline filter.
- **sections**:
  - Batch table (batch, heat, item, certificate, use-by, quantity, status)
  - Expiring and expired tabs
- **actions**:
  - Open batch
  - Link certificate
  - Mark unavailable
  - Export
- **access**: inventory.view.

#### Inventory settings `/inventory/settings` (Stock, consumables & materials)

Configure units, rules and locations.

- **layout**: Tabbed settings.
- **sections**:
  - Units and conversions
  - Reorder rules
  - Use-by lead times
  - Negative stock policy
  - Variance tolerance
  - Required certificate on receipt
  - Locations
  - Correction permissions
  - Terminology keys
- **actions**:
  - Save
  - Add location
- **access**: inventory.configure.

#### Mobile stock `/m/inventory` (Stock, consumables & materials)

Issue, receive and count in the field.

- **layout**: Mobile scan-first screens with offline queue.
- **sections**:
  - Scan bar
  - Quick issue to task
  - Receive from docket
  - Count sheet
- **actions**:
  - Scan
  - Issue
  - Receive
  - Record waste
  - Count
- **access**: Storepersons and field users with inventory.post.
