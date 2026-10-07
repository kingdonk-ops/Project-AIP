# Page specs for `schedule`

#### Calendar `/schedule` (Schedule & look-ahead (basic))

Month, week and agenda view of inspections due, scope mandated dates, certificate expiries and commitments.

- **layout**: Full-width calendar with a left filter rail (project, asset subtree, discipline, crew, type, status, overdue only) and a top toolbar for view switch, today and iCal. Item click opens a right drawer.
- **sections**:
  - Filter rail
  - Calendar grid or agenda list
  - Type colour legend
  - Item summary drawer (source link, asset, crew, reminders)
  - Overdue banner
- **actions**:
  - Switch view
  - Filter
  - Open source record
  - Reschedule where source allows
  - Set reminder
  - Assign crew
  - Export to iCal
- **access**: schedule.view; items limited by the viewer's project, asset-subtree and source-module permissions

#### Look-ahead `/schedule/lookahead` (Schedule & look-ahead (basic))

Two- to six-week list of upcoming items grouped by week and crew.

- **layout**: Window selector (2-6 weeks) above a week-column board or table toggle, with bulk action bar on selection.
- **sections**:
  - Window and filter bar
  - Weekly columns or Look-ahead items table (date, type, title, asset, scope, crew, status, overdue flag)
  - Bulk action bar
  - Empty state with guidance
- **actions**:
  - Add to weekly plan
  - Assign crew
  - Set reminder
  - Export selected to iCal
  - Create ad hoc item
  - Roll forward
- **access**: schedule.view to see; schedule.plan to assign, add to plan or create items

#### Create or edit schedule item `/schedule/items/new` (Schedule & look-ahead (basic))

Add a manual dated item (title, date, asset, scope, notes) or edit one.

- **layout**: Modal or side sheet form.
- **sections**:
  - Title and date
  - Asset picker
  - Scope picker
  - Notes
- **actions**:
  - Save
  - Cancel
  - Delete (manual items only)
- **access**: schedule.plan

#### Schedule item detail `/schedule/items/:id` (Schedule & look-ahead (basic))

Show one calendar entry with its source record, crew, reminders and commitment history.

- **layout**: Single column detail with a right-hand activity panel.
- **sections**:
  - Summary and dates
  - Source record link
  - Asset and location
  - Assigned crew and people
  - Reminders
  - Commitment history and reasons not done
  - Activity
- **actions**:
  - Open source
  - Add commitment
  - Assign crew
  - Set reminder
  - Reschedule
- **access**: schedule.view; edit actions need schedule.plan

#### Weekly work plan `/schedule/weekly-plan` (Schedule & look-ahead (basic))

Optional weekly commitments per crew with tick-off and reason when not done.

- **layout**: Week picker header, commitments table grouped by crew, completion summary strip.
- **sections**:
  - Week selector and publish status
  - Commitments table (task/scope, asset, crew, committed by, done, reason not done)
  - Reason-code dialog
  - Completion summary
- **actions**:
  - Add commitment
  - Mark done
  - Record reason not done
  - Roll forward to next week
  - Remove commitment
  - Publish plan
- **access**: schedule.plan; read-only for schedule.view; hidden if commitments disabled for the project

#### Mobile today and this week `/schedule/mobile` (Schedule & look-ahead (basic))

Field view of the user's own and crew items for today and the week.

- **layout**: Mobile single column agenda with day chips, cached offline, large tap targets.
- **sections**:
  - Day selector
  - Agenda cards (type icon, asset, due state)
  - Commitment tick-off
  - Offline sync indicator
- **actions**:
  - Open item
  - Tick commitment done
  - Pick reason not done
  - Set reminder
- **access**: schedule.view; tick-off needs schedule.plan or crew membership

#### Schedule settings `/settings/schedule` (Schedule & look-ahead (basic))

Configure look-ahead, sources, reminders, reason codes and iCal feed.

- **layout**: Tabbed settings form.
- **sections**:
  - Default look-ahead length
  - Item sources and colours
  - Reminder lead times per type
  - Weekly plan on/off per project
  - Reason-code list
  - Working days and week start
  - iCal feed and token rotation
  - Terminology labels
- **actions**:
  - Save
  - Rotate iCal token
  - Reset to defaults
  - Edit labels
- **access**: Tenant or project admin with schedule.export and settings permission
