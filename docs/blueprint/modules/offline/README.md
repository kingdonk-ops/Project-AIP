# Offline field app & sync (`offline`)

- **Group:** Asset core
- **Phase:** P2

What it is
The mobile/tablet app that lets inspectors work with no signal and sync later. It is the riskiest module and the biggest gap in the chosen stack for LNG and mining sites.

What it does
Inspectors download their assigned assets, templates and open work, capture inspections, photos, measurements and issues offline, and sync when connected. It uses cursor-based delta pull and an idempotent push outbox with client-generated ids. Inspection responses are append-only so no measurement is ever lost, and media uploads are deferred until online. Conflicts on the same field show a merge screen.

Features
- Bottom tabs: Today, Capture, Inspections, Sync; large Capture button (photo, voice, form, defect)
- Scan QR/NFC to open an asset; last-used asset default
- Sync scope: assigned sites/projects, active templates, open work, last 12 months of history
- Pull cursor (timestamp, id); push batches up to 500 ops with batch_id idempotency; pull cap 2,000 rows with has_more
- Per-item sync state and a sync chip in the header
- Encrypted local store (SQLCipher or IndexedDB encryption)
- Conflict rules per record type; field-level merge screen
- Photo markup on capture; deferred presigned upload
- Sync triggers: app foreground, reconnect, every 5 minutes; 2s autosave debounce
- Offline eligibility snapshot with sync-time revalidation: gating works offline from a downloaded validity snapshot, then is rechecked on sync and sign-offs made on since-expired data are flagged
- Offline drawing and document packs per work area, with versions and stale warnings
- Storage budget and media compression controls, with upload prioritisation
- Sync diagnostics and support bundle (log and queue inspector, shareable)
- Device management with remote wipe and lost-device flow
- Conflict simulation test harness: scripted multi-device, long-offline scenarios in CI

Interactions
- Inspections, ITPs and hold points: run inspections offline
- Asset hierarchy and registers: asset subset syncs to device
- Upload and file processing pipeline: deferred media upload
- Users, sign-in and SSO: device registration and PIN users
- Certificates, competency and calibration gate: eligibility snapshot
- Forms and templates: templates sync to devices
- Tech stack: PWA vs native decision
- Events consumed: user deactivated (revoke devices), assignment changed (scope change), template published

Data
- Spec: docs/spec/05-sync-protocol.md, PRD section 5, backlog E8 (S1-S5)
- devices table: tenant, user, device_label, platform (pwa/ios/android), public_key (device-bound), app_version, status (active/revoked/wipe_pending/wiped), last_seen_at, last_pull_cursor, wipe_requested_at, soft delete
- sync_batches / sync_operations: unique (tenant, device, batch_id), op_count at most 500, per-op results returned on replay, append-only; payloads under a retention job, hash-only after retention for legal hold
- Every syncable table needs a composite index (tenant_id, updated_at, id), sync_version and deleted_at tombstones so deletes propagate
- Media rows live in the uploads module; this module stores pending refs only
- Backend module backend/app/modules/offline: pull, push, scope, conflict registry and handler registry; new syncable record types register a handler and conflict rule from the owning module
- Security: bind devices, remote revoke and wipe, limited sync scope, re-check authorisation on every push, treat client timestamps and IDs as untrusted
- Settings: sync scope rules, page cap and batch max, sync interval and debounce, allowed networks, encryption requirement, device approval and max devices per user, PIN policy and offline TTL, offline session maximum, conflict rules, media compression and size limits, wipe policy, stale-data threshold

Pages
- Today (/m/today): assigned work, hold points, eligibility warnings, last-used assets, unsynced warning
- Capture (/m/capture): photo with markup, voice, form, defect, asset context bar
- Inspections (/m/inspections): card list with sync badges and download status
- Inspection runner (/m/inspections/:id): stepper on a pinned template revision with eligibility banner, signature and autosave
- Sync (queue/outbox): per-item state, retry, view payload, resolve conflict, discard drafts; conflict list with keep mine/keep server; deferred media uploads; sync log; device and security status
- Notifications: repeated sync failure, conflict, stale unsynced data, stalled media, device revoked or wipe requested, device not synced for X days, storage nearly full

Decisions and notes
- Not built yet.
- All six scouted suggestions accepted.
- Test on real devices and poor connectivity; note iOS background sync and storage-eviction limits.
- Define conflict rules per record type up front.

Open questions
- PWA versus native. The tech stack advisor recommends a PWA (service worker, IndexedDB via Dexie or RxDB, background sync, tus or S3 multipart uploads), which fits the append-only sync, with Expo/React Native (WatermelonDB or PowerSync) if camera, biometric and background sync reliability require it. The owner has not decided.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
