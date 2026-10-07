# Page specs for `scope_work`

#### RSW register `/scopes` (Scopes of work (RSW), disciplines & tasks)

Portfolio of scopes of work for the project.

- **layout**: DataTable with a KPI strip, tree scope chip and slide-over blade.
- **sections**:
  - KPI strip: active scopes, earned hours, QA/QC backlog, pending client review
  - Table: RSW no./rev, asset, location, priority, work order, CTR, WBS, progress, hours, mandated completion, status
  - Filters: priority, status, discipline, WBS
- **actions**:
  - Create RSW
  - Open
  - Change priority
  - Assign discipline lead
  - Update planned hours
  - Add delay reason
  - Export
- **access**: scope.view within project scope.

#### Create or edit RSW `/scopes/new` (Scopes of work (RSW), disciplines & tasks)

Capture scope details and commercial data.

- **layout**: Multi-section form.
- **sections**:
  - Number and revision
  - Asset picker
  - Location, corrosion environment
  - Observation and remedial works
  - Notification no.
  - Priority and mandated date
  - Commercial fields
- **actions**:
  - Save
  - Save and add disciplines
  - Cancel
- **access**: scope.create.

#### RSW detail `/scopes/:id` (Scopes of work (RSW), disciplines & tasks)

Run the scope through disciplines, tasks and the completion gate.

- **layout**: Header with progress and gate status, with tabs.
- **sections**:
  - Header: RSW no./rev, asset, priority, status, progress
  - Scope details
  - Disciplines and ordered tasks
  - Requirements and gate status
  - Linked ITPs, inspections, RFIs, hold points
  - Consumables issued
  - Commercial
  - Hours: planned, earned, actual, delay
  - Access and technique
  - Documents and procedures
  - Revision history
  - Activity
- **actions**:
  - Add discipline or task
  - Reorder tasks
  - Spawn ITP/RFI/inspection
  - Issue consumables
  - Log hours and delay
  - Complete RSW (gate-checked)
  - Create revision
- **access**: scope.view; edit and complete need scope.edit and scope.complete.

#### Scope portal WBS grid `/scopes/portal` (Scopes of work (RSW), disciplines & tasks)

Unified WBS grid with a slide-over blade for planners and supervisors.

- **layout**: Dense grid with a right-hand blade and split-view toggle.
- **sections**:
  - WBS grid
  - Slide-over blade
  - Inline hours editing in 0.5h steps
- **actions**:
  - Inline edit
  - Open blade
  - Group by WBS or priority
  - Export
- **access**: scope.view; edit by permission.

#### Cross-RSW task report `/scopes/tasks` (Scopes of work (RSW), disciplines & tasks)

Find tasks across RSWs, for example every task still needing an ITP.

- **layout**: Filterable report table with saved views.
- **sections**:
  - Filters: requirement type, state, discipline
  - Task table with RSW link
- **actions**:
  - Filter
  - Bulk create ITP
  - Save view
  - Export
- **access**: scope.view; reporting needs reporting.view.

#### RSW settings `/admin/scopes/settings` (Scopes of work (RSW), disciplines & tasks)

Configure vocabularies, gates and numbering.

- **layout**: Sectioned settings form.
- **sections**:
  - Priority definitions and target durations
  - Disciplines and task templates
  - Access methods and techniques
  - Delay reasons
  - Gate rules
  - Auto-create behaviour
  - Numbering and revision
  - Terminology
- **actions**:
  - Edit
  - Save
- **access**: Tenant admin or scope admin.

#### Mobile my scopes `/m/scopes` (Scopes of work (RSW), disciplines & tasks)

Field view of assigned RSWs and tasks.

- **layout**: Card list with a task checklist and offline badge.
- **sections**:
  - My RSWs
  - Task chain
  - Requirement status
  - Quick hours and delay log
- **actions**:
  - Open task
  - Log hours
  - Log delay
  - Start inspection
  - Capture photo
- **access**: Assigned field users within synced scope.
