# Data import, export & backup (`data_io`)

- **Group:** Platform services
- **Phase:** P1

What it is
Data import, export and tenant export for the platform (Platform services; suggested phase P2). It gets data into and out of the system in bulk and gives customers a no-lock-in exit path. It is a customer-facing portability and handover tool, not disaster recovery. Production backup and recovery rely on Postgres PITR, managed snapshots and S3 versioning with cross-region copy, which this module does not replace. It also serves legal hold, siloed or on-premise customers and single-tenant handover.

What it does
- Imports Excel and CSV asynchronously, with validation and a dry-run report before anything is committed.
- Exports any register, or the whole organisation's data, as Excel, CSV or JSON, honouring permissions and masking.
- Produces a tenant export (records, files and audit chain) with a verification manifest, as an authorised, logged, rate-limited admin action, because it is a bulk-exfiltration path.
- Respects legal hold on all deletes, overwrites and rollbacks.
- Supports bulk creation and bulk update of existing records, and undo of a whole import batch.

Features
- Import wizard: template download, column mapping, dry run, row-level error report with fix-and-reimport, async job.
- Import limits: file size limit, schema validation, formula-injection protection.
- Asset tree import (deferred in AIP's tree context menu): parent resolution, code rules, and a preview of the resulting hierarchy that catches orphans and duplicate tags before commit.
- Update-by-key mode for bulk edits of existing assets, welds and components, not only create.
- Import batches with rollback of the whole batch, plus import history.
- Export any register or the whole tenant as Excel, CSV or JSON.
- Export manifests with checksums and a documented schema per module, so customers and auditors can verify completeness.
- Tenant export controls: restricted to tenant admins, step-up MFA, approval (dual approval for full exports), encryption with tenant keys, expiring time-limited downloads, rate limiting, audit logging, alerts on volume anomalies.
- Handover data book export per asset subtree with structured data and linked files, reusing the same export contract.
- Legal hold respected.

Interactions
- Asset hierarchy and registers: tree import, update-by-key and register exports.
- Operations, hosting and deployment: runs as background jobs.
- Security and compliance programme: exfiltration controls, audit events, masking, MFA step-up.
- All other modules: read through a registered export contract so new modules join exports automatically.
- Users and permissions: imports and any restore must map users via the users table and never bypass row-level security or cross tenants.

Data
- Import job: file, mapping, mode (create or update-by-key), dry-run result, row errors, status, batch id.
- Import batch: records created or changed, rollback state.
- Export or backup set: scope (tenant, project or asset subtree), manifest, checksums, encryption key reference, expiry, requester, approver(s).
- Documented schema per module.
- Audit events for every import, export, approval, download and rollback.
- Restore request (if restore is built): conflict report, user mapping.

Pages
- Import wizard (template, upload, mapping, dry run, errors, commit).
- Tree import preview.
- Import history with batch rollback.
- Export page: register or tenant scope picker, format choice.
- Tenant export request and approval, with download showing expiry.
- Handover data book export from an asset subtree.

Decisions and notes
- Owner accepted: tree import with preview, update-by-key, batch rollback, manifests with checksums and schemas, step-up MFA with approval and encryption, handover data book export.
- This module is a tenant export and portability tool only; real backups are infrastructure-level.
- Source references: PRD section 12 (full organisation data export), spec E2-S4 and E2-S5, tree Import deferred (TASKS section 48).
- Rio Tinto-type clients may demand exit rights and long retention, so portability matters.
- Competitors generally offer export tools or data on request rather than self-service backup, though specifics are unconfirmed.

Open questions
- Is a restore or import-from-export path built at all? The designer proposed restore preview with conflict report; the other advisors stress hostile-data risk and cross-tenant restore risk. Not decided.
- Is dual approval required for every full export (security output) or a single approval (accepted suggestion wording)?
- Are scheduled exports to storage in scope? The scout saw them in the market; not accepted.
- Is project-scoped export in scope alongside tenant scope?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
