# Integrations & webhooks (`integrations`)

- **Group:** Platform services
- **Phase:** P3

What it is
The platform services module that connects AIP to the tools customers already use: ERP/EAM/CMMS systems, Microsoft Teams, Slack, email and calendars. It gives customers a versioned public REST API, signed outbound webhooks, approved chat notifications, iCal feeds and connectors to client systems such as SAP PM and Maximo for work orders and asset sync. Suggested phase: P3. Inbound email and other inbound features belong to the inbound_email and connectors modules, not here.

What it does
Pushes platform events (for example ncr.raised, inspection.signed_off, approval.rejected, deadline.due) to external tools through background jobs with retry and payload signing. Exposes a system-to-system REST API using OAuth2 client credentials (PRD section 4, docs/spec/03-openapi.yaml). Syncs assets and work orders with client EAM/ERP systems, using the client register as master for tag numbers, and pushes inspection results and findings back to the client EAM as notifications or measurement documents. Every outbound destination must be approved by a tenant admin, and payloads are redacted by audience and team visibility so commercial or sensitive data does not leak into chat or external endpoints.

Features
- Public REST API /api/v1 with OpenAPI, OAuth2 client credentials, idempotency keys and rate limits
- Scoped API keys per project and module, with usage logs
- Outbound webhooks with HMAC signatures, retries, delivery log and replay
- Webhook payload redaction profiles by audience (summary-only option for chat and external endpoints)
- Teams and Slack notifications; email digests
- Outbound destination approval workflow by tenant admin, with per-tenant allowlist and SSRF checks
- iCal feeds for inspection and shutdown schedules; feed tokens revoke on user deactivation
- ERP/EAM connectors (SAP PM, Maximo) for work orders and assets, with field mapping, transformation and conflict rules, and bulk and incremental sync
- Push of inspection results and findings back to client EAM as notifications or measurement documents
- Integration health page with failed delivery queue and replay, and health alerts
- Integration audit log
- Client credentials held in a secrets manager and rotated

Interactions
- Comments, mentions and notifications: notification channels
- Asset hierarchy and registers: asset sync
- Scopes of work (RSW), disciplines and tasks: work orders
- Security and compliance programme: external exposure controls
- Users and projects: connectors are configured per project; feed tokens tied to users
- Domain events: subscriptions consume events and deliver via jobs

Data
- Connector: type, project, credentials reference (secrets store), approval status
- Subscription: event types, filters, audience redaction profile
- Delivery log: attempts, status, response, replayable
- iCal feed token: user, scope, revoked flag
- API client and API key: scopes by project and module, usage log
- Approved destination (allowlist entry): tenant, host/URL, approver, date
- Field mapping and conflict rule sets per ERP/EAM connector
- Sync state records (incremental cursors, conflicts)
- Integration audit log entries

Pages
- Connector setup per project
- Subscription matrix (events by destination)
- Delivery log with replay
- Integration health page with failed delivery queue
- Destination approval and allowlist admin
- API keys and usage
- Field mapping and conflict resolution for connectors

Decisions and notes
- Owner accepted: asset and work order sync with field mapping and conflict rules; push-back of results to client EAM; scoped API keys with usage logs; redaction profiles; health page with replay; destination approval workflow with allowlist and SSRF checks.
- Client asset registers are master for tag numbers.
- FastAPI provides OpenAPI automatically.
- SAP PM and Maximo connectors are likely per-customer projects rather than core; Telegram is listed in the current features but advisors consider it unacceptable for IRAP or Rio Tinto data and competitors skip it (see open questions).
- Priority channels: Teams, email, iCal and signed webhooks.
- Possible later patterns raised by the competitor review: SharePoint, Power BI and Maximo/SAP export for mining clients.
- Terminology must be renamable per market.

Open questions
- Keep or drop Telegram? Current text lists it; security and competitor advisors recommend dropping it; the owner has not decided.
- Are SAP PM and Maximo connectors core product or per-customer delivery projects (tech stack advisor says per-customer; owner accepted the sync feature but not this scoping)?
- Are SharePoint and Power BI export patterns in scope?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
