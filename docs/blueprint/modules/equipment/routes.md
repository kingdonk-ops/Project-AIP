# Page specs for `equipment`

#### Equipment register `/equipment` (Equipment & fleet)

List plant, vehicles and instruments with eligibility state.

- **layout**: DataTable with a type tab strip and a detail drawer.
- **sections**:
  - Tabs (all, plant, vehicle, instrument)
  - Filters (type, project, status, calibration, ownership)
  - Register table (ID, name, type, make/model, serial, ownership, project, status, calibration due, next service, eligibility)
  - Bulk action bar
- **actions**:
  - Add equipment
  - Open
  - Assign to project
  - Change status
  - Schedule maintenance
  - Request calibration
  - Export register
- **access**: equipment.view; edit needs equipment.manage.

#### Add equipment `/equipment/new` (Equipment & fleet)

Register new equipment.

- **layout**: Form driven by the content-type definition.
- **sections**:
  - Type and identity
  - Ownership and hire details
  - Calibration requirement and interval
  - Hire charge rate
  - Linked asset (optional)
- **actions**:
  - Save
  - Save and add calibration certificate
  - Cancel
- **access**: equipment.manage.

#### Equipment detail `/equipment/:id` (Equipment & fleet)

Full record with calibration, service and usage.

- **layout**: Header with eligibility badge and tabbed body.
- **sections**:
  - Identity and ownership
  - Current status and project
  - Calibration certificates and validity
  - Eligibility gate status
  - Maintenance schedule and service history
  - Pre-start and inspection history
  - Usage on inspections
  - Hire and charge history
  - Linked asset
  - Documents
  - Activity and audit
- **actions**:
  - Edit
  - Upload calibration certificate
  - Transfer to project
  - Run pre-start
  - Schedule service
  - Mark out of service
  - Create work order
- **access**: equipment.view; actions per permission.

#### Edit equipment `/equipment/:id/edit` (Equipment & fleet)

Change details and settings.

- **layout**: Same form as create with change-reason field.
- **sections**:
  - Identity
  - Ownership and hire
  - Calibration settings
  - Linked asset
- **actions**:
  - Save
  - Cancel
- **access**: equipment.manage.

#### Maintenance calendar `/equipment/maintenance` (Equipment & fleet)

See services and calibrations due.

- **layout**: Calendar with a list toggle.
- **sections**:
  - Calendar of due and overdue items
  - Filters by type and project
  - Overdue list
- **actions**:
  - Schedule service
  - Record service
  - Reschedule
- **access**: equipment.view; schedule needs equipment.maintain.

#### Pre-start checks `/equipment/prestarts` (Equipment & fleet)

Review pre-start submissions and failures.

- **layout**: DataTable with status filters.
- **sections**:
  - Submissions table
  - Failed checks tab
  - Template mapping
- **actions**:
  - Open submission
  - Run pre-start
  - Raise task or NCR
  - Clear failure
- **access**: equipment.view; clearing needs equipment.maintain.

#### Hire charge statement `/equipment/charges` (Equipment & fleet)

Review internal hire charges by project.

- **layout**: Summary cards over a charges table.
- **sections**:
  - Period selector
  - Charges by project
  - Charge lines (days, rate, total)
- **actions**:
  - Generate charges
  - Adjust line
  - Export statement
- **access**: equipment.charges with commercial permission.

#### Equipment settings `/equipment/settings` (Equipment & fleet)

Configure types, calibration enforcement and rates.

- **layout**: Tabbed settings.
- **sections**:
  - Types and attributes
  - Calibration lead times and enforcement mode
  - Pre-start template mapping
  - Maintenance defaults
  - Hire rate cards
  - Terminology keys
- **actions**:
  - Save
  - Edit rate card
- **access**: equipment.configure.

#### Mobile equipment `/m/equipment` (Equipment & fleet)

Scan, pre-start and check calibration in the field.

- **layout**: Mobile list with QR or barcode scan, large status chips, and offline-ready pre-start forms.
- **sections**:
  - Scan bar
  - My equipment
  - Calibration status card
  - Pre-start form
- **actions**:
  - Scan
  - Run pre-start
  - Report defect
  - View calibration
- **access**: Field users with equipment.view and equipment.prestart.
