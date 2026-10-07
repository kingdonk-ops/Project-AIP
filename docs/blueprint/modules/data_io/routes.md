# Page specs for `data_io`

#### Import wizard `/p/:projectId/import` (Data import, export & backup)

Bulk create or update records from Excel or CSV with validation and dry-run before commit.

- **layout**: Stepper page: template, upload, mapping, dry run, errors, commit.
- **sections**:
  - Template download per register
  - File upload with size limit
  - Column mapping
  - Mode selector (create or update-by-key)
  - Dry-run summary
  - Row-level error report
  - Commit confirmation
- **actions**:
  - Download template
  - Upload file
  - Map columns
  - Run dry run
  - Download error report
  - Fix and re-upload
  - Commit as async job
- **access**: Users with import permission on the target register, subject to the same row-level scope as manual entry.

#### Asset tree import preview `/p/:projectId/assets/import` (Data import, export & backup)

Preview the resulting asset hierarchy and catch orphans and duplicate tags before commit.

- **layout**: Split view: source rows on the left, resulting tree preview on the right with issues panel.
- **sections**:
  - Parent resolution settings and code rules
  - Tree preview with new, changed and unchanged markers
  - Orphan and duplicate tag list
  - Summary counts
- **actions**:
  - Adjust code rules
  - Resolve orphan
  - Resolve duplicate
  - Commit
  - Cancel
- **access**: Asset managers with asset create/update permission.

#### Import history and batches `/p/:projectId/import/history` (Data import, export & backup)

Review past imports and roll back a whole batch.

- **layout**: Table with a batch detail drawer.
- **sections**:
  - Batch table (file, mode, user, counts, status)
  - Batch detail (records created or changed)
  - Rollback state and legal hold flag
- **actions**:
  - View detail
  - Download original file and error report
  - Roll back batch
  - Re-run
- **access**: Importer and project admins; rollback is blocked when records are under legal hold.

#### Export `/p/:projectId/export` (Data import, export & backup)

Export a register or project data as Excel, CSV or JSON.

- **layout**: Single form with scope picker and recent exports list.
- **sections**:
  - Scope picker (register, project, asset subtree)
  - Format choice
  - Column and masking preview
  - Recent exports with expiry
- **actions**:
  - Start export
  - Download when ready
  - Cancel
- **access**: Users with export permission per register; output honours permissions and masking.

#### Tenant export requests `/admin/data/tenant-export` (Data import, export & backup)

Request and approve full tenant exports with strong controls.

- **layout**: Request list with a detail page showing approval progress.
- **sections**:
  - Request form (scope, reason)
  - Step-up MFA prompt
  - Approval status (single or dual, configurable)
  - Encryption key reference
  - Download with visible expiry
  - Manifest and checksum verification
- **actions**:
  - Request export
  - Approve or reject
  - Download
  - Verify manifest
  - Cancel request
- **access**: Tenant admins only; requester cannot approve their own request; every action is audited and rate-limited.

#### Handover data book export `/p/:projectId/assets/:assetId/handover-export` (Data import, export & backup)

Export an asset subtree's structured data and linked files as a handover package.

- **layout**: Wizard in a side sheet launched from the asset tree.
- **sections**:
  - Subtree summary
  - Included modules and files
  - Manifest preview
  - Progress and download
- **actions**:
  - Select modules
  - Start export
  - Download
  - Verify manifest
- **access**: Users with handover export permission on the subtree, such as project managers and document controllers.

#### Export schemas and manifests `/admin/data/schemas` (Data import, export & backup)

Show the documented schema for each module's export for customers and auditors.

- **layout**: Master-detail documentation view.
- **sections**:
  - Module list
  - Schema per module
  - Sample manifest
- **actions**:
  - Download schema
  - Download sample manifest
- **access**: Tenant admin, auditors and project admins (read-only).
