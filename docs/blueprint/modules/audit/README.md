# Audit trail, activity & timeline (`audit`)

- **Group:** Reporting, search & AI
- **Phase:** P0

What it is
The immutable record of who did what and when, shown as an activity feed per asset, record and project. It is the audit trail for the platform and the evidence source for claims and disputes. It is an append-only, hash-chained audit log written from the domain-event outbox, anchored periodically to S3 Object Lock, with permissions separate from app admin. The activity feed and project timeline are views over it, rolled up by asset id. It also hosts the recycle bin view of soft-deleted records. Phase suggestion: P0.

What it does
Captures every significant event across modules with actor, timestamp and before/after values, without depending on individual modules choosing to emit events (the universal audit writer captures changes itself). Presents the history as per-record activity tabs, an asset-subtree rollup and a cross-module project timeline. Corrections are superseding events, never edits, and superseding entries are shown rather than hidden. Visibility is filtered by the viewer's permissions. Lets auditors and tribunals verify the chain independently of the platform. Keeps a separate security audit stream for auth, permission changes and exports. Manages legal holds so that purge and recycle bin behaviour is defensible.

Features
- Append-only audit_log with before/after, actor, timestamp; REVOKE UPDATE/DELETE at database level, with separate DB roles so the app cannot rewrite the chain
- Hash chaining with prior hash, and periodic anchoring to S3 Object Lock
- Activity tab on assets, inspections and projects
- Project timeline feed, filterable by module, person, asset subtree and date
- Asset-subtree activity rollup with a 'who touched this asset' view, so a unit and everything beneath it appear in one feed
- Field-level change history with reason-for-change on controlled records (inspection results, certificates) changed after submission
- Flags on on-behalf-of, force-unlock and override events (gate overrides, expiry bypasses) so auditors can sample exceptions first
- Distinct security audit stream (auth, permission changes, exports, reads of sensitive records) in tamper-evident storage, with SIEM forwarding
- Offline verifier tool and signed export manifest, so the hash chain can be verified without trusting the platform
- Audit export for SOC 2, legal hold and disputes, with hash verification
- Legal hold manager scoped by project or asset subtree, with a hold register recording who placed and released each hold
- Recycle bin with days-remaining and scheduled purge, respecting legal hold
- Open the source record from any event
- Cursor pagination
- Separate audit read permission, distinct from tenant admin

Interactions
- Database & schema conventions: append-only tables
- E-signatures & tamper-evident records: attestations
- Claims evidence pack (basic): evidence source; also read by retrieval and reporting
- Comments, mentions & notifications: events trigger notifications
- All modules: comments, status changes, approvals, signings, force-unlocks and deadline extensions appear as events
- Permissions catalogue: audit read and export permissions

Data
- audit_log / TimelineEvent: tenant, project, asset, actor, auth strength, source module, record ref, event type, summary key, payload (before/after), source IP or device, hash, prior hash, occurred_at, flags (on-behalf-of, force-unlock, override), reason for change, superseded-by reference
- Security audit event stream, stored separately
- Anchor records (hash, S3 Object Lock reference, time)
- Legal hold and hold register (scope, placed by, released by, dates)
- Soft-deleted records with purge date
- Export manifest (signed)

Pages
- Project timeline
- Activity tab on asset, inspection and project
- Asset history and 'who touched this asset' view
- Security audit view
- Audit export and verification
- Legal hold register
- Recycle bin

Decisions and notes
- Built in AIP: Activity feed real audit trail (TASKS §14), Activity tab on asset detail (§28), recycle bin (§7)
- Spec in AIP: E10-S1/S2 universal audit writer and DB-level revoke
- The audit store is separate from editable business data and from app admin permissions
- Corrections are superseding events, never edits
- Purge jobs must honour legal hold
- Differentiator: a hash-chained, asset-filterable event stream supporting claims evidence, unlike most tools' per-module change history
- Owner accepted: offline verifier and signed manifest, security stream with SIEM forwarding, field-level history with reason-for-change, subtree rollup, exception flags, legal hold manager

Open questions
- None currently recorded; no advisor conflicts were found and the owner has not raised any.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
