# Page specs for `audit`

#### Project Timeline `/projects/:pid/timeline` (Audit trail, activity & timeline)

Cross-module event feed

- **layout**: Feed with filter rail
- **sections**:
  - Filters
  - Event feed
  - Exception flags
- **actions**:
  - Filter
  - Open source
  - Export
- **access**: audit.read

#### Asset Activity and Who Touched This `/assets/:assetId/activity` (Audit trail, activity & timeline)

Subtree rollup of events for an asset

- **layout**: Tab on asset detail with subtree toggle
- **sections**:
  - Subtree toggle
  - Feed
  - Actor summary
- **actions**:
  - Toggle subtree
  - Open source
- **access**: Asset view plus audit scope

#### Record Activity Tab `/records/:type/:id/activity` (Audit trail, activity & timeline)

Field-level history with reasons

- **layout**: Tab on record
- **sections**:
  - Events
  - Before/after diff
  - Reason for change
- **actions**:
  - Open diff
- **access**: Record view permission

#### Security Audit View `/admin/audit/security` (Audit trail, activity & timeline)

Auth, permission and export events

- **layout**: Table with filters
- **sections**:
  - Events
  - Filters
  - SIEM status
- **actions**:
  - Filter
  - Export
- **access**: security.audit.read

#### Audit Export and Verification `/admin/audit/export` (Audit trail, activity & timeline)

Export with signed manifest and verify chain

- **layout**: Wizard
- **sections**:
  - Scope
  - Manifest
  - Verification result
  - Verifier download
- **actions**:
  - Export
  - Verify
  - Download verifier
- **access**: audit.export

#### Legal Hold Register `/admin/audit/holds` (Audit trail, activity & timeline)

Place and release holds

- **layout**: Register with form
- **sections**:
  - Active holds
  - History
  - Scope picker
- **actions**:
  - Place hold
  - Release hold
- **access**: legal.hold.manage

#### Recycle Bin `/admin/recycle-bin` (Audit trail, activity & timeline)

Restore or purge soft-deleted records

- **layout**: Table with days remaining
- **sections**:
  - Items
  - Hold flags
- **actions**:
  - Restore
  - Purge (blocked under hold)
- **access**: recycle.manage
