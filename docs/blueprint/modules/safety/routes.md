# Page specs for `safety`

#### Incident register `/projects/:projectId/safety` (Safety & HSE)

List incidents, near misses and observations with severity, risk and notifiable status.

- **layout**: DataTable with a filter bar, a Quick report button and a bulk action bar.
- **sections**:
  - Filters (type, severity, status, site, notifiable, date range, risk band)
  - Table (report no., type, date and time, site, asset, severity, risk score, status, notifiable, reporter)
  - Bulk action bar
  - Empty state
- **actions**:
  - Quick report
  - Open
  - Investigate
  - Add corrective action
  - Mark notifiable
  - Close
  - Export (masked)
  - Assign investigator
- **access**: safety.view for the basic register. Reporting is open to all site users. Injury fields appear only with safety.sensitive.read.

#### Report incident or observation `/projects/:projectId/safety/new` (Safety & HSE)

Capture a report with photos, location, asset and risk scoring.

- **layout**: Single-column form with a sticky save bar. It has a simplified mobile variant.
- **sections**:
  - Type, date and time
  - Site and asset
  - Description and photos
  - Likelihood and consequence with live risk band
  - People involved (masked)
  - Injury details (restricted)
  - Immediate actions
- **actions**:
  - Save draft
  - Submit
  - Attach photo
- **access**: Any authenticated site user. Restricted fields are shown only to HSE roles.

#### Incident detail and investigation `/projects/:projectId/safety/:reportId` (Safety & HSE)

Review a report, assess risk, investigate, manage corrective actions and the regulator timeline.

- **layout**: Header with the WorkflowBar. The body is tabbed and a regulator timeline banner sits above when the report is notifiable.
- **sections**:
  - Summary and classification
  - Risk assessment
  - Location, asset and diary link
  - People involved (masked)
  - Injury and health details (restricted)
  - Photos and evidence
  - Investigation
  - Corrective actions
  - Regulator notification timeline
  - Audit trail
- **actions**:
  - Advance workflow
  - Edit risk score
  - Assign investigator
  - Add corrective action
  - Mark notifiable
  - Record regulator notification
  - Close
- **access**: Reporter sees their own submission. HSE roles see all. Masked fields are server-side filtered, and legal hold blocks deletion.

#### Corrective actions `/projects/:projectId/safety/actions` (Safety & HSE)

Show actions raised from safety reports, using the shared issues and CAPA engine.

- **layout**: Table with a board toggle.
- **sections**:
  - Filters (owner, status, overdue, source)
  - Actions table
  - Board view
- **actions**:
  - Open action
  - Reassign
  - Close
  - Export
- **access**: safety.view. Close follows the issues module rules.

#### HSE KPIs `/projects/:projectId/safety/kpis` (Safety & HSE)

Show TRIR, LTIFR and observation rate with the hours worked source.

- **layout**: Dashboard with KPI tiles and trend charts.
- **sections**:
  - KPI tiles (TRIR, LTIFR, observations per 200k hours)
  - Trend charts
  - Hours worked source and gaps
  - Leading versus lagging indicators
- **actions**:
  - Change period
  - Export
  - Open source records
- **access**: safety.kpi.view

#### Permits to work (advanced) `/projects/:projectId/safety/advanced/permits` (Safety & HSE)

Issue and track permits where HSE Advanced is enabled for the site.

- **layout**: Register table with a status board toggle.
- **sections**:
  - Filters (type, status, expiring)
  - Permit table
  - Board view
- **actions**:
  - Create permit
  - Issue
  - Suspend
  - Close
  - Check holder competency
- **access**: Site with HSE Advanced enabled. Permit authorities have safety.permit.manage.

#### JSAs and toolbox talks (advanced) `/projects/:projectId/safety/advanced/jsa` (Safety & HSE)

Record JSA/JHA documents and toolbox talks with attendance.

- **layout**: Two tabs, each with a list and a form built on the form renderer.
- **sections**:
  - JSA list
  - Toolbox talk list with attendance
  - Attendance capture
- **actions**:
  - Create JSA
  - Record toolbox talk
  - Capture attendance
  - Export
- **access**: Site with HSE Advanced enabled. Supervisors can create, all workers can sign.

#### PPE issue register (advanced) `/projects/:projectId/safety/advanced/ppe` (Safety & HSE)

Track PPE issued to people.

- **layout**: Table with a quick issue drawer.
- **sections**:
  - PPE issue table
  - Issue drawer
- **actions**:
  - Issue PPE
  - Return
  - Export
- **access**: Site with HSE Advanced enabled. HSE roles manage.

#### HSE audits (advanced) `/projects/:projectId/safety/advanced/audits` (Safety & HSE)

Run HSE audits using templates and track findings.

- **layout**: List with audit detail built on the audit shell.
- **sections**:
  - Audit list
  - Checklist
  - Findings and CAPA
- **actions**:
  - Plan audit
  - Run checklist
  - Raise corrective action
- **access**: Site with HSE Advanced enabled. HSE auditors.

#### Safety settings `/settings/safety` (Safety & HSE)

Configure the risk matrix, incident types, notifiable rules, masking roles and the advanced pack per site.

- **layout**: Settings page with sections and a site switch table.
- **sections**:
  - Enable HSE Advanced per site
  - Risk matrix definition
  - Incident types and severities
  - Notifiable criteria and deadlines
  - Field masking roles
  - Hours worked source
  - Retention and legal hold
  - Escalation recipients
- **actions**:
  - Toggle advanced pack for a site
  - Edit matrix
  - Save
- **access**: Tenant admin or safety.settings.manage

#### Mobile quick report `/m/safety/quick-report` (Safety & HSE)

Log an incident, near miss or observation in a few taps, working offline.

- **layout**: Mobile full-screen form with a large photo button and a bottom submit bar.
- **sections**:
  - Type selector
  - Photo capture
  - Location and asset (auto-filled where possible)
  - Short description
  - Quick risk score
  - Offline sync indicator
- **actions**:
  - Capture photo
  - Submit
  - Save offline
  - Add detail later
- **access**: Any authenticated site user. Submissions are idempotent on sync.
