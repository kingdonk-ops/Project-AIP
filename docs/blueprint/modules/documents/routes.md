# Page specs for `documents`

#### Document library `/documents` (Document library & control)

Find and manage files by asset, record, tag or full text.

- **layout**: Three panes: left smart-view and asset-tree facet, centre file table, right preview pane.
- **sections**:
  - Smart views and saved views
  - Asset-tree facet with children toggle
  - Filter bar
  - Document table (number/title, type, revision, status, assets, discipline, project, tags, uploader, updated, size)
  - Preview pane
  - Bulk action bar
- **actions**:
  - Upload
  - Search (title and OCR)
  - Preview
  - Download (stamped)
  - Upload new revision
  - Tag
  - Link to asset or record
  - Add to distribution
  - Favourite or pin
  - Move to bin
  - Export register
- **access**: documents.view; actions need documents.edit or manage; results filtered by asset, team and external-share scope

#### Upload dialog `/documents/upload` (Document library & control)

Upload one or many files with metadata, naming validation and duplicate detection.

- **layout**: Modal with drag-drop zone and per-file metadata grid.
- **sections**:
  - Drop zone and progress
  - Filename parse results
  - Metadata form (title, type, assets, linked record, discipline, revision, tags, custom fields)
  - Duplicate hash warnings
  - Quarantine status
- **actions**:
  - Add files
  - Apply metadata to all
  - Submit
  - Cancel
- **access**: documents.create

#### Document detail `/documents/:id` (Document library & control)

Show a document with its history, links and state.

- **layout**: Preview on the left, tabbed metadata panel on the right.
- **sections**:
  - Preview
  - Metadata and custom fields
  - Linked assets and records
  - Version history
  - Cross-references
  - Distribution and subscribers
  - ISO 19650 state and transition log
  - Approvals
  - Activity and audit
- **actions**:
  - Download
  - Upload new revision
  - Edit metadata
  - Link record
  - Subscribe
  - Request approval
  - Open in viewer
  - Move to bin
- **access**: documents.view; edit needs documents.edit; downloads scope-checked

#### Version history drawer `/documents/:id/versions` (Document library & control)

Compare, download, promote or restore revisions.

- **layout**: Right-hand drawer with version list and compare view.
- **sections**:
  - Version list (number, uploader, comment, hash, current flag)
  - Compare view
  - Restore confirmation
- **actions**:
  - Download
  - Compare
  - Promote to current
  - Restore
- **access**: documents.view; promote and restore need documents.manage

#### Recycle bin `/documents/bin` (Document library & control)

Recover deleted files within the retention window.

- **layout**: Table with retention countdown and legal-hold badge.
- **sections**:
  - Deleted documents table
  - Retention and hold indicators
- **actions**:
  - Restore
  - Purge (blocked under legal hold)
  - Filter
- **access**: documents.manage; purge needs admin and is blocked by legal hold

#### Required-documents register `/documents/required` (Document library & control)

Track prerequisite source documents that gate scope start.

- **layout**: Register table with status chips and scope filter.
- **sections**:
  - Required documents table (name, scope, due, status, linked document)
  - Gate status summary
  - Overdue list
- **actions**:
  - Add requirement
  - Mark received and link file
  - Waive with reason
  - Export
- **access**: documents.view; edit needs documents.manage

#### CDE containers `/documents/cde` (Document library & control)

View ISO 19650 states and transition containers where enabled.

- **layout**: Table with state columns and row action menu.
- **sections**:
  - Container table (state, suitability code, originator, asset/zone)
  - Transition log drawer
- **actions**:
  - Transition state
  - View log
  - Filter by state
- **access**: documents.cde, only where ISO 19650 is enabled for the project

#### Asset documents tab `/assets/:assetId/documents` (Document library & control)

Show drawings, certificates and reports for an asset and optionally its subtree.

- **layout**: Tab within asset detail with a table and gallery toggle.
- **sections**:
  - Include children toggle
  - Document table
  - Type filters
- **actions**:
  - Upload against asset
  - Open
  - Download
  - Switch to gallery
- **access**: documents.view plus asset-subtree scope

#### Photo gallery `/assets/:assetId/photos` (Document library & control)

Visual evidence per asset or inspection, key for CUI work.

- **layout**: Responsive thumbnail grid with date grouping and lightbox.
- **sections**:
  - Filters (date, inspection, tag)
  - Thumbnail grid
  - Lightbox with metadata
- **actions**:
  - Open in markup
  - Tag
  - Link to inspection
  - Download
  - Before and after pair
- **access**: documents.view; GPS metadata per policy

#### Mobile documents `/documents/mobile` (Document library & control)

Find and view documents and capture photos on site.

- **layout**: Mobile list with asset search, camera upload and offline cache indicator.
- **sections**:
  - Asset-first search
  - Recent and pinned
  - Offline sets
  - Camera capture
- **actions**:
  - Open
  - Capture and attach photo
  - Pin for offline
  - Upload queued files
- **access**: documents.view and documents.create

#### Document settings and register export `/settings/documents` (Document library & control)

Configure types, naming, ISO 19650, retention, stamps and register exports.

- **layout**: Tabbed settings with a register export template builder.
- **sections**:
  - Types, categories and tags
  - Naming conventions and parsers
  - Distribution lists
  - ISO 19650 states and codes
  - Retention and bin window
  - Legal hold rules
  - Watermark and stamp text
  - Register export templates
  - Storage region and limits
  - Terminology labels
- **actions**:
  - Save
  - Create export template
  - Test filename parser
  - Run export
- **access**: Tenant admin or documents.admin; legal hold needs a records manager role
