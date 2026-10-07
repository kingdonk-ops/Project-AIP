# Page specs for `meetings`

#### Meeting list and planner `/meetings` (Meetings & AI minutes)

Plan and find meetings, including recurring series.

- **layout**: List with a calendar toggle and filters.
- **sections**:
  - Upcoming and past meetings
  - Series
  - Filters by type, project and package
- **actions**:
  - Create meeting
  - Create series
  - Use agenda template
  - Open
- **access**: meetings.view; create needs meetings.create

#### Meeting detail `/meetings/:id` (Meetings & AI minutes)

Manage agenda, attendees, recording, minutes and actions in one place.

- **layout**: Tabbed page with a status header and WorkflowBar.
- **sections**:
  - Agenda items with linked RFIs, interfaces and NCRs
  - Attendees, apologies and consent state
  - Recording and upload
  - AI-drafted minutes
  - Decisions
  - Actions and carried-forward items
  - Distribution and acknowledgement
- **actions**:
  - Add agenda item
  - Pull open items
  - Record or upload audio
  - Request draft
  - Publish minutes
  - Create tasks from actions
- **access**: Attendees can read; chair and secretary edit; recording needs tenant opt-in

#### Live capture `/meetings/:id/capture` (Meetings & AI minutes)

Record audio and take quick notes during the meeting, including offline.

- **layout**: Full-screen mobile-first view with a consent gate, a large record control and a notes pane.
- **sections**:
  - Consent notice and per-attendee state
  - Recorder with level meter
  - Quick notes tied to agenda items
  - Upload status
- **actions**:
  - Record
  - Pause
  - Stop
  - Dictate
  - Tag agenda item
- **access**: Chair or secretary; blocked or paused if an attendee declines consent

#### Minutes review editor `/meetings/:id/minutes/review` (Meetings & AI minutes)

Let the chair verify the AI draft against the transcript before publishing.

- **layout**: Split view: transcript with highlights on one side, editable minutes with suggested decisions and actions on the other.
- **sections**:
  - Transcript with audio playback
  - Suggested decisions and actions with source highlights
  - Asset, NCR and RFI link suggestions
  - AI-draft banner
- **actions**:
  - Accept or edit item
  - Play source segment
  - Link asset
  - Correct attendee contribution
  - Publish and sign
- **access**: Chair and delegate; nothing is published without confirmation

#### Toolbox-talk sign-on `/meetings/toolbox/:id` (Meetings & AI minutes)

Quick attendance sign-on by PIN or QR, offline-capable.

- **layout**: Kiosk-style mobile screen with a QR display and a PIN pad, then a signed attendance summary.
- **sections**:
  - Talk summary
  - Sign-on entry
  - Attendee list
- **actions**:
  - Sign on
  - Add non-user attendee
  - Close and sign record
- **access**: Presenter; attendees via scoped PIN or QR credentials limited to this meeting

#### Meeting settings `/admin/meetings` (Meetings & AI minutes)

Configure agenda templates, vocabulary hints, retention and provider.

- **layout**: Settings tabs.
- **sections**:
  - Recording opt-in
  - Provider and region
  - Agenda templates
  - Vocabulary hints per project
  - Audio retention and legal hold
- **actions**:
  - Enable or disable recording
  - Edit templates
  - Edit hints
  - Set retention
- **access**: Tenant admin and AI governance owner
