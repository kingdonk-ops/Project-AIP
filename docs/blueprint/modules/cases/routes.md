# Page specs for `cases`

#### Controlled procedures register `/p/:projectId/documents/procedures` (User-authored playbooks)

List controlled procedures with their current revision and acknowledgement status.

- **layout**: Standard document register table with a procedure type filter and status chips.
- **sections**:
  - Filters (type, discipline, status)
  - Procedure table (revision, owner, acknowledged %)
  - Overdue acknowledgement indicators
- **actions**:
  - Open procedure
  - Create procedure
  - Issue new revision
  - Export acknowledgement status
- **access**: Project members can view procedures in their scope; document controllers create and issue; approval before issue is configurable and not yet decided.

#### Procedure view `/p/:projectId/documents/procedures/:documentId` (User-authored playbooks)

Read the Markdown procedure with terminology tokens resolved and acknowledge the current revision.

- **layout**: Document reader with revision header and an acknowledgement bar fixed at the bottom.
- **sections**:
  - Revision header and history
  - Rendered Markdown content
  - Acknowledgement bar
  - Linked competency requirement
- **actions**:
  - Acknowledge current revision
  - Switch revision
  - Download PDF
  - Open edit (controllers)
- **access**: Users within project and team visibility; acknowledgement is by the signed-in person only.

#### Procedure editor `/p/:projectId/documents/procedures/:documentId/edit` (User-authored playbooks)

Write and revise a procedure in Markdown with terminology tokens.

- **layout**: Split Markdown editor and live preview, with a metadata panel.
- **sections**:
  - Markdown editor with token picker
  - Live preview using project terms
  - Metadata (type, audience, acknowledgement required)
  - Competency link settings
- **actions**:
  - Insert terminology token
  - Save draft
  - Submit for approval or issue
  - Cancel
- **access**: Document controllers and procedure owners.

#### Acknowledgement status `/p/:projectId/documents/procedures/:documentId/acknowledgements` (User-authored playbooks)

See who has and has not acknowledged the current revision.

- **layout**: Table with summary tiles and a filter by team.
- **sections**:
  - Summary (acknowledged, outstanding, overdue)
  - Person table with date and time
  - Team and company filter
  - Competency record link
- **actions**:
  - Filter
  - Export list
  - Send reminder
- **access**: Document controllers, QA managers, supervisors for their own team, and auditors (read-only).

#### Help guide mapping `/admin/help/guides` (User-authored playbooks)

Map screens to guides so the help button opens the right Markdown document.

- **layout**: Simple table with a screen picker and document selector.
- **sections**:
  - Screen key list
  - Mapped guide per screen
  - Missing mappings
- **actions**:
  - Map screen to guide
  - Remove mapping
  - Preview guide
- **access**: Tenant admin and document controllers.

#### Contextual help panel `(shell overlay) help button` (User-authored playbooks)

Open the relevant guide from any screen, including on mobile.

- **layout**: Right-side drawer on desktop, bottom sheet on mobile; cached for offline reading.
- **sections**:
  - Guide content with resolved terms
  - Link to the full procedure
  - Acknowledge prompt if required
- **actions**:
  - Open guide
  - Open full procedure
  - Acknowledge
  - Close
- **access**: All authenticated users, restricted to guides they can see.
