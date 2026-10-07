# Report engine & published records (`report_engine`)

- **Group:** Inspection & quality
- **Phase:** P2

What it is
The report engine and published records module turns structured inspection, diary and meeting data into PDF reports, certificates and signed records. It sits in Inspection & quality (suggested phase P1). It is specified in the AIP repo (E7 S1-S4, report-template-schema.json, PRD §8) but not yet built. E-signatures, signature capture and landscape output all wait on it.

What it does
Report templates, stored as data, select sections and map fields to report slots, so one inspection can render as an internal report, a client report or a compliance certificate. Rendering is HTML to PDF in a background worker job, honours landscape layouts, stores the PDF as a document and lists it in a searchable register. Publishing signs diaries, minutes and inspection reports and distributes them to a named list. Each issued report is pinned to the template and data version used so it can be reproduced exactly years later.

Features
- Report templates as data: sections, field mapping, styling, orientation (landscape required for coating/DFT reports), versioning and live-data preview
- Internal, client and certificate variants of the same record
- Auto-generate on approval (configurable)
- Report QA pre-flight running the rules engine before generation, to stop issue with missing readings or unsigned points
- Async rendering in a worker queue
- Photos, charts and repeating tables inlined
- Domain blocks: thickness map, CUI condition and coating DFT charts (readings vs minimum wall, heat maps by grid)
- Wet-signature block: name, signature image, date/time
- Pin each issued report to template and data version; re-render with the pinned version
- Client-specific numbering and revision sequence rules with clear supersession (for example Rio Tinto numbering)
- Report register with search
- Publish a signed PDF and distribute to a named list; republish as a superseding version; corrections are new superseding entries, never edits
- Expiring authenticated download links with delivery receipts instead of emailed attachments
- Data book compiler with bookmarked index, cover sheets and per-asset ordering
- Branding per tenant/client

Interactions
- Inspections, ITPs & hold points: source data (diaries first, then meetings and inspections)
- Document library & control: PDFs stored as documents
- E-signatures & tamper-evident records: signature blocks and seals; document hash and signer attestation embedded in a verifiable manifest; sealed outputs stored immutably and linked to the audit chain
- Rules engine: pre-flight
- Terminology dictionary & localisation: report labels
- Handover, data books & submissions: data book compilation
- File distribution lists and users: recipients validated against the project directory
- Notifications, correspondence and closeout: receive record.published

Data
- Report template: key, version, record type (inspection/diary/meeting), variant, orientation, definition validated against report-template-schema.json, client company, status (published immutable)
- PublishingProfile: record type, template, recipients, signer roles, auto-generate flag, pre-flight rule set key, numbering sequence
- PublishedRecord (append-only; UPDATE/DELETE revoked for the app role): source record id and version, PDF document id, hash, publish time, recipients, delivery status, supersedes link
- Report register entry: search metadata, client report number, revision
- Delivery receipt: recipient, link, expiry, access log
- Numbering sequences; data snapshot freezing source version and data
- Seals and attestations are stored by the signing module; the manifest here references them. Data book output is a document plus manifest.

Pages
- Report templates list and three-pane template designer with live-data preview
- Publish dialog with preview and recipient set picker
- Report register with search at /reports/register
- Published history with delivery receipts
- Data book compiler

Access: report.template.view and report.template.manage; report.view; report.publish plus signer role.

Decisions and notes
- Gotenberg (Chromium) preferred for landscape coating/DFT reports with inlined photos; WeasyPrint is lighter but weaker on complex CSS; Playwright is the alternative.
- Render in a sandboxed, network-isolated worker, JavaScript disabled where possible, sanitised templates, to avoid SSRF and script risk.
- Recipients validated against the project directory, not free text; recipients outside the tenant get a controlled portal link; delivery logged.
- Pre-seal stamping and merging can use pdf-lib or pdfcpu.
- All six scout suggestions were accepted by the owner.
- Differentiator versus Procore, Fieldwire, SafetyCulture, Dalux, Sitemate and Autodesk Build: signed, hash-verifiable publishing with manifest and named recipients.

Open questions
- Sealing approach: PAdES via node-signpdf or AWS KMS-held keys, versus hash and manifest only.
- External signing (DocuSign or Adobe Sign) versus in-app attestations only.
- Immutable storage: S3 Object Lock for sealed outputs versus MinIO with object lock on Coolify, or hash-and-manifest only.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
