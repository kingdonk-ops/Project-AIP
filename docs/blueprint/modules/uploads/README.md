# Upload & file processing pipeline (`uploads`)

- **Group:** Documents & records
- **Phase:** P0

What it is
The single, safe path by which every file enters the platform, including very large files and uploads interrupted by poor site connections. It is plumbing rather than a market differentiator, but it is the highest-exposure surface in the system because it parses untrusted CAD, IFC, PDF and image content. One upload service covers ordinary files (photos, forms, PDFs) and large resumable uploads (drawings, PDF packs, NDT data, and later multi-gigabyte CAD or IFC models). Suggested phase: P0.

What it does
Clients request a signed URL and upload directly to a quarantine bucket, bypassing the app. Because the app is bypassed, content-type checks, size limits and tenant-prefix enforcement live in the signed policy and in a post-upload quarantine step. Large files use S3 multipart or tus so they survive dropped connections. After upload, the object is scanned with ClamAV, validated by magic bytes (never by extension), and checked against size and decompression-ratio caps. Thumbnailing, preview generation and OCR run in sandboxed workers. Only then is the object released to tenant-scoped storage and a reference returned to the caller. The pipeline fails closed on scan errors. For chunked uploads, type is re-validated server-side after reassembly, and the assembled file gets the same quarantine and scanning as any other upload.

Features
- Presigned upload with a confirm-upload metadata step
- Resumable chunked uploads (tus or S3 multipart) that survive dropped connections
- Quarantine bucket, then ClamAV, then magic bytes, then size and ratio caps, then release
- Thumbnail and preview generation; EXIF GPS handling configured per project
- Sandboxed, network-isolated, non-root converters with CPU, memory and time limits and short-lived credentials
- Scan status chip on attachments (quarantined, clean, failed)
- Unguessable, user-bound upload IDs; session expiry; scheduled cleanup of orphan parts; quotas against storage exhaustion; project permissions enforced on each chunk request
- Upload tray with progress, pause, resume, retry and a recovery prompt after reconnecting
- Capture-time metadata preservation: original device timestamp, GPS (where permitted) and a capture hash stored privately, separate from the sanitised shared copy
- Offline upload queue with priority, bandwidth rules (Wi-Fi only for video) and visible per-file state
- Content-hash deduplication across a tenant with reference counting; reuse of the same photo or certificate across different records is flagged as an integrity signal
- Per-file-type policy table (allowed types, max size, scan depth, preview behaviour) editable by tenant admins within platform limits
- Rescan of stored files on signature-database update, with automatic quarantine of newly detected items; scanner signatures kept current
- Specialist previews for NDT and survey formats: DICOM-like radiography, point-cloud thumbnails, spreadsheets of thickness readings
- Storage quotas and file-size policies per tenant or project

Interactions
- Document library and control: stores results; completion creates a document or file_versions record
- Offline field app and sync: deferred mobile uploads via the offline queue
- Security and compliance programme: hardening controls, tenant-scoped prefixes and KMS keys (relevant to IRAP)
- Operations, hosting and deployment: worker capacity
- Jobs: triggers conversion, OCR and thumbnail jobs
- Consumed for attachments by documents, forms, inspections, daily diary and NCR
- Depends on projects and users for permissions
- Emits upload.completed and upload.rejected, consumed by documents and notifications
- Files are served from a separate domain

Data
- Upload session: tenant, project, requester, declared type and size, status
- Resumable session: file hash, chunk size, parts received, expiry, assembled file reference
- Quarantine object and scan result (including rescan history)
- Private capture metadata (device timestamp, GPS, capture hash) linked to the sanitised public copy
- Content hash with reference count per tenant
- Per-file-type policy rows (allowed types, max size, scan depth, preview behaviour)
- Quota usage per tenant or project

Pages
- Upload tray with per-file state, progress, pause, resume and retry
- Scan status chip on every attachment
- Tenant admin file-type policy table
- Quarantine review list for failed or newly flagged items
- Storage quota view

Decisions and notes
- AIP currently uses local app storage (app/storage.py) with a PRD /media/presign flow. Local storage is acceptable only for the Coolify dev environment; the S3 swap is planned before multi-instance deployment and local disk must not be used in production.
- Ordinary and resumable uploads are merged into one service on S3 presigned URLs, with multipart for large files.
- Multi-gigabyte CAD is phase 2; photos, PDFs and NDT data over poor remote WA site connections are the priority.
- Accepted by the owner: metadata preservation, offline queue, deduplication, per-type policy table, rescan on signature update, specialist NDT and survey previews.
- Converters and OCR run in containers with no network egress and hard resource limits.
- OCR options noted: AWS Textract (Sydney region) or OCRmyPDF/Tesseract in a worker, indexed in Postgres full-text search initially.

Open questions
- tus or S3 multipart for resumable uploads: advisors list both and no choice has been made.
- OCR engine: Textract (Sydney) versus OCRmyPDF/Tesseract is undecided.
- Default EXIF GPS stripping policy per project, given the accepted private retention of original GPS.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
