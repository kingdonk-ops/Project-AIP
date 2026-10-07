# Page specs for `commissioning`

#### Systems register `/projects/:projectId/commissioning` (Commissioning)

List commissioning systems with readiness, checklist status, open issues and blocking NCRs.

- **layout**: Split view with a system tree and readiness rings on the left and a table on the right. A toggle switches to table only.
- **sections**:
  - Filters (status, readiness range, blocking items, discipline)
  - System tree with readiness rings
  - Systems table
  - Bulk action bar
- **actions**:
  - Create system
  - Open
  - Run checklists
  - Log issue
  - Request commission
  - Apply checklist templates
  - Assign owner
  - Export
- **access**: commissioning.view. Create and edit need commissioning.manage.

#### Create or edit system `/projects/:projectId/commissioning/systems/new` (Commissioning)

Group asset nodes into a system and assign checklists and a lead.

- **layout**: Form with an asset tree picker beside it.
- **sections**:
  - System no. and name
  - Asset nodes (asset tree picker)
  - Parent system
  - Responsible lead
  - Checklist templates
- **actions**:
  - Save
  - Save and generate checklists
  - Cancel
- **access**: commissioning.manage

#### System detail `/projects/:projectId/commissioning/systems/:systemId` (Commissioning)

Manage one system's checklists, issues, gate requirements and commission action.

- **layout**: Header with the readiness ring and status. Tabs sit below with the gate panel pinned on the right.
- **sections**:
  - System summary and readiness ring
  - Asset nodes and subsystems
  - Checklists (pre-functional and functional)
  - Issue log
  - Gate requirements and outstanding items
  - Linked documents and certificates
  - Sign-offs
  - Commission action and history
  - Activity
- **actions**:
  - Open checklist
  - Assign checklist
  - Log issue
  - Request sign-off
  - Request commission
  - Commission system
  - View gate failures
- **access**: commissioning.view. Commission action is limited to credentialled sign-off roles. The gate is enforced server-side.

#### Checklists `/projects/:projectId/commissioning/checklists` (Commissioning)

Track checklist execution across systems.

- **layout**: DataTable with filters.
- **sections**:
  - Filters (system, phase, assignee, result)
  - Table (system, checklist, phase, assignee, progress, result, completed date)
- **actions**:
  - Assign
  - Open checklist
  - Export
- **access**: commissioning.view. Run needs inspection.execute.

#### Commissioning issue log `/projects/:projectId/commissioning/issues` (Commissioning)

Show issues raised against systems, including blocking ones.

- **layout**: Table with board toggle.
- **sections**:
  - Filters (system, severity, blocking, status)
  - Issues table
  - Board view
- **actions**:
  - Log issue
  - Open issue
  - Assign
  - Close
  - Export
- **access**: commissioning.view. Close follows the issues module rules.

#### Commission gate `/projects/:projectId/commissioning/gate/:systemId` (Commissioning)

Show exactly what stops a system from being commissioned and who must act.

- **layout**: Checklist-style page with pass and fail rows and links to the blocking items.
- **sections**:
  - Gate rule results
  - Outstanding checks
  - Open blocking NCRs and issues
  - Missing sign-offs and competency problems
  - Gate history
- **actions**:
  - Open blocker
  - Request sign-off
  - Recheck gate
  - Commission when clear
- **access**: commissioning.view. Commission needs commissioning.commission.

#### Commissioning settings `/settings/commissioning` (Commissioning)

Configure templates per phase, readiness weighting, gate rules and sign-off roles.

- **layout**: Settings page with sections.
- **sections**:
  - Checklist templates per phase
  - Readiness weighting
  - Gate rule set
  - Required sign-off roles and competencies
  - Issue severities
  - System numbering
  - Handover status mapping
- **actions**:
  - Edit and save
  - Preview readiness on a system
- **access**: Tenant admin or commissioning.settings.manage

#### Mobile checklist execution `/m/commissioning/systems/:systemId` (Commissioning)

Run pre-functional and functional checks in the field, offline-capable.

- **layout**: Mobile single-column list of checklists with a progress header and a bottom bar.
- **sections**:
  - System header with readiness
  - Checklist list
  - Check items with result and photo
  - Quick log issue
- **actions**:
  - Run checklist
  - Capture photo
  - Log issue
  - Submit checklist
- **access**: Assigned inspectors with the required competencies
