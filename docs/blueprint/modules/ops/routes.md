# Page specs for `ops`

#### My jobs drawer `(drawer)/jobs` (Operations, hosting & deployment)

Show the user's running and recent background jobs from any page.

- **layout**: Right-hand drawer opened from header icon; works on mobile as a bottom sheet
- **sections**:
  - Filter chips (running, completed, failed)
  - Job list with progress
- **actions**:
  - Open result
  - Cancel
  - Retry
  - Clear completed
- **access**: Any authenticated user (own jobs only)

#### Admin queue `/admin/jobs` (Operations, hosting & deployment)

View and manage all jobs and queue health.

- **layout**: DataTable with filters and detail drawer
- **sections**:
  - Queue health strip
  - Jobs table
  - Job detail (parameters, events, result, error, correlation ID)
- **actions**:
  - Retry
  - Cancel
  - Download result
  - Copy correlation ID
  - Bulk retry or cancel
- **access**: Tenant admin for own tenant; platform admin across tenants

#### Environments and deployments `/admin/ops/environments` (Operations, hosting & deployment)

Show environment health, versions and pipeline status.

- **layout**: Card grid plus deployments table
- **sections**:
  - Environment table (hosting, region, version, health, data class)
  - Pipeline status
  - SLOs and alerts
  - Recovery targets
- **actions**:
  - View deployment
  - Open status page
- **access**: Platform admin and engineering

#### Backups and restore evidence `/admin/ops/backups` (Operations, hosting & deployment)

Backup status and quarterly restore test records.

- **layout**: Status cards plus table
- **sections**:
  - Backup schedule and last result
  - Restore test evidence
  - PITR window
- **actions**:
  - Record restore test
  - Download evidence
  - Trigger backup
- **access**: Platform admin and security lead

#### Storage lifecycle `/settings/storage-lifecycle` (Operations, hosting & deployment)

Set defaults and per-project overrides while blocking expiry on evidence.

- **layout**: Settings form with JSON preview
- **sections**:
  - Defaults (tier transitions)
  - Project overrides
  - Rendered s3-lifecycle.json preview
  - Evidence no-expiry guard
- **actions**:
  - Save
  - Add override
  - Apply policy
- **access**: Super-admin with storage_lifecycle:manage

#### Ops settings `/admin/ops/settings` (Operations, hosting & deployment)

Configure job limits, error sink, backup and SLO thresholds.

- **layout**: Tabbed settings form
- **sections**:
  - Job types and limits
  - Tenant queue quotas
  - Client error limits
  - SLO thresholds
  - Sandbox reset schedule
- **actions**:
  - Save
  - Reset sandbox now
- **access**: Platform admin

#### Tenant cost and usage `/admin/ops/usage` (Operations, hosting & deployment)

Per-tenant storage, jobs and AI call reporting.

- **layout**: Chart and table report
- **sections**:
  - Usage by tenant
  - Trend charts
  - Quota status
- **actions**:
  - Export CSV
  - Change period
- **access**: Platform admin; tenant admin sees own tenant
