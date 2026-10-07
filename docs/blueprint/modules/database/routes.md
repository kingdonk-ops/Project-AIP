# Page specs for `database`

#### Table convention coverage `/admin/platform/schema-coverage` (Database & schema conventions)

Show RLS and convention compliance per table as audit evidence.

- **layout**: DataTable with summary header and detail drawer
- **sections**:
  - Summary (tables failing, last run)
  - Coverage table (tenant_id, RLS, FORCE RLS, indexes, append-only grants, sync columns)
  - Policy and index viewer
- **actions**:
  - Re-run checks
  - Export report
  - View policy
  - View exceptions
- **access**: Platform admin and security lead; auditors read-only

#### Recycle bin `/recycle-bin` (Database & schema conventions)

Restore or purge soft-deleted records, respecting legal holds.

- **layout**: DataTable with filter bar and bulk toolbar
- **sections**:
  - Filters (type, project, deleted by, hold, dates)
  - Deleted records table
  - Hold warning banner
- **actions**:
  - Restore
  - View
  - Purge (blocked under hold)
  - Bulk restore
- **access**: Project admin for own projects; tenant admin for all; purge needs elevated permission

#### Legal holds `/admin/legal-holds` (Database & schema conventions)

Place and release holds at record, asset or project level.

- **layout**: DataTable with create dialog
- **sections**:
  - Holds table (scope, target, reason, placed by, status)
  - Place hold form with target picker
  - Affected-records preview
- **actions**:
  - Place hold
  - Release selected
  - View affected records
- **access**: Tenant admin and designated legal or records role

#### Data retention settings `/admin/database/settings` (Database & schema conventions)

Configure soft-delete retention, purge schedule, partitions and hot attributes.

- **layout**: Settings form with read-only roles reference
- **sections**:
  - Soft-delete retention and purge schedule
  - Partition intervals
  - Hot-attribute approvals
  - Database roles reference (read-only)
- **actions**:
  - Save
  - Approve hot attribute
- **access**: Tenant admin for retention; platform admin for partitions and roles

#### Concurrency conflict dialog `(modal)/conflict` (Database & schema conventions)

Resolve a 409 sync_version mismatch.

- **layout**: Modal with side-by-side current vs your changes
- **sections**:
  - Field-by-field diff
  - Current record summary
- **actions**:
  - Merge selected fields
  - Reload current
  - Cancel
- **access**: Any user editing the record
