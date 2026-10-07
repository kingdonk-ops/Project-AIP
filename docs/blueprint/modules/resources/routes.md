# Page specs for `resources`

#### Resource register `/resources` (Resources & crews (basic))

List people and crews with skills and credential status.

- **layout**: DataTable with filters and a detail drawer.
- **sections**:
  - Filters (type, company, skill, credential status, project, availability)
  - Register table (name, type, company, role, skills, credential status, home project, availability today, next 7 days)
- **actions**:
  - Add resource
  - Open
  - Assign
  - Set availability
  - View credentials
  - Import from staff register
  - Export
- **access**: resources.view; edit needs resources.manage. Rates are visible only with resources.rates.

#### Add resource `/resources/new` (Resources & crews (basic))

Create a person or crew.

- **layout**: Form.
- **sections**:
  - Type
  - User or name
  - Company and role
  - Skills from competency register
  - Crew members
  - Optional rate
- **actions**:
  - Save
  - Cancel
- **access**: resources.manage.

#### Resource detail `/resources/:id` (Resources & crews (basic))

Profile, credentials and assignments.

- **layout**: Header with credential badge and tabbed body.
- **sections**:
  - Profile and company
  - Skills
  - Credentials and expiry
  - Crew membership
  - Assignments calendar
  - Availability
  - Conflicts
  - Activity and audit
- **actions**:
  - Edit
  - Assign
  - Set availability
  - Add to crew
  - Open credential
- **access**: resources.view; people can see their own.

#### Crew detail `/resources/crews/:id` (Resources & crews (basic))

Manage crew members and assignments.

- **layout**: Header with a member list and calendar.
- **sections**:
  - Crew summary
  - Members and roles
  - Combined credential status
  - Assignments
- **actions**:
  - Add member
  - Remove member
  - Assign crew
  - Edit
- **access**: resources.manage.

#### Assignment calendar `/resources/assignments` (Resources & crews (basic))

See who is assigned where and spot conflicts.

- **layout**: Resource-by-day grid with conflict flags and a filter bar.
- **sections**:
  - Resource rows by date
  - Conflict and skill-mismatch flags
  - Unassigned work rail
- **actions**:
  - Create assignment
  - Drag to move
  - Resolve conflict
  - Override expired credential with reason
  - Shift dates
- **access**: resources.view; assign needs resources.assign.

#### Create assignment `/resources/assignments/new` (Resources & crews (basic))

Assign a resource to an RSW, task or inspection.

- **layout**: Modal with a live skill-match panel.
- **sections**:
  - Resource picker
  - Target (RSW, task, inspection)
  - Dates and hours per day
  - Skill match and credential check
  - Conflict preview
- **actions**:
  - Assign
  - Assign with override
  - Cancel
- **access**: resources.assign.

#### Resource settings `/resources/settings` (Resources & crews (basic))

Configure types, skills and conflict rules.

- **layout**: Tabbed settings.
- **sections**:
  - Resource types and roles
  - Skill mapping
  - Warn or block on expired credentials
  - Double-booking threshold
  - Rate visibility
  - Roster patterns
  - Terminology keys
- **actions**:
  - Save
- **access**: resources.configure.

#### Mobile my assignments `/m/resources/my-week` (Resources & crews (basic))

Show a worker their upcoming work.

- **layout**: Mobile list by day.
- **sections**:
  - This week's assignments
  - Credential expiry warnings
  - Availability toggle
- **actions**:
  - Open assignment
  - Set unavailable
  - Acknowledge
- **access**: Any signed-in user, own data only.
