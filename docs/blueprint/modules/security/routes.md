# Page specs for `security`

#### Compliance dashboard `/security/compliance` (Security & compliance programme)

Control status and evidence overview, showing proven vs specified.

- **layout**: KPI cards above control and framework views
- **sections**:
  - Framework coverage (SOC 2, ISO 27001, ISM, APP)
  - Evidence overdue
  - Proven vs specified
  - Programme timeline
- **actions**:
  - Filter by framework
  - Export control matrix
  - Open control
- **access**: Security lead and compliance admin; auditors read-only

#### Controls `/security/controls` (Security & compliance programme)

Control catalogue with framework mappings and evidence.

- **layout**: DataTable with detail drawer
- **sections**:
  - Controls table
  - Mapping editor
  - Evidence history
- **actions**:
  - Create control
  - Assign owner
  - Add evidence
  - Edit mapping
  - Mark not applicable
- **access**: Security lead edit; others read-only

#### Evidence `/security/evidence` (Security & compliance programme)

Collected evidence items per control and period.

- **layout**: DataTable with filters
- **sections**:
  - Evidence table (source, collected, period, status)
  - Upload evidence form
- **actions**:
  - Add evidence
  - Download
  - Mark reviewed
- **access**: Security lead and control owners

#### Access reviews `/security/access-reviews` (Security & compliance programme)

Quarterly review of users, roles and teams with sign-off.

- **layout**: Review list and per-review checklist
- **sections**:
  - Review cycles
  - User, role and team rows with keep or revoke
  - Sign-off panel
- **actions**:
  - Start review
  - Keep
  - Revoke
  - Sign off
  - Export
- **access**: Designated reviewers; tenant admin

#### Breach register `/security/breaches` (Security & compliance programme)

Log incidents and track NDB assessment and notification clock.

- **layout**: Register plus incident detail with timeline
- **sections**:
  - Incident table
  - NDB assessment form
  - Notification clock
  - Contacts
- **actions**:
  - Log incident
  - Assess
  - Mark notified
  - Close
- **access**: Security lead and privacy officer

#### Data map and classification `/security/data-map` (Security & compliance programme)

Privacy data map and classification tags driving masking and AI residency.

- **layout**: DataTable with tag editor
- **sections**:
  - Data map entries
  - Classification tags (public, internal, sensitive, health)
  - Masking rules
- **actions**:
  - Add entry
  - Edit tag
  - Edit masking rule
- **access**: Security lead and privacy officer

#### Pen-test findings and restore tests `/security/pentests` (Security & compliance programme)

Track findings (release block on open highs) and restore test records.

- **layout**: Two tabs of tables
- **sections**:
  - Findings tracker
  - Restore test records
  - Vulnerability exceptions
- **actions**:
  - Add finding
  - Change status
  - Record restore test
  - Attach evidence
- **access**: Security lead; release manager read-only

#### Trust pack and provenance `/security/trust-pack` (Security & compliance programme)

Publish whitepaper, sub-processors, data-flow diagram and AGPL provenance log.

- **layout**: Document list with detail
- **sections**:
  - Trust documents
  - Sub-processor list
  - Provenance entries pending review
- **actions**:
  - Upload
  - Publish
  - Review provenance entry
- **access**: Security lead and legal reviewer

#### Tenant security settings `/settings/security` (Security & compliance programme)

Tenant IP allow-list, session and MFA policy, alert views.

- **layout**: Settings form with alerts tab
- **sections**:
  - IP allow-list
  - Session timeout and MFA policy
  - Bulk-export and anomalous-access alerts
- **actions**:
  - Save
  - Add IP range
  - Acknowledge alert
- **access**: Tenant admin
