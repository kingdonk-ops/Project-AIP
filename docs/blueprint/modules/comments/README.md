# Comments, mentions & notifications (`comments`)

- **Group:** Collaboration & coordination
- **Phase:** P1

What it is
The shared collaboration and alert layer for the asset-centric inspection, ITP/QA traceability and site platform. It has two services: a comments service that gives every module threaded discussion on any record or file, and a notification service that tells people about things. Comments are table stakes for users, so this is built as shared infrastructure rather than a headline feature. The differentiator is that discussion stays attached to asset and inspection records and survives across projects. Terminology must be renamable per market, so all message wording uses translatable keys. First customer is Kaefer on Rio Tinto remediation work.

What it does
One comments service keyed by (record type, record id, asset id) gives every module threaded comments, @mentions, resolve state and pins on PDF pages or photos. One notification service consumes domain events from the outbox, resolves recipients, applies per-user preferences and delivers in-app, email and push (mobile) messages, with digests. Other modules publish events to it and never send their own messages. Several AIP deferrals wait on this module: assignment, overdue corrective actions, schedule reminders and expiry reminders.

Features
- Threaded comments with @mentions, resolve and reopen
- Comment pins on PDF pages and photos (page, x/y, optional asset or defect link); viewpoints capture a drawing or photo reference with markup JSON
- Comments on a file are scoped to a file version and can be carried forward on request
- Comment visibility classes (internal, shared with client, shared with subcontractor) set per comment, with clear on-screen badges, so commercial or safety-sensitive remarks never reach other parties
- Asset-level discussion history: a combined thread view on an asset node rolling up comments from its inspections, NCRs and RFIs
- Comment conversion: turn a comment into a task, issue or corrective action, with a back-link
- Edit history and superseding comments: edits never overwrite; admins can see history; legal-hold protection applies
- In-app notification centre with unread counts, email and mobile push
- Per-user preferences and daily digest; mark read, snooze, mute thread
- Notifications driven by domain events (assignment, approval needed, overdue, expiring)
- Notification rules by asset subtree, discipline and severity (for example any failed inspection under Unit 3 notifies the QA lead)
- Quiet hours and site-shift awareness, with escalation for critical items (hold point waiting, expired certificate)
- Mandatory safety and legal notices bypass mute settings
- Translatable message keys with admin wording overrides per tenant
- Idempotent delivery jobs with deduplication to prevent notification storms
- Per-tenant search indexing of comment text

Interactions
- Audit trail, activity and timeline: events come from the outbox; comment events are written to the timeline
- Tasks, deadlines and my work: mentions and assignments create work items; deadlines use notifications for reminders and escalations; converted comments become tasks
- Markup, viewer and plan room: comment pins are overlaid from here; file approvals may require all comments resolved before final approval
- Users, sign-in and SSO: preferences on profile; users and teams are read for mention lookup
- Permissions: project and asset permissions are checked before any thread is shown
- Dashboards and meetings: scheduled digests and minutes distribution use the notification service
- Issues and corrective actions: conversion targets

Data
- Comment: record type, record id, asset id, parent id, body, author, file version, status (open/resolved), visibility class, author organisation, edited/superseded flag, legal-hold flag
- Mention
- Pin: page, x, y, optional asset or defect link
- Viewpoint: drawing reference, markup JSON, photo
- Notification: translatable message key, parameters, recipient, record link, channel, read/seen state
- Preference: user, event type, channel, digest frequency, quiet hours
- Notification rule: asset subtree, discipline, severity, recipients
- Template and tenant wording override
- Events emitted include comment.mentioned and comment.resolved

Pages
- Comment side panel embedded in every record page and in the viewer
- Mentions-of-me inbox
- Viewpoint and pin capture on drawings and photos, with resolve filters
- Asset discussion history view on the asset node
- In-app bell and notification inbox
- Preference matrix
- Admin template, wording override and notification rule screens

Decisions and notes
- Owner accepted all six scout suggestions: visibility classes, asset discussion history, subtree/discipline/severity rules, quiet hours with escalation, conversion actions, and edit history with legal hold.
- Optimistic concurrency is used instead of locks.
- Treat as a shared service, not a headline feature.
- External parties see only threads their visibility class allows.

Open questions
- Delivery transport is undecided: advisor suggested SSE in-app with SES email and optional Teams or Slack, while the existing stack is Python FastAPI; the advisor's BullMQ job runner does not fit and the job mechanism needs choosing.
- PDF markup: build in-house or license a PDF SDK (Apryse or Nutrient), given the cost of matching Bluebeam.
- Whether to support reply by email into the thread (seen in the market, not accepted).
- Whether Teams or Slack channels are in scope.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
