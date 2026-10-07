# Page specs for `ingestion`

#### Ingestion dashboard `/ingestion` (Inbound capture & connectors)

Show intake health: quarantined, failed and unfiled counts with ageing alerts.

- **layout**: Dashboard with KPI tiles on top, ageing chart and alert list below, and a connector health strip.
- **sections**:
  - Counts by state (quarantined, failed, unfiled)
  - Ageing alerts
  - Connector health summary
  - Recent runs
- **actions**:
  - Drill into queue
  - Acknowledge alert
  - Run now
- **access**: ingestion.view; project-scoped data filtered by policy service; module hidden unless enabled for tenant

#### Connector list `/ingestion/connectors` (Inbound capture & connectors)

List connectors with schedule and health status.

- **layout**: DataTable with status chips and a row action menu.
- **sections**:
  - Filters by type, project and status
  - Table: type, target, project, schedule, last run, health
- **actions**:
  - Create
  - Pause/resume
  - Run now
  - Test connection
  - Open run log
- **access**: ingestion.manage for actions; ingestion.view to read

#### Connector setup wizard `/ingestion/connectors/new` (Inbound capture & connectors)

Create or edit a connector and verify it before enabling.

- **layout**: Stepper wizard with a test-result side panel; edit reuses the same steps.
- **sections**:
  - Type (watched folder, S3, SharePoint, email)
  - Target and credentials reference
  - Project, default category and asset
  - Schedule
  - Data minimisation (file types, max size, path filters, source retention)
  - Test connection result
  - Review
- **actions**:
  - Test connection
  - Save draft
  - Enable
  - Cancel
- **access**: ingestion.manage; secrets are write-only and never displayed

#### Run log `/ingestion/connectors/:id/runs` (Inbound capture & connectors)

Show import runs with failures and duplicates.

- **layout**: Master-detail: run table with a detail drawer.
- **sections**:
  - Run table with counts and errors
  - Failed and duplicate file list
  - Error detail
- **actions**:
  - Retry failed
  - Open imported file
  - Export log
- **access**: ingestion.view; retry needs ingestion.manage

#### Filing queue `/ingestion/filing-queue` (Inbound capture & connectors)

Let a person file or reject each inbound draft.

- **layout**: Three-pane: queue list, preview with scan and sender badges, and suggestion panel.
- **sections**:
  - Queue with filters (channel, sender trust, age)
  - Preview (sanitised email or document)
  - Provenance (sender, SPF/DKIM/DMARC, hash, channel)
  - Suggested project, asset, document type and thread
  - Certificate candidates from the mill-cert recogniser
- **actions**:
  - Assign to project or asset
  - File
  - Reject
  - Mark as duplicate or new version
  - Confirm certificate candidate
  - Bulk assign
- **access**: ingestion.file, scoped to the user's projects; nothing files automatically

#### Import queue (unmatched) `/ingestion/import-queue` (Inbound capture & connectors)

Triage items that could not be matched to a project or asset.

- **layout**: DataTable with bulk selection and a right-hand detail panel.
- **sections**:
  - Unmatched items
  - Reason for no match
  - Sender trust
  - Quarantine state
- **actions**:
  - Assign to project or asset
  - Reject
  - Open in mapping screen
- **access**: ingestion.file

#### Mapping and review `/ingestion/mapping` (Inbound capture & connectors)

Review and correct learned mappings from sender and filename patterns.

- **layout**: Two-column: pattern rules table with an example preview.
- **sections**:
  - Sender and filename pattern rules
  - Default category and asset per rule
  - Sample matches
- **actions**:
  - Edit rule
  - Disable rule
  - Reprocess unmatched items
- **access**: ingestion.manage

#### Mailbox and alias settings `/ingestion/mailboxes` (Inbound capture & connectors)

Configure project aliases, allowed senders and sender trust.

- **layout**: List with a detail form and a trust results panel.
- **sections**:
  - Aliases per project
  - Allow-list and verified domains
  - SPF/DKIM/DMARC results
  - Rate limits
  - Webhook and chat channels with HMAC settings
- **actions**:
  - Create alias
  - Add sender or domain
  - Verify domain
  - Rotate webhook secret
  - Upload .eml
  - Disable alias
- **access**: ingestion.manage; tenant admin for domain verification

#### Site agents `/ingestion/agents` (Inbound capture & connectors)

Enrol and monitor outbound-only agents on site laptops and instrument export folders.

- **layout**: DataTable with an enrolment dialog.
- **sections**:
  - Enrolled agents and last check-in
  - Allow-listed destinations
  - Enrolment code
- **actions**:
  - Enrol
  - Revoke
  - Edit destinations
- **access**: ingestion.manage
