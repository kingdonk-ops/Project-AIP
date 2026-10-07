# Site diary & field reports (`diary`)

- **Group:** Field operations
- **Phase:** P2

What it is
The legally significant daily record of what happened on site, captured by supervisors and field workers. Not built in AIP; the delivery advisor placed it in the Phase 1 MVP (suggested phase P1). One diary model absorbs the earlier field_diary and fieldreports, with two access modes (full user, and PIN/magic link) and a report output.

What it does
Records weather (auto-fetched), labour, plant, events, instructions received, delays, deliveries, photos, video and drone captures. At day end it is sealed into a tamper-evident signed record. Corrections are superseding entries or post-seal addenda, never edits. Field workers without full accounts contribute through PIN or magic-link access. A structured daily field report summarises workforce, delays, safety and approvals for the client.

Features
- Daily diary with weather (source and fetch time stored, manual override), labour and plant (pre-filled from resources and equipment), events, instructions, delays, deliveries from logistics
- Photos, videos and drone/reality capture, with malware scanning and metadata handling
- End-of-day seal: hash chain, signed PDF (PAdES, KMS-held key), RFC 3161 timestamp, S3 Object Lock copy, signer identity and recorded time source; seal job idempotent and time-zone aware
- Corrections as superseding entries; addendum workflow after seal; full history visible
- Field contributions by PIN/magic link: click-through POST to survive email scanners, short-lived signed tokens, device binding, attempt limits and rate-limited PINs, per-project and module scope, revocable, every action logged; users see only their own entries; entries treated as lower assurance until reviewed by an authenticated supervisor
- Daily field report for client distribution
- Links to RSWs, inspections and incidents of the day
- Offline capture (PWA) with client UUIDs
- Delay event records with cause code, duration, affected scope and notice-sent flag
- Auto-summary of the day's inspections, hold point outcomes and NCRs
- Trusted device time and capture time recorded separately from sync time
- Foreman contributions merged by area or crew with attribution
- Access and permit status snapshot (scaffold, isolations, permits) in the day record
- Missing-diary alerts and seal-overdue escalation

Interactions
- Users, sign-in & SSO: PIN/magic-link field access; one shared external-identity mechanism with the portal
- E-signatures & tamper-evident records: daily seal and signing engine (diary supplies the payload)
- Report engine & published records: signed PDF and client report
- Claims evidence pack: diary entries are core evidence
- Safety & HSE: incidents of the day
- Voice notes & phone log: confirmed drafts create diary notes
- Resources, equipment, logistics: pre-fill; events feed variations and claims evidence
- Notifications: diary not started or submitted, day sealed, amendment added, field link issued/used/expiring, report sent, sync conflicts

Data
- diary_days: one per project per date (unique), status open/sealing/sealed, IANA timezone defining the day boundary, opened_by or principal id, current_seal_id, sync_version
- diary_entries (typed, append-only), diary_entry_links, diary_seals, attachment links
- REVOKE UPDATE/DELETE on entries, links and seals for the app role; trigger blocks non-addendum inserts on sealed days and changes to date or project
- RLS with tenant_id and project_id on all tables
- Reuses assets, documents, inspections, issues, tasks, users
- Configuration: entry types and sections, cut-off time, timezone, required signers, weather provider, delay cause list, field access defaults, report template, retention and legal hold, terminology keys

Pages
- Diary register (/projects/:projectId/diary): table, month strip, missing-day indicators, bulk export and send
- Open diary day (/diary/new)
- Diary day detail (/diary/:date): sections for weather through amendments, seal and verification, report preview, contributors rail
- Field mobile day log, timesheet summary and link issue/revoke admin
- Permissions: diary.view, diary.create, diary.edit, diary.amend, diary.report

Decisions and notes
- All six advisor suggestions were accepted by the owner
- Differentiator is sealed archives with superseding corrections; verify competitor claims before asserting uniqueness

Open questions
- Is countersigning required by default?
- Default seal cut-off and auto-seal time per project?
- Is the Phase 1 or early Phase 2 timing final?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
