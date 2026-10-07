# Database & schema conventions (`database`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
The data layer for the platform: the core tables, the conventions every table follows, and how the schema evolves. PostgreSQL is the single system of record. AIP already runs on PostgreSQL/PostGIS with forward-only Alembic migrations; this module defines the full target schema and closes the gaps between what is built and what is specified. Under the owner's TypeScript rebuild decision, the schema, RLS and migrations carry over, with Alembic raw-SQL migrations and templates kept.

What it does
- Stores every tenant's data in one pooled schema (pooled only at launch), with the tenant boundary enforced by the database (row-level security) rather than only by application code.
- Applies the same conventions to every table: tenant_id, uuid primary key, created/updated timestamps, sync_version for optimistic concurrency on offline-edited tables, deleted_at for soft delete where applicable, and asset_id where history follows the asset.
- Holds the asset hierarchy as an ltree path for fast subtree queries, and configurable data as JSONB validated server-side against a per-type schema.
- Keeps audit and sign-off tables append-only, so evidence cannot be altered by the application.
- Evolves the schema safely through forward-only raw-SQL migrations tested up-down-up in CI.
- New tables come from the migration template and mixins/helpers, so tenant_id, RLS and sync columns are never hand-written; CI blocks drift.

Features
- Core entities: organisations, projects, sites, content_types, entity_type_categories, entity_types, assets, inspection_templates, inspections, inspection_responses (append-only), issues, corrective_actions, documents, certificates, media, users, roles, user_roles, audit_log, workflow_definitions, report_templates, devices, sync_operations.
- tenant_id on every table with FORCE RLS. The app connects as a non-owner role without BYPASSRLS; a separate migrator role owns the schema. Tenancy is set per transaction with SET LOCAL app.tenant_id and the session fails closed if unset. Take care with PgBouncer or RDS Proxy so SET LOCAL behaves correctly.
- CI check fails if any new table lacks tenant_id, an RLS policy, FORCE RLS or required indexes. It also produces a schema-drift and RLS-coverage report retained as a CI artefact for SOC 2 evidence (accepted).
- Cross-tenant and IDOR tests across every table (Testcontainers).
- ltree path with GIST index for the asset hierarchy; JSONB attributes with GIN index.
- Hot-attribute promotion: admin-flagged JSONB attributes get generated columns or expression indexes (for example wall loss, coating type, insulation class) so filters stay fast without per-customer schema changes; delivered through item types (accepted).
- inspection_current_responses view: latest value per field, with full history retained.
- As-at queries: view an asset and its inspection state at a past date, backed by history tables (accepted).
- sync_version optimistic concurrency (409 on mismatch). Already enforced on assets (Phase 23); extended to inspections, issues, certificates and scopes, with 409 payloads carrying the current record (accepted).
- client_generated_id unique per tenant for idempotent offline sync.
- Soft delete (deleted_at) with recycle bin. Legal-hold flag at record, asset or project level blocks purge and crypto-shred jobs; an asset hold applies to the subtree via ltree (accepted).
- Append-only audit with REVOKE UPDATE/DELETE for the app role.
- Time-based partitioning with automated partition management for high-volume tables: responses, audit, sync_operations, activity (accepted).
- Expand/contract migrations for zero downtime, tested against a production-size snapshot.
- Partial unique index for one current revision per document group.
- Reporting read models use snapshot tables carrying tenant_id and RLS (decided).
- Tenant key scheme: shared key with tenant prefixes (decided).

Interactions
- Tenancy, organisations and data residency: RLS policies enforce the tenant boundary.
- Architecture and module boundaries: the schema mirrors the bounded contexts.
- Offline field app and sync: sync columns, client_generated_id and views support device sync; the frontend handles 409 conflicts with a shared conflict dialog offering merge or reload.
- Audit trail, activity and timeline: append-only audit tables.
- Content types, item types and attributes: JSONB attribute schemas.

Data
- Shared mixins or equivalents: tenant, timestamp, sync_version, soft delete, asset-scoped.
- Roles (migrations/roles.sql): migrator (owner), app (non-owner, no BYPASSRLS), readonly, plus append-only grants.
- Standard new-table migration template (migrations/templates/new_table.sql.tpl) including tenant_id, FORCE RLS policy, indexes and grants.
- Platform tables: schema_convention_exceptions (approved exceptions such as global reference tables, read by the CI check), rls_coverage_reports (commit, tables total, tables missing controls, per-table JSONB report, artefact key; append-only, linked to security evidence), legal holds (scope_type record/asset/project, scope_id, reason, matter reference, placed/released).
- Helpers: session (SET LOCAL per transaction), concurrency (409 on mismatch), ltree, JSONB schema validation.
- Reference files: docs/spec/01-database-schema.sql, docs/spec/02-erd.md (ERD per bounded context), docs/conventions/schema-conventions.md.
- Config not code: per-type JSONB attribute schemas, retention and legal-hold policy, recycle bin window.
- Settings: soft-delete retention days, recycle bin purge schedule, partition interval per table, hot-attribute approval required, slow-query threshold, database roles reference (read-only).
- Built in AIP: entity type registry, assets with ltree, inspections, disciplines/tasks tables, consumable_issuances, certificates (migration 0024), documents with revision groups, audit/activity log.

Pages
- Table convention coverage (/admin/platform/schema-coverage): per-table tenant_id, RLS, FORCE RLS, indexes, append-only grants and sync columns; re-run checks, export report, view policy and exceptions.
- Recycle bin (/recycle-bin): restore or purge soft-deleted records; purge blocked under legal hold.
- Legal holds (/admin/legal-holds): place and release holds with target picker and affected-records preview.
- Data retention settings (/admin/database/settings): retention, purge schedule, partition intervals, hot-attribute approvals, read-only roles reference.
- Concurrency conflict dialog: field-by-field diff with merge selected fields, reload current or cancel.
- Notifications: convention check failed in CI, partition creation failing, legal hold placed or released, purge scheduled, conflict resolved.
- Otherwise developer and CI tooling: convention checks, RLS isolation tests, up-down-up migration tests.

Decisions and notes
- Owner decisions: pooled tenancy only at launch; Alembic raw SQL with templates; Postgres FTS plus pgvector; snapshot tables with tenant_id and RLS for reporting; shared key with tenant prefixes.
- Owner accepted: sync_version extension, as-at queries, time partitioning, hot-attribute promotion, RLS-coverage CI artefact, and legal hold.
- Closure table is rejected for now; ltree is built.
- Phase 24 fixed a real cross-tenant isolation gap via org_scope join helpers; RLS makes this structural.
- Action: verify tenant_id and RLS on all existing AIP tables and confirm the app role is non-owner without BYPASSRLS. Keep migrations on the separate privileged role and make sure append-only tables cannot be altered by the app role. Validate JSONB against per-type schemas server-side.
- Tenancy must be settled now, because it cannot be retrofitted.
- Scope Redis keys, queues, S3 prefixes, search indexes and embeddings by tenant (workers and caches are the usual leak path).
- Suggested phase: P0.

Open questions
- Whether hash chaining of audit and evidence tables is required in this module or only in the audit module (suggested by the lead programmer and feature scout; advisor output leans to the audit module; no owner decision).
- Whether a siloed single-tenant stack is offered later for IRAP and mining customers; launch is pooled only, so this is deferred and affects deployment more than schema.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
