# Page specs for `integrations`

#### Integrations overview and health `/admin/integrations` (Integrations & webhooks)

See the status of all connectors, subscriptions and failing deliveries at a glance.

- **layout**: Dashboard with status tiles and a failed delivery queue below.
- **sections**:
  - Connector status tiles
  - Delivery success rate
  - Failed delivery queue
  - Health alerts
  - Recent integration audit entries
- **actions**:
  - Open connector
  - Replay failed delivery
  - Replay selected
  - Acknowledge alert
  - Open audit log
- **access**: Tenant admin and integration admin; project admins see their own project's connectors.

#### Connector list and setup `/p/:projectId/integrations/connectors` (Integrations & webhooks)

Configure per-project connectors to EAM/ERP and chat systems.

- **layout**: List with a stepped setup wizard in a side sheet.
- **sections**:
  - Connector list (type, status, approval, last sync)
  - Setup wizard (type, credentials reference, scope)
  - Approval status
  - Test connection
- **actions**:
  - Add connector
  - Test connection
  - Pause or resume
  - Rotate credentials
  - Delete
- **access**: Project admin with integration permission; new external destinations require tenant admin approval.

#### Field mapping and conflict rules `/p/:projectId/integrations/connectors/:connectorId/mapping` (Integrations & webhooks)

Define how client EAM fields map to AIP fields and how conflicts resolve.

- **layout**: Two-column mapping editor with a rules panel and a conflict queue tab.
- **sections**:
  - Source and target field mapping
  - Transformations
  - Conflict rules (client register is master for tags)
  - Sample record preview
  - Conflict queue
- **actions**:
  - Map field
  - Add transformation
  - Set conflict rule
  - Run dry-run sync
  - Resolve conflict
  - Run bulk or incremental sync
- **access**: Project admin and integration admin; conflict resolution available to asset managers.

#### Sync state and history `/p/:projectId/integrations/connectors/:connectorId/sync` (Integrations & webhooks)

Monitor sync runs, cursors and errors.

- **layout**: Table of runs with a detail drawer.
- **sections**:
  - Run history
  - Cursor state
  - Per-record errors
  - Counts created, updated, conflicted
- **actions**:
  - Start sync
  - Retry failed records
  - Reset cursor (confirmed)
  - Download error report
- **access**: Project admin and integration admin.

#### Subscription matrix `/admin/integrations/subscriptions` (Integrations & webhooks)

Choose which events go to which approved destinations and with what redaction.

- **layout**: Matrix grid of events by destination, with a filter side panel.
- **sections**:
  - Event by destination matrix
  - Filters (project, discipline, team)
  - Redaction profile per subscription
  - Payload preview
- **actions**:
  - Toggle subscription
  - Set filter
  - Choose redaction profile
  - Send test event
- **access**: Tenant admin and integration admin; project admins for project-scoped subscriptions.

#### Delivery log `/admin/integrations/deliveries` (Integrations & webhooks)

Audit and replay outbound deliveries.

- **layout**: Filterable table with a payload and response drawer.
- **sections**:
  - Filters (status, destination, event, date)
  - Delivery table
  - Attempt history
  - Signed payload and response viewer
- **actions**:
  - Replay
  - Bulk replay
  - Copy delivery ID
  - Export log
- **access**: Tenant admin and integration admin; payload view is masked per permission.

#### Destination approval and allowlist `/admin/integrations/destinations` (Integrations & webhooks)

Approve outbound destinations and keep the allowlist.

- **layout**: Two tabs: pending requests and approved allowlist.
- **sections**:
  - Pending requests (requester, host, purpose)
  - Allowlist (host, approver, date)
  - SSRF check result
  - Approval history
- **actions**:
  - Approve
  - Reject
  - Revoke
  - Re-run SSRF check
  - Request new destination
- **access**: Tenant admin approves; integration admins request; auditors read-only.

#### API clients and keys `/admin/integrations/api` (Integrations & webhooks)

Manage system-to-system API access and review usage.

- **layout**: Client list with a detail page showing scopes and usage charts.
- **sections**:
  - API clients
  - Scopes by project and module
  - Key rotation and expiry
  - Usage log and rate limits
- **actions**:
  - Create client
  - Set scopes
  - Rotate secret (shown once)
  - Revoke
  - Export usage
- **access**: Tenant admin and integration admin.

#### Chat and email channels `/admin/integrations/channels` (Integrations & webhooks)

Set up Teams, Slack and email digests with audience redaction.

- **layout**: Card per channel with settings drawer.
- **sections**:
  - Teams and Slack channels
  - Email digest schedule
  - Redaction profile (summary-only option)
  - Test message
- **actions**:
  - Connect channel
  - Set redaction
  - Send test
  - Disconnect
- **access**: Tenant admin; project admins for project channels (subject to destination approval).

#### My calendar feeds `/me/calendar-feeds` (Integrations & webhooks)

Let users subscribe to inspection and shutdown schedules via iCal.

- **layout**: Simple list with copy-link controls.
- **sections**:
  - Available feeds
  - Scope selector (project, discipline)
  - Feed URL with token
  - Revoked feeds
- **actions**:
  - Create feed
  - Copy URL
  - Revoke
  - Regenerate
- **access**: Any authenticated user for feeds within their own project access; tokens revoke on deactivation.

#### Integration audit log `/admin/integrations/audit` (Integrations & webhooks)

Review changes to integration configuration and credentials.

- **layout**: Filterable audit table with a detail drawer.
- **sections**:
  - Filters
  - Audit table
  - Before/after detail
- **actions**:
  - Filter
  - Export
- **access**: Tenant admin, security and auditors (read-only).
