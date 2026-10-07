# Document library & control (`documents`)

- **Group:** Documents & records
- **Phase:** P1

What it is
Document library & control is the single document store for the platform (Documents & records, suggested phase P1). Every file is attached to an asset and/or a record (inspection, issue, RFI, task, submittal, project), and carries project_id and an optional asset_id. It is asset-first: retrieval starts from the asset or record, not a folder tree. It absorbs the separate file_* modules (versions, tags, trash, references, search) as features on one file table with one revision chain and one audit trail. ISO 19650 naming and states are an optional configuration of documents, not a separate model.

What it does
Lets users upload and classify files against assets and records, control revisions (one current, others superseded), find files by asset, tag, view or OCR full-text search, notify people through distribution lists, and recover deleted files from a recycle bin. It tracks required prerequisite source documents and can block work from starting until they are received. Where a client requires it, it applies lightweight ISO 19650 naming validation and container states (WIP, Shared, Published, Archived). Differentiator versus project/folder-centric competitors: asset_id as a first-class link, tenant-configurable terminology, and quarantine/OCR ingestion tied to inspection records. The aim is to compete on traceability, not on generic storage.

Features
- Upload against asset, inspection, issue or project; document type, title, revision, metadata; upload progress and thumbnail previews
- Bulk upload with filename parsing (client naming conventions, auto-naming from templates) and duplicate detection by file hash
- Revision control: document_group_id, current vs superseded, promote-to-current, restore of any version, version history with compare and download
- Tags (discipline/phase defaults), favourites and pins, personal and shared saved smart views
- Cross-references from files to RFIs, issues, inspections, tasks and submittals
- OCR full-text search (Textract or Tesseract) with Postgres FTS
- Distribution lists and subscriptions, with notification on new revisions
- Recycle bin with retention window and legal-hold override; purge must respect legal hold
- ISO 19650 naming validation and container states with suitability codes and an append-only state transition log; signing can be required on gate approvals; labels and state names renameable per tenant
- Required source-documents register (permits, surveys, geotech, procedures) with status
- Required-documents gate before scope start, reusing the completion-gate pattern: work cannot start until required documents are marked received
- Documents tab on the asset detail page with inherited subtree view (optionally including child assets), showing drawings, certificates and reports
- Photo gallery view per asset and inspection, important for CUI work where visual evidence is the main record
- Controlled-copy watermark with download stamp: user, time and revision stamped on download or print so copies show they may be superseded
- Client-configurable document register export (columns and formats per client)

Interactions
- Upload & file processing pipeline: all files enter through quarantine, ClamAV scan and OCR
- Markup, viewer & plan room: viewed and annotated
- Workflow & approvals engine: document approval routes and ISO gate approvals
- Transmittals & correspondence: sent formally; transmittals can be created automatically on publish
- Handover, data books & submissions: bundled into data books
- Search, retrieval & saved views: indexed for search
- Notifications: receive document and state-change events
- Reads projects, users and the asset tree; emits document.created, document.updated, document.deleted and cde.state_changed

Data
- Document: id, tenant, project_id, asset_ids[], discipline, type, title, status, current_version_id, hash, custom fields, document_group_id
- FileVersion: document id, version number, storage key, hash, uploader, comment, created at, is_current
- Category and tag definitions (tenant-configurable names and fields)
- Cross-reference links, distribution lists and subscriptions, saved views
- Required-document register entries with status
- ISO 19650 fields: state, suitability code, originator, asset/zone; StateTransition log (append-only)
- Storage: S3 with per-tenant prefix and KMS, regional buckets, short-lived signed URLs

Pages
- Documents and Records > Document Library: folder and smart-view tree on the left, file table in the centre, preview pane on the right, with asset-tree facet
- Upload dialog with metadata and drag-drop; document detail with preview, history and links
- Version history drawer with compare, download and restore
- Documents tab on the asset detail page; photo gallery
- Required-documents register
- Documents and Records > CDE Containers: table with state columns and transition action menu
- Register export configuration

Decisions and notes
- Built in AIP: documents/attachments first slice (TASKS section 22), revision control (section 43), recycle bin (sections 7 and 9.4). Deferred items (asset Documents tab, photo gallery, S3 storage swap before multi-instance deployment) are now accepted features.
- Define storage, virus scanning, retention and legal hold early; OCR, versioning and CDE build on them.
- ISO 19650 is an optional configuration, not a separate model. Clients mandating a specific CDE will need integration, not replacement.
- Security: apply asset, team and external-share scope on every download and preview.
- Folders are secondary to asset and record links; folder permissions are not a competitive focus.

Open questions
- Whether a separate Folder entity is kept (feature designer) or retrieval relies on smart views and asset links only (asset-first stance).
- Whether ISO 19650 container records stay purely as configuration on Document, or a UK customer later justifies a dedicated InformationContainer model.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
