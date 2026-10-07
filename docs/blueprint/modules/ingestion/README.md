# Inbound capture & connectors (`ingestion`)

- **Group:** Documents & records
- **Phase:** P3

What it is
Inbound capture & connectors brings documents and correspondence into the app from outside: watched folders and cloud drives, forwarded emails and .eml files, chat and SMS gateways, generic webhooks, and an outbound-only agent for site laptops and NDT instrument export folders. Every channel feeds one governed pipeline with provenance, tenant scoping and a person in the loop. It is a documents and records module, suggested for phase P3. In the AIP repo it is not built. It is disabled by default per tenant.

What it does
All inbound channels pass through a single quarantine, malware scan (ClamAV), magic-byte check and OCR pipeline, run in network-isolated workers and reusing the upload and file processing pipeline. Each item is attributed to a verified sender or alias (or marked unverified) and lands as a draft record in a filing queue for a person to file or reject. Nothing inbound auto-creates records with privileged effect, and content is never auto-executed by AI. Duplicates are detected by content hash. When file names match, a new version is written via file_versions. Inbound paperwork such as mill certificates and test reports is read by OCR and proposed as component certificate candidates for human confirmation.

Features
- Watched folder and cloud drive connectors (SharePoint, S3, watched folder, email; keep connectors few rather than chasing breadth) with schedules, health status, test connection, pause, run now and retry
- Forwarded email and .eml import with threading by Message-ID and References headers; attachments extracted and stored as documents through the quarantine pipeline; HTML bodies sanitised, never rendered unsanitised
- Chat, SMS and generic webhooks with HMAC signatures, replay windows and per-tenant rate limiting; origin marked unverified unless signed
- Quarantine, ClamAV, OCR, then filing queue
- Sender verification and per-project aliases
- Sender trust levels: per-alias allow-lists, domain verification, SPF/DKIM/DMARC result display, and quarantine of unverified senders (sender identity treated as unverified unless SPF, DKIM and DMARC pass)
- Filing queue with suggested project, asset, document type and correspondence thread, learned from sender and filename patterns
- Mill-cert and test-report recogniser: OCR extraction of heat number, material grade and standard, proposed as component certificate candidates
- Site-laptop and NDT instrument export folder agent with outbound-only connection and allow-listed destinations (thickness readings, radiographs, UT files)
- Per-connector data-minimisation rules: file type allow-list, max size, path filters, retention of source copies
- Ingestion dashboard showing quarantined, failed and unfiled counts with ageing alerts

Interactions
- Upload & file processing pipeline: shared quarantine pipeline
- Transmittals & correspondence: files into correspondence
- Document library & control: files into the library
- Security & compliance programme: external exposure controls
- Notifications and jobs: receive connector.run_completed and connector.failed
- Notifications and change_intelligence: receive inbound_email.received
- Reads projects, users, documents (hash duplicate check) and the alias-to-project mapping
- Component traceability and certificates: receives certificate candidates

Data
- Connector: type, target path, project, default category and asset, schedule, credentials reference
- ImportRun: counts, errors
- ImportedFile: source path, hash, document id
- InboundMailbox: project address or forwarding alias, allowed senders
- RawMessage: hash, headers, stored original
- ParsedMessage: subject, from, to, cc, date, message-id, in-reply-to, attachments
- CaptureChannel: type, project and related settings for chat, SMS and webhook channels
- Secrets held in a secrets manager, scoped per tenant; egress limited to allow-listed hosts; destinations restricted against path traversal and SSRF

Pages
- Connector list with health
- Setup wizard with test connection
- Run log with failures and duplicates
- Import queue with unmatched items
- Mapping and review screen
- Mailbox and alias settings
- Filing queue
- Ingestion dashboard

Decisions and notes
- Disabled by default per tenant
- Drafts only; a person files every item
- One shared pipeline for every channel
- Owner accepted all six feature suggestions listed above
- Actions: create, pause, run now, retry, upload .eml, forward to alias, assign to project or asset, reject
- Differentiator is governed ingestion with provenance and tenant scoping; HTML sanitised
- Rate-limit per tenant and per alias
- Tech stack advice favours AWS SES inbound with S3 delivery

Open questions
- Email intake: AWS SES inbound with mailparser in a worker, or Microsoft Graph for M365 customers (likely for Kaefer and Rio Tinto)? Not yet decided; possibly support both.
- Should email import and non-email capture stay in this module or remain separate sub-modules? The competitor researcher suggested merging, and this module already combines them.
- Is legal-hold retention for inbound items in scope here or in the security and compliance programme?
- Should .msg import be supported alongside .eml?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
