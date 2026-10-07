# Page specs for `offline`

#### Today (mobile) `/m/today` (Offline field app & sync)

Start-of-shift view of assigned work, due items and sync health.

- **layout**: Mobile bottom-tab shell; header with sync chip; stacked cards.
- **sections**:
  - Assigned inspections and tasks
  - Scheduled bookings and hold points today
  - Eligibility warnings (expiring tickets or calibrations)
  - Last-used assets
  - Unsynced data warning
- **actions**:
  - Open item
  - Scan QR/NFC
  - Force sync
  - Open last-used asset
- **access**: Authenticated field users, inspectors, supervisors (own assigned scope)

#### Capture (mobile) `/m/capture` (Offline field app & sync)

Fast capture of photo, voice, form or defect against an asset.

- **layout**: Large central Capture button with four tiles; asset context bar at top.
- **sections**:
  - Asset context (default last-used)
  - Photo capture with markup
  - Voice note recorder
  - Start form/inspection
  - Raise defect
- **actions**:
  - Take photo
  - Mark up photo
  - Record voice
  - Start form
  - Raise defect
  - Change asset
  - Scan QR/NFC
- **access**: Field users with capture permission on the project/asset subtree

#### Inspections (mobile) `/m/inspections` (Offline field app & sync)

List and run offline-available inspections.

- **layout**: Filterable card list with per-item sync state; drill into full-screen runner.
- **sections**:
  - Filters (state, asset, project)
  - Inspection cards with sync badge
  - Download-for-offline status
- **actions**:
  - Open
  - Continue draft
  - Discard draft
  - Submit for review
- **access**: Assigned inspectors; supervisors for their team

#### Inspection runner (mobile) `/m/inspections/:id` (Offline field app & sync)

Fill a pinned template revision offline with autosave.

- **layout**: Single-column stepper with sticky progress and eligibility banner.
- **sections**:
  - Eligibility banner
  - Sections and fields
  - Photo/measurement inputs
  - ITP step list
  - Signature capture
  - Autosave indicator
- **actions**:
  - Answer fields (append-only)
  - Attach media
  - Sign
  - Submit
  - Raise issue
- **access**: Assignee with required competency; eligibility checks apply

#### Sync (mobile) `/m/sync` (Offline field app & sync)

Show queue, cursors, conflicts and media uploads; let user control sync.

- **layout**: Tabbed screen: Queue, Conflicts, Media, Log.
- **sections**:
  - Sync status summary
  - Outbox with per-item state
  - Conflict list
  - Deferred media with progress
  - Storage and encryption status
- **actions**:
  - Sync now
  - Retry/retry all failed
  - View payload
  - Discard draft
  - Resolve conflict
  - Pause media on cellular
- **access**: Any registered device user (own device)

#### Merge screen (mobile) `/m/sync/conflicts/:id` (Offline field app & sync)

Field-level conflict resolution.

- **layout**: Side-by-side (stacked on phone) local vs server per field.
- **sections**:
  - Field diff
  - Author and timestamp of each version
  - Record context
- **actions**:
  - Keep mine
  - Keep server
  - Edit merged value
  - Save resolution
- **access**: Record owner or supervisor

#### Device unlock and PIN `/m/unlock` (Offline field app & sync)

Unlock encrypted local store; PIN sign-in for field users.

- **layout**: Minimal full-screen PIN pad.
- **sections**:
  - PIN entry
  - Offline session time remaining
  - Re-authenticate prompt
- **actions**:
  - Enter PIN
  - Biometric unlock
  - Re-authenticate online
- **access**: Registered device users

#### Offline & sync settings `/settings/offline` (Offline field app & sync)

Tenant-level sync policy.

- **layout**: Settings form with grouped cards.
- **sections**:
  - Sync scope rules
  - Page/batch limits and interval
  - Conflict rules per record type
  - Media limits and network rules
  - Encryption, PIN and session policy
  - Stale-data threshold
- **actions**:
  - Edit
  - Save
  - Reset to defaults
- **access**: Tenant admin

#### Device register `/admin/devices` (Offline field app & sync)

Manage registered devices.

- **layout**: Data table with right-hand detail drawer.
- **sections**:
  - Filters (user, platform, last sync, status)
  - Device table
  - Detail drawer: device summary, scope, outbox, cursor, conflicts, media, sync log, security
- **actions**:
  - Approve registration
  - Revoke
  - Remote wipe
  - Export log
  - Change scope
- **access**: Tenant admin; security admin; supervisors read-only for their team
