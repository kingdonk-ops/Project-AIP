# Page specs for `service`

#### Ticket Queue `/service/tickets` (Service & maintenance)

Triage tickets with SLA countdowns

- **layout**: Register table with SLA countdown column, saved view tabs and filter bar
- **sections**:
  - Saved view tabs
  - Ticket table with priority and SLA clock
  - Quick-create drawer
- **actions**:
  - Create ticket
  - Assign
  - Pause/resume SLA with reason
  - Convert to work order
- **access**: service.view; manage with service.manage

#### Ticket Detail `/service/tickets/:ticketId` (Service & maintenance)

Ticket context, SLA clock and pause history

- **layout**: Header with clock, two-column body
- **sections**:
  - Asset and contact
  - SLA clock and pause intervals
  - Linked work orders
  - Activity
- **actions**:
  - Pause/resume with reason
  - Escalate
  - Close
- **access**: service.view; edit with service.manage

#### Work Order Register `/service/work-orders` (Service & maintenance)

List work orders by source, status and asset subtree

- **layout**: Register with subtree filter and source facets
- **sections**:
  - Filters
  - Table
  - Bulk actions
- **actions**:
  - Create
  - Filter
  - Export
- **access**: service.view

#### Work Order Detail `/service/work-orders/:woId` (Service & maintenance)

Execute and sign off work with tasks, labour, materials and forms

- **layout**: Tabbed detail: Overview, Tasks, Labour and Materials, Forms, Sign-off
- **sections**:
  - Source finding with photos and recommended repair
  - Task list
  - Labour and materials
  - Embedded form completion
  - Technician assignment with eligibility check
  - Sign-off
- **actions**:
  - Assign eligible technician
  - Complete form
  - Add labour/material
  - Sign off
- **access**: service.view; execute for assigned technicians; sign-off with service.signoff

#### PM Calendar `/service/pm` (Service & maintenance)

Plan preventive and recurring inspections by asset subtree

- **layout**: Calendar (month/week) with asset tree filter on left
- **sections**:
  - Asset subtree selector
  - Calendar of due items
  - Schedule list view
  - Interval rules panel
- **actions**:
  - Create schedule
  - Reschedule
  - Generate inspection/WO
- **access**: service.view; edit with service.plan

#### Campaign Template Designer `/service/campaigns/templates/:id` (Service & maintenance)

Define stages, gates and ITP binding

- **layout**: Ordered stage builder with property panel
- **sections**:
  - Stage list (strip, inspect, repair, reinsulate, recoat)
  - Gate rules
  - ITP binding
  - Terminology labels
- **actions**:
  - Add/reorder stage
  - Bind ITP
  - Publish
- **access**: service.configure

#### Campaign Progress `/service/campaigns/:campaignId` (Service & maintenance)

Track campaign stage progress per asset

- **layout**: Matrix of assets by stage with status cells
- **sections**:
  - Stage matrix
  - Gate status
  - Blockers
- **actions**:
  - Advance stage
  - Open ITP
  - Raise WO
- **access**: service.view

#### Asset History Timeline `/assets/:assetId/history` (Service & maintenance)

Merged construction, handover baseline, inspection and work order history

- **layout**: Vertical timeline with module filters and baseline pinned
- **sections**:
  - Baseline card
  - Timeline events
  - Filters
- **actions**:
  - Filter
  - Open source record
  - Export
- **access**: Asset view permission within scope

#### Service Contracts and SLA Setup `/service/contracts` (Service & maintenance)

Manage contracts, scope and SLA targets, pause reasons and thresholds

- **layout**: Register plus form with SLA target table
- **sections**:
  - Contract list
  - Terms and scope
  - SLA targets
  - Pause reason list
  - Auto-WO severity threshold
- **actions**:
  - Create/edit contract
  - Set SLA
  - Configure thresholds
- **access**: service.configure

#### Mobile Work Order `/m/service/work-orders/:woId` (Service & maintenance)

Field execution of work orders

- **layout**: Single-column stepper with sticky footer
- **sections**:
  - Tasks
  - Photos
  - Form
  - Sign-off
- **actions**:
  - Complete task
  - Capture photo
  - Submit
- **access**: Assigned technicians; offline support pending open decision
