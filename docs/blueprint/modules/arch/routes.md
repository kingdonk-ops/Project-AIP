# Page specs for `arch`

#### Domain event catalogue `/admin/platform/events` (Architecture & module boundaries)

Register of all versioned domain events, their owners, subscribers and 24h health.

- **layout**: Full-width DataTable with filter bar and right-hand detail drawer
- **sections**:
  - Filter bar (module, status, has failures, version)
  - Catalogue table (event, version, owning module, schema, subscribers, published 24h, failed 24h, status)
  - Schema viewer drawer
  - Recent events panel
- **actions**:
  - Search
  - Export catalogue CSV
  - Mark deprecated
  - View schema
  - View recent events
  - Replay range
  - Register event (create form)
- **access**: Platform admin and developers; tenant admins read-only for their own tenant's events

#### Event detail `/admin/platform/events/:eventName` (Architecture & module boundaries)

Inspect one event: schema, subscribers, throughput and failures.

- **layout**: Two-column detail with tabs
- **sections**:
  - Overview and bounded context
  - Published interface and payload schema
  - Subscribers and health
  - Recent changes and ADR references
- **actions**:
  - Replay range
  - Deprecate
  - Copy schema reference
- **access**: Platform admin and developers

#### Dead-letter queue `/admin/platform/events/dead-letter` (Architecture & module boundaries)

Triage events that exhausted retries.

- **layout**: DataTable with bulk toolbar and error detail drawer
- **sections**:
  - Summary strip (count, oldest, alert threshold)
  - Table (event ID, event, subscriber, attempts, last error, first failed, tenant, status)
  - Error and payload drawer
- **actions**:
  - Retry selected
  - Discard with reason
  - Export
  - Open related event
- **access**: Platform admin; tenant admin sees own tenant rows only

#### Replay jobs `/admin/platform/events/replay` (Architecture & module boundaries)

Request and monitor replay of events to rebuild timeline, search or deadlines.

- **layout**: Wizard form plus job history table
- **sections**:
  - Replay form (event, version, range, subscriber, dry run)
  - Impact preview
  - History of replay jobs with status
- **actions**:
  - Start replay
  - Cancel
  - View result
- **access**: Platform admin with replay permission

#### Tenant configuration bundles `/admin/config-bundles` (Architecture & module boundaries)

Export, diff and import versioned bundles of templates, types, workflows, terms and rules.

- **layout**: Tabbed page: Export, Import and diff, History
- **sections**:
  - Export selector (component types to include)
  - Import upload with validation result
  - Side-by-side diff with change summary
  - Approval step if required
  - Bundle history
- **actions**:
  - Export bundle
  - Upload and validate
  - Review diff
  - Approve and apply
  - Roll back
  - Promote sandbox to production
- **access**: Tenant admin; import requires approval role when setting is on

#### Workflow definitions `/admin/workflows` (Architecture & module boundaries)

List versioned workflow definitions with in-flight pinning counts.

- **layout**: DataTable with version history drawer
- **sections**:
  - Definitions table (record type, version, status, in-flight records)
  - Version history
  - Publish confirmation showing pinned in-flight count
- **actions**:
  - Create version
  - Publish
  - Compare versions
  - Retire
- **access**: Workflow owners and tenant admin

#### Module map and feature flags `/admin/platform/modules` (Architecture & module boundaries)

View modules, dependencies and manifest status; toggle per-tenant feature flags.

- **layout**: Split view: dependency graph left, module list with flags right
- **sections**:
  - Generated module map by bounded context
  - Manifest and import-lint status
  - Feature flag toggles (BIM, AI, deferred modules)
  - Rollup cache settings
- **actions**:
  - Toggle flag
  - Open manifest
  - Download module-map.md
- **access**: Platform admin; tenant admin can toggle flags for own tenant

#### Platform settings `/admin/platform/settings` (Architecture & module boundaries)

Configure outbox and rollup behaviour.

- **layout**: Single-column settings form
- **sections**:
  - Dispatcher poll interval and batch size
  - Retry and backoff
  - Dead-letter alert threshold
  - Event retention
  - Rollup cache TTL and invalidation mode
- **actions**:
  - Save
  - Reset to defaults
- **access**: Platform admin
