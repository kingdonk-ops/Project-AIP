# Page specs for `logistics`

#### Mobilisation plan `/projects/:projectId/mobilisation` (Site logistics & mobilisation)

Show readiness against target start and what blocks it.

- **layout**: Dashboard header with a readiness ring and a blockers panel above grouped checklists.
- **sections**:
  - Header (project, target start, readiness %)
  - Blockers roll-up
  - Readiness items by area
  - Template applied
  - Eligibility checks (inductions, permits)
- **actions**:
  - Add item
  - Apply template
  - Mark ready with evidence
  - Assign owner
  - Change due date
  - Export checklist
  - Edit target start
- **access**: logistics.view; edit needs logistics.manage; owners update their own items.

#### Readiness item detail `/projects/:projectId/mobilisation/items/:itemId` (Site logistics & mobilisation)

Manage one item, its evidence and linked credential requirement.

- **layout**: Two-column detail page.
- **sections**:
  - Item summary and status
  - Blocks start flag
  - Linked permit or induction
  - Evidence files
  - Activity
- **actions**:
  - Mark ready
  - Attach evidence
  - Reassign
  - Delete
- **access**: Item owner or logistics.manage.

#### Delivery booking board `/projects/:projectId/logistics/bookings` (Site logistics & mobilisation)

Schedule and manage deliveries by gate and slot.

- **layout**: Calendar and board toggle with gate lanes and a pending-requests rail.
- **sections**:
  - Day or week calendar by gate
  - Slot capacity indicators
  - Status board (requested, approved, arrived, received, rejected)
  - Pending requests
- **actions**:
  - New booking
  - Approve
  - Reschedule
  - Reject
  - Mark arrived
  - Create goods receipt
  - Export
- **access**: logistics.view; approve needs logistics.approve_booking; gate security gets a read and arrive-only view.

#### Create booking `/projects/:projectId/logistics/bookings/new` (Site logistics & mobilisation)

Book a delivery against a PO.

- **layout**: Form with live slot availability.
- **sections**:
  - Supplier, PO and PO lines
  - Vehicle and driver
  - Gate, date and slot
  - Materials and expected docket
  - Required documents on arrival
- **actions**:
  - Submit
  - Save draft
  - Cancel
- **access**: logistics.manage, or suppliers through the restricted link.

#### Booking detail `/projects/:projectId/logistics/bookings/:id` (Site logistics & mobilisation)

Track a delivery through arrival and receipt.

- **layout**: Header with state bar and a tabbed body.
- **sections**:
  - Booking summary
  - PO lines and docket
  - Arrival and checks (certificates, docket)
  - Goods receipt and stock link
  - Activity
- **actions**:
  - Approve
  - Reschedule
  - Reject
  - Record arrival
  - Receive goods
  - Flag missing certificate
- **access**: logistics.view; actions per permission.

#### Gates and hours `/projects/:projectId/logistics/gates` (Site logistics & mobilisation)

Configure gates, opening hours and slot capacity.

- **layout**: List with a weekly hours editor.
- **sections**:
  - Gate list
  - Weekly hours grid
  - Holiday exceptions
  - Slot length and capacity
  - Notification recipients
- **actions**:
  - Add gate
  - Edit hours
  - Add exception
  - Deactivate
- **access**: logistics.configure.

#### Laydown zones `/projects/:projectId/logistics/laydown` (Site logistics & mobilisation)

See zones, capacity and contents on a site plan.

- **layout**: Map or plan canvas with a zone list side panel.
- **sections**:
  - Site plan with zone polygons
  - Zone list (capacity, utilisation, linked area or asset)
  - Zone contents
- **actions**:
  - Add zone
  - Edit zone
  - Assign delivery to zone
  - Switch to list
- **access**: logistics.view; edit needs logistics.manage.

#### Logistics settings `/projects/:projectId/logistics/settings` (Site logistics & mobilisation)

Templates, areas, booking rules and goods-receipt behaviour.

- **layout**: Tabbed settings.
- **sections**:
  - Mobilisation templates
  - Readiness areas and item types
  - Booking lead time and cancellation
  - Supplier link settings
  - Required documents
  - Auto goods receipt
  - Terminology keys
- **actions**:
  - Save
  - Import template
- **access**: logistics.configure.

#### Supplier booking portal `/supplier/bookings` (Site logistics & mobilisation)

Let suppliers request and track slots without commercial data.

- **layout**: Minimal portal page on the separate portal origin.
- **sections**:
  - My bookings
  - Request slot form
  - Slot availability
  - Required documents
- **actions**:
  - Request booking
  - Amend request
  - Cancel within window
  - Upload docket
- **access**: Supplier portal users or magic-link principals scoped to named POs.

#### Mobile gate check-in `/m/logistics/gate` (Site logistics & mobilisation)

Record arrivals at the gate.

- **layout**: Mobile list of today's expected deliveries with a large arrive button.
- **sections**:
  - Today's bookings
  - Docket and certificate checklist
  - Photo capture
- **actions**:
  - Mark arrived
  - Flag missing document
  - Reject at gate
- **access**: Gate and security roles with logistics.arrive.
