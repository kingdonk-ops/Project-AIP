# Architecture & module boundaries (`arch`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
The structural blueprint of the product: how it is split into bounded contexts, how modules talk to each other, and how code is organised so a change usually touches one place. It is a modular monolith: one deployable API, internally split into strict modules, plus a separate worker process and a Python sidecar used only for heavy file processing (IFC, CAD, OCR). AIP, the existing working product (FastAPI, async SQLAlchemy, Postgres/PostGIS, React/Vite/TypeScript, 48 build phases done), is already a modular monolith. The owner has decided on a TypeScript rebuild, which supersedes the earlier advisor view of continuing the Python AIP backend; the module boundaries, engines and conventions below carry over to the rebuild. OpenConstructionERP (AGPL-3.0) is a feature reference only.

What it does
Modules never import each other's internals. They call published service interfaces or react to domain events delivered from a transactional outbox. Shared engines are built once and consumed by every module, so no module invents its own status model or audit trail. Data comes first and documents second: PDFs are rendered views of structured data, never the system of record. Every record carries tenant_id, project_id and optional asset_id so history follows the asset. A new or changed module edits only its own folder and manifest; cross-module effects are added as event subscribers, not imports.

Features
- About 8 bounded contexts: Identity & Tenancy, Asset & Project Core, Inspection & Quality, Documents & Records, Commercial, Field Ops, Safety & Compliance, Platform
- Shared engines: one workflow/approval engine, one form-schema engine (JSONLogic expressions), one rules engine, one audit log, one notification service, one file pipeline
- Transactional outbox (domain_events), written in the same transaction as the state change, feeding notifications, timeline, search indexing, deadlines and claims evidence. A dispatcher in the worker polls with SKIP LOCKED, fans out to subscribers, retries and dead-letters. Background jobs run on a Redis queue (arq or Celery as decided)
- Domain-event catalogue with versioned schemas (typed name, version, validated payload), replay and a dead-letter view, so timeline, search, deadlines and claims evidence can be rebuilt after a bug (accepted)
- Universal record-link service (record_type, record_id, asset_id) so any record can be related to any other record and to an asset, giving a traceable chain such as defect to NCR to repair to re-inspection (accepted)
- Workflow definition versioning with in-flight pinning, so changing an approval flow does not alter records already mid-review; each record table pins workflow_definition_id and version in its own module (accepted)
- Tenant configuration bundle: export, diff and import of templates, types, workflows, terms and rules as one versioned package, for cloning a setup into a new market or customer and promoting sandbox to production (accepted)
- Module capability manifest per module (permissions, events, settings, terminology keys), checked in CI (accepted)
- Asset-scoped rollup service computing counts and status per ltree node, cached and invalidated by events, for tree badges and dashboards on large hierarchies (accepted)
- Import-boundary lint; modules may import only other modules' service, schemas and events packages
- Per-tenant feature flags for deferred modules (BIM, AI), used as a router guard
- Entity registry pattern already proven in AIP: content type > category > item type > record
- Tenant terminology dictionary so terms are renamable per market (for example Variation vs Change Order); en-AU only at launch, other packs as data later
- Module scaffolder from a template with router, service, models, schemas, events, permissions, manifest and tests; frontend module template with routes, api, components, hooks and an index.ts as the only entry point
- Request context carrying tenant_id, project_id, actor and asset subtree scope

Interactions
- Database & schema conventions: this module defines the conventions every module follows
- Tech stack: chooses the languages and frameworks implementing the boundaries
- Workflow & approvals engine: the single engine all record types use
- Form & template designer: the single form engine for inspections, permits and checklists
- Audit trail, activity & timeline: every module emits events into the one audit trail

Data
- domain_events outbox: tenant_id, project_id, asset_id, event_name, event_version, aggregate_type, aggregate_id, JSONB payload validated by the event catalogue, actor_id (null for system events), occurred_at, published_at, attempts, dead_lettered_at, last_error. RLS forced. Append-only: no UPDATE of payload, dispatcher grant limited to publish and attempt columns. Partial index on unpublished, non-dead-lettered rows (tenant_id, occurred_at); further indexes on aggregate, asset and event name; consider monthly partitioning
- workflow_definitions table (versioned)
- Record-link table (record_type, record_id, asset_id)
- Denormalised asset_id on every row, the established AIP activity rollup pattern
- module_manifests is a global reference table and the only tenant_id exception, documented in a CI allow-list
- Reuses assets, entity_types, inspections, issues, documents, tasks
- Key components: event outbox writer, dispatcher, event registry, module registry (loads manifests, mounts routers, checks dependencies), feature flags, worker entrypoint (queue consumers, outbox dispatcher, scheduled jobs), sidecar called via job queue and signed callbacks. Exact file paths follow the TypeScript layout
- Settings: dispatcher poll interval and batch size, retry count and backoff, dead-letter alert threshold, event retention, per-tenant feature flags, bundle import approval required, rollup cache TTL and invalidation mode

Pages
- Domain event catalogue (/admin/platform/events): filters by module, status, failures and version; columns for version, owner, schema, subscribers, published and failed in 24h; row actions view schema, recent events, replay range, deprecate; export CSV; register event form
- Event detail (/admin/platform/events/:eventName): overview, payload schema, subscribers and health, recent changes and ADR references
- Dead-letter queue (/admin/platform/events/dead-letter): retry, discard with reason, export, error and payload drawer
- Replay jobs (/admin/platform/events/replay): form with event, version, range, subscriber and dry run; impact preview; job history
- Tenant configuration bundle export, diff and import, with approval when the setting is on
- Generated module map of contexts, modules, events and dependencies
- Per-tenant feature flag settings
- Notifications: dead-letter threshold exceeded, replay finished, workflow version published, bundle import completed, feature flag changed, CI import or manifest failure

Decisions and notes
- Owner decisions win: TypeScript rebuild (replacing the earlier ADR 0001 continue-AIP direction, which should be rewritten accordingly), Next.js frontend, Redis queue, JSONLogic, Postgres FTS plus pgvector, pooled tenancy at launch, snapshot tables with tenant_id and RLS for reporting read models
- Status today: domain_events and workflow_definitions are in the spec (PRD section 7) but not built; status flows are hardcoded in AIP
- The six feature suggestions above are accepted
- A different transport could replace the Postgres dispatcher later; hash chaining of audit tables is left to the audit module

Open questions
- Monolith vs split report renderer (PRD section 13); Gotenberg is chosen for PDF rendering, but the process split is not settled
- Sandbox for scripts (PRD section 13)
- Response history model (PRD section 13)
- Advisors suggested an append-only, hash-chained audit log anchored to S3 Object Lock, with audit permissions separate from application admin; the owner has not decided whether this is in scope
- Advisors suggested dropping pipelines, compliance_ai and eac in v1, and phasing delivery (phase 1 vertical slice for Kaefer on Rio Tinto remediation); the owner has not decided
- Outbox transport: Postgres polling dispatcher (current design) vs BullMQ/SNS (advisor); with the TypeScript rebuild and Redis queue now chosen, whether to adopt BullMQ is undecided

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
