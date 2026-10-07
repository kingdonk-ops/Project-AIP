# Page specs for `tasks`

#### My Work `/my-work` (Tasks, deadlines & my work)

Single home queue of approvals awaiting me, inspections to sign, overdue items, mentions and expiring certificates.

- **layout**: Home page with a filter chip bar above a single prioritised list. A right rail holds the due-soon widget. On mobile it is a single column with swipe actions.
- **sections**:
  - Filter chips (All, Approvals, Sign, Overdue, Mentions, Expiries)
  - Queue list grouped by urgency
  - Due-soon widget (extends the existing dashboard Due soon)
  - Delegation banner when acting as a delegate
  - Offline/sync status
- **actions**:
  - Approve
  - Open source record
  - Sign
  - Acknowledge
  - Quick-add task
  - Snooze with reason
- **access**: Any signed-in user, showing only their own items and delegated items

#### My Tasks and Deadlines `/tasks` (Tasks, deadlines & my work)

Personal list of tasks and the deadlines I own.

- **layout**: Tabs for Tasks and Deadlines. DataTable with saved views and a side drawer for detail.
- **sections**:
  - Tabs
  - Filters (status, priority, due, asset, source module)
  - Task table
  - Deadline table
  - Task drawer with checklist, comments, attachments and source link
- **actions**:
  - Create task
  - Edit
  - Complete
  - Tick checklist item
  - Reassign
  - Acknowledge deadline
  - Extend with reason
  - Resolve
- **access**: Any signed-in user for their own records. Reassign requires the tasks.assign permission.

#### Create or Edit Task `/tasks/new` (Tasks, deadlines & my work)

Full task form, also used as a modal from quick-add.

- **layout**: Form page or modal using FormRenderer.
- **sections**:
  - Title and description
  - Assignee, due date and priority
  - Asset picker (tree)
  - Source record link
  - Checklist builder
  - Attachments
  - Recurrence option
- **actions**:
  - Save
  - Save and add another
  - Cancel
  - Attach photo
- **access**: Users with tasks.create. Personal to-dos are available to all users.

#### Project and Asset-Subtree Task Board `/projects/:projectId/tasks/board` (Tasks, deadlines & my work)

Kanban of tasks for a project or an asset subtree.

- **layout**: Left asset tree panel with a board of status columns (workflow states) on the right.
- **sections**:
  - Asset tree with subtree toggle
  - Board columns
  - Cards (assignee, due date, priority, overdue flag)
  - Filter bar
- **actions**:
  - Drag between statuses
  - Create in column
  - Open card
  - Filter by subtree
  - Bulk reassign
- **access**: Project members with tasks.view, scoped to their asset subtree

#### Team and Project Overdue Board `/projects/:projectId/overdue` (Tasks, deadlines & my work)

Manager view of overdue deadlines and tasks by team and escalation level.

- **layout**: Summary tiles above a grouped table.
- **sections**:
  - Count tiles by escalation level
  - Overdue table grouped by owner or team
  - Escalation log drawer
- **actions**:
  - Reassign
  - Extend with reason
  - Acknowledge
  - Resolve
  - Export
- **access**: Managers and supervisors with tasks.manage_team

#### Overdue and Ageing Analytics `/projects/:projectId/tasks/analytics` (Tasks, deadlines & my work)

Ageing analytics by source module, team and escalation level.

- **layout**: Dashboard with charts above a drill-down table.
- **sections**:
  - Filters (period, module, team)
  - Ageing buckets chart
  - Overdue by source module
  - Escalation level breakdown
  - Drill-down table
- **actions**:
  - Filter
  - Drill down
  - Export CSV or Excel
  - Save view
- **access**: Managers and reporting roles with tasks.analytics

#### Policy Admin `/settings/tasks/policies` (Tasks, deadlines & my work)

Configure grace periods and escalation per deadline type, and auto-task rules.

- **layout**: Settings page with tabs: Deadline policies, Auto-task rules, Recurring templates, Calendars.
- **sections**:
  - Policy table (type, grace, escalation manager rule)
  - Auto-task rule builder (event, conditions, task template)
  - Recurring template list (for example weekly CUI strip-and-inspect per area)
  - Project calendars, regional holidays and shutdown periods
  - Test rule panel
- **actions**:
  - Create or edit policy
  - Enable or disable rule
  - Create template
  - Add holiday or shutdown
  - Preview next occurrences
- **access**: Tenant or project admins with tasks.admin

#### Delegation Settings `/settings/delegation` (Tasks, deadlines & my work)

Set out-of-office routing for approvals and sign-offs.

- **layout**: Simple form plus a history table.
- **sections**:
  - Delegate picker
  - Date range
  - Scope (approvals, sign-offs)
  - Active and past delegations with audit record
- **actions**:
  - Create delegation
  - End early
  - View audit
- **access**: Any user for themselves. Admins can set on behalf of others.

#### Mobile Tasks (Offline) `/m/tasks` (Tasks, deadlines & my work)

Field capture and completion of tasks with queued sync.

- **layout**: Mobile PWA with a bottom tab bar, large touch targets and a persistent sync badge.
- **sections**:
  - Today list
  - Quick-add bar
  - Task detail with checklist
  - Photo capture
  - Queued actions list
- **actions**:
  - Add task
  - Complete
  - Tick checklist
  - Attach photo
  - Retry sync
- **access**: Any signed-in field user, limited to their assigned and project-scoped data
