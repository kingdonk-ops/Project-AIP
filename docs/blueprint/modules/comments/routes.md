# Page specs for `comments`

#### Comment side panel `Embedded: CommentPanel` (Comments, mentions & notifications)

Threaded discussion on any record, file or viewer page.

- **layout**: Right-hand drawer, bottom sheet on mobile.
- **sections**:
  - Thread list with resolve filters
  - Composer with @mentions and visibility selector
  - Visibility badges
  - Edit history
- **actions**:
  - Comment
  - Mention
  - Resolve or reopen
  - Convert to task, issue or corrective action
  - Change visibility
  - View history
  - Carry forward to new file version
- **access**: Per parent record permission; external parties see only threads their visibility class allows

#### Mentions of me `/inbox/mentions` (Comments, mentions & notifications)

Show threads where the user was mentioned.

- **layout**: List with open and resolved filters and a thread preview.
- **sections**:
  - Mention list
  - Thread preview
- **actions**:
  - Open record
  - Reply
  - Resolve
  - Mark read
- **access**: Authenticated user

#### Pin and viewpoint capture `Embedded: viewer pin layer` (Comments, mentions & notifications)

Place comments on PDF pages and photos.

- **layout**: Overlay on the markup viewer with a pin list sidebar.
- **sections**:
  - Pins by page
  - Resolve filters
  - Viewpoint capture
- **actions**:
  - Add pin
  - Link asset or defect
  - Save viewpoint
  - Resolve
- **access**: Comment permission on the file

#### Asset discussion history `/assets/:id/discussion` (Comments, mentions & notifications)

Roll up comments from the asset subtree's inspections, NCRs and RFIs.

- **layout**: Tab on the asset node with a timeline thread view.
- **sections**:
  - Combined thread
  - Filters by source record, status and visibility
  - Subtree toggle
- **actions**:
  - Open source record
  - Comment
  - Filter
- **access**: Asset view permission; items filtered by visibility class

#### Notification inbox `/notifications` (Comments, mentions & notifications)

Notification centre with a bell in the header.

- **layout**: Bell dropdown plus a full-page list.
- **sections**:
  - Unread counts
  - Notification list
  - Snoozed and muted items
- **actions**:
  - Mark read
  - Snooze
  - Mute thread
  - Open record
- **access**: Authenticated user

#### Preference matrix `/settings/notifications` (Comments, mentions & notifications)

Set channel, digest and quiet hours per event type.

- **layout**: Matrix of event types by channel, with a quiet hours panel.
- **sections**:
  - Channel matrix
  - Digest frequency
  - Quiet hours
  - Mandatory notices (locked)
- **actions**:
  - Toggle channel
  - Set digest
  - Set quiet hours
- **access**: Each user for themselves

#### Templates, wording and rules `/admin/notifications` (Comments, mentions & notifications)

Manage message templates, tenant wording overrides and notification rules.

- **layout**: Tabs: Templates, Wording overrides, Rules, Escalation and shifts.
- **sections**:
  - Message keys with preview
  - Rule builder (asset subtree, discipline, severity, recipients)
  - Quiet hours and shift calendars
  - Mandatory notice list
- **actions**:
  - Edit wording
  - Create rule
  - Test rule
  - Enable or disable
- **access**: notifications.admin
