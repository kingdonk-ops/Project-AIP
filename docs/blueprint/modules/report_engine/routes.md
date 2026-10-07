# Page specs for `report_engine`

#### Report templates `/settings/reports/templates` (Report engine & published records)

List versioned report templates by record type, variant, orientation and client.

- **layout**: DataTable with a filter bar and bulk action bar.
- **sections**:
  - Filters (record type, variant, orientation, client, status)
  - Table (name, record type, variant, orientation, version, client, status, updated)
  - Empty state
- **actions**:
  - Create template
  - Edit
  - Preview with live data
  - Duplicate
  - Publish new version
  - Archive
  - Export JSON
- **access**: report.template.view. Authoring needs report.template.manage.

#### Report template designer `/settings/reports/templates/:templateId` (Report engine & published records)

Build a template from sections, map fields to slots, style it and preview it against real records.

- **layout**: Three-pane designer with a section outline on the left, a canvas in the centre and a properties panel on the right. A live-data preview pane sits on the canvas toggle.
- **sections**:
  - Section outline and blocks (tables, photos, charts, signature block)
  - Field mapping panel
  - Styling and branding
  - Orientation and page settings
  - Live-data preview with record picker
  - Version history
  - Pre-flight rule set binding
  - Domain blocks (thickness map, CUI condition, DFT chart)
- **actions**:
  - Add or reorder section
  - Map field
  - Preview with record
  - Save draft
  - Publish new version
  - Revert to version
- **access**: report.template.manage. Templates are sanitised on save.

#### Report register `/reports/register` (Report engine & published records)

Search issued reports with number, revision, source record and supersession.

- **layout**: Searchable DataTable with a filter sidebar and a preview drawer.
- **sections**:
  - Search and filters (client, record type, status, date)
  - Table (report no., revision, title, source record, template and version, client, generated, status, supersedes)
  - PDF preview drawer
  - Supersession chain
- **actions**:
  - Open report
  - Download selected
  - Add to data book
  - Export register CSV
  - Open source record
  - Republish as superseding
- **access**: report.view. Download of client variants follows project and client scope.

#### Publish dialog `Embedded: publish dialog on a source record` (Report engine & published records)

Preview, pre-flight, sign and distribute a record to a named recipient list.

- **layout**: Modal wizard with steps for preview, pre-flight, recipients and confirm.
- **sections**:
  - PDF preview
  - Pre-flight results from the rules engine
  - Variant and template selection
  - Recipient set picker validated against the project directory
  - Signer and seal summary
  - Link expiry
- **actions**:
  - Run pre-flight
  - Choose variant
  - Select recipients
  - Sign and publish
  - Cancel
- **access**: report.publish and the signer role for the record type. External recipients receive portal links.

#### Published history and receipts `/reports/published` (Report engine & published records)

Show published records with hash, recipients, delivery status and access log.

- **layout**: Table with a detail drawer.
- **sections**:
  - Published records table
  - Delivery receipts per recipient
  - Access log
  - Hash and manifest verification
  - Supersession chain
- **actions**:
  - Verify seal
  - Resend link
  - Extend or revoke link
  - Republish superseding version
  - Download manifest
- **access**: report.publish or report.audit.view

#### Render jobs `/reports/jobs` (Report engine & published records)

Monitor render and distribution jobs and retry failures.

- **layout**: Table with status filters.
- **sections**:
  - Job list (record, template, status, duration)
  - Error detail
- **actions**:
  - Retry
  - Cancel
  - Open record
- **access**: report.manage or tenant admin

#### Data book compiler `/projects/:projectId/databooks` (Report engine & published records)

Assemble reports and documents into an ordered data book with bookmarks and cover sheets.

- **layout**: Two-pane builder with a source picker on the left and an ordered book outline on the right, plus a preview.
- **sections**:
  - Source picker (reports, documents, certificates)
  - Per-asset ordering outline
  - Cover sheets and index settings
  - Compile status
  - Preview
- **actions**:
  - Add items
  - Reorder
  - Set cover sheet
  - Compile
  - Download
  - Publish as record
- **access**: report.databook.manage

#### Report settings `/settings/reports` (Report engine & published records)

Configure numbering, defaults, link expiry, branding and renderer.

- **layout**: Settings page with sections.
- **sections**:
  - Numbering and revision rules per client
  - Default templates per record type
  - Auto-generate on approval
  - Link expiry defaults
  - Branding per tenant and client
  - Renderer selection
  - Pre-flight rule set
  - Retention for published records
  - Allowed external recipient domains
- **actions**:
  - Edit and save
  - Preview numbering
- **access**: Tenant admin or report.settings.manage

#### Portal report download `/portal/reports/:linkToken` (Report engine & published records)

Let external recipients view and download a published report through an expiring authenticated link.

- **layout**: Minimal branded page on the separate portal origin, with a confirm button before the download.
- **sections**:
  - Report title, number and revision
  - Superseded warning if applicable
  - Download button
  - Seal verification info
- **actions**:
  - Confirm and download
  - Verify seal
- **access**: Named external recipient with a valid link. Access is logged as a delivery receipt.
