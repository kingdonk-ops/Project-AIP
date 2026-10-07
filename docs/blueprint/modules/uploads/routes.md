# Page specs for `uploads`

#### Upload tray `/uploads (tray)` (Upload & file processing pipeline)

Global panel showing every upload with state and controls, including offline-queued files.

- **layout**: Docked panel on desktop, full-screen sheet on mobile; reachable from the app shell.
- **sections**:
  - Per-file rows with progress and scan chip
  - Priority and Wi-Fi-only rules
  - Recovery prompt after reconnecting
- **actions**:
  - Pause
  - Resume
  - Retry
  - Cancel
  - Reprioritise
- **access**: Any authenticated user for their own uploads; project permission checked per chunk

#### Mobile upload queue `/m/uploads` (Upload & file processing pipeline)

Manage deferred field uploads on a phone.

- **layout**: Single-column list with large touch targets and a storage and connection banner.
- **sections**:
  - Queued, uploading and failed groups
  - Connection and bandwidth status
- **actions**:
  - Upload now
  - Hold video for Wi-Fi
  - Retry
  - Remove
- **access**: Authenticated field users

#### File-type policy table `/admin/files/policies` (Upload & file processing pipeline)

Edit allowed types, size limits, scan depth and preview behaviour within platform limits.

- **layout**: Editable DataTable with platform limits shown inline.
- **sections**:
  - Policy rows
  - Platform limit indicators
  - EXIF GPS policy per project
- **actions**:
  - Add or edit row
  - Reset to default
  - Set project GPS policy
- **access**: Tenant admin (uploads.policy.manage)

#### Quarantine review `/admin/files/quarantine` (Upload & file processing pipeline)

Review failed or newly flagged files after rescan.

- **layout**: List with a detail drawer showing scan history.
- **sections**:
  - Failed and flagged items
  - Scan results and rescan history
  - Where used (references)
- **actions**:
  - Keep quarantined
  - Delete
  - Request rescan
  - Notify uploader
- **access**: uploads.quarantine.review (security or tenant admin); no preview of unreleased content

#### Storage quota view `/admin/files/storage` (Upload & file processing pipeline)

Show usage and quotas per tenant and project.

- **layout**: Dashboard with usage bars and a project table.
- **sections**:
  - Tenant usage
  - Per-project usage and limits
  - Dedupe savings
  - Reused-file integrity signals
- **actions**:
  - Edit quota
  - Export usage
- **access**: Tenant admin; project managers read their own project

#### Attachment scan chip `Embedded: scan status chip and attachment component` (Upload & file processing pipeline)

Show quarantined, clean or failed on every attachment.

- **layout**: Inline chip with tooltip and a detail popover.
- **sections**:
  - Status
  - Scan time
  - Reuse flag
- **actions**:
  - View scan details
  - Retry upload
- **access**: Anyone who can see the parent record; files served only when clean
