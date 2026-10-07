# Punch list & defects liability (`punchlist`)

- **Group:** Inspection & quality
- **Phase:** P2

What it is
Snag items at completion and defects reported during the defects liability period (DLP) after handover. Punch items carry photo, location and responsible party with a verify-before-close workflow. After handover the same records continue as defects tied to the asset, with retention release linked to verified closure. Terms are tenant-configurable (Punch, Defect, Deficiency, Snag).

What it does
Punch is implemented as a lightweight issue kind on the existing issues model with its own terms, quick capture and verification, avoiding a duplicate module. Location is dual: the asset tree (so history follows the asset) and an optional drawing pin or geographic point. Closure requires verification by someone other than the assignee, with evidence photos.

Features
- Punch items with photo, drawing pin, asset, responsible party, due date, category and priority
- Verify before close; reject and reopen
- Independent verifier with evidence
- DLP per project or contract with start and end dates, configurable by contract and jurisdiction
- Post-handover defects assigned to contractor or subcontractor; same record converts from punch phase to DLP phase
- Retention release gated on verified closure
- Walkdown mode on mobile with area progress, offline capture, voice notes and assign-later
- Export per area or contractor for handover (PDF and spreadsheet), add to transmittal
- Bulk assign, change due date, verify and export
- Create items from minor inspection failures; escalate to NCR
- Reminders and overdue notifications

Interactions
- Markup, viewer & plan room: pins on drawings
- Handover, data books & submissions: closeout readiness; handover completion starts DLP
- Issues, NCRs & corrective actions: escalate to NCR
- Asset hierarchy & registers: history follows the asset
- Inspections: minor defects create items
- Tasks: rectification tasks
- Portal: contractors see items assigned to their company

Data
Built on issues and assets; punch_items carry project_id, asset_id, number, phase (punch or dlp), title, description, category, priority, status (open, fixed, verified, closed, reopened), responsible_company_id, responsible_user_id, due_date, drawing_document_id, pin, location, source_inspection_id, escalated_issue_id, dlp_period_id, sync_version. Also verifications (append-only), dlp_periods and retention_links. Client-generated ids with last-writer-wins on non-status fields for offline. Retention eligibility is computed from item status and stored with a timestamp. Terminology is a terms key, not a column.

Pages
- Punch/defects register (/punch) with list, map and drawing toggle
- Create punch item (/punch/new) with mobile quick capture
- Punch item detail (/punch/:id)
- Verification queue (/punch/verification)
- Defects liability dashboard (/punch/dlp)
- Walkdown mode (/m/walkdown)

Decisions and notes
- Owner accepted all six suggestions listed above.
- Phase 2. AIP has issues but no separate punch or defects module.
- Verifier must differ from assignee; rule is configurable.
- Retention percentage, DLP length and release rule are configuration.

Open questions
- Whether disputed defects escalate to claims evidence and change orders in this phase is not decided.
- Retention and payment clock integration depth is not decided.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
