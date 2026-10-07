# Page specs for `qms`

#### Quality dashboard `/projects/:projectId/quality` (Quality roll-up & audits)

Read-only roll-up of ITP completion, open NCRs, punch ageing, first-time pass rate, cost of poor quality and audit status, with no copied data.

- **layout**: Dashboard grid of KPI tiles from the reporting layer. A filter bar sits on top with project, discipline, contractor and period. Tiles drill into source registers.
- **sections**:
  - Filter bar (project, site, discipline, subcontractor, period)
  - KPI tiles: ITP completion, open NCRs, punch ageing, FTPR, COPQ
  - FTPR breakdown by discipline, inspector and subcontractor
  - Audit status summary
  - Trend charts
  - Last refreshed and data-definition note
- **actions**:
  - Change filters
  - Drill into source register
  - Export tile as CSV or image
  - Save view
  - Schedule quality report
  - Customise tile layout (permitted roles)
- **access**: Users with quality.view on the project. Inspector-level FTPR is limited to quality managers and above. Portal users see only the tiles shared with them.

#### Cost of poor quality report `/quality/copq` (Quality roll-up & audits)

Show rework hours and cost from issues, grouped by COPQ category, discipline, subcontractor and period.

- **layout**: Report page with a filter header, summary cards, a stacked chart and a detail table.
- **sections**:
  - Filters
  - Summary cards (total cost, hours, count)
  - Cost by category chart
  - Cost over time
  - Detail table linking to issues
  - Cost source and rate basis note
- **actions**:
  - Filter
  - Open source issue
  - Export CSV
  - Schedule report
  - Print or PDF via the report engine
- **access**: quality.copq.view (quality managers, project managers, commercial). Cost rates are hidden from users without cost visibility.

#### First-time pass rate analysis `/quality/ftpr` (Quality roll-up & audits)

Analyse pass rates by discipline, inspector and subcontractor using the tenant's FTPR definition.

- **layout**: Split layout with a ranked chart on the left and a drill-down table on the right.
- **sections**:
  - Dimension selector
  - Ranked bar chart
  - Trend line
  - Failed inspections table
  - FTPR definition panel
- **actions**:
  - Switch dimension
  - Drill to inspections
  - Export CSV
- **access**: quality.view. The inspector dimension needs quality.inspector_metrics.

#### Audit register `/quality/audits` (Quality roll-up & audits)

List, filter and plan internal, external and supplier audits.

- **layout**: Standard register: DataTable with a filter bar, a bulk action bar and a Calendar toggle.
- **sections**:
  - Filters (type, standard, status, lead auditor, date)
  - Table (audit no., title, type, scope, standard, lead, auditee, planned date, status, findings, open findings)
  - Bulk action bar
  - Empty state
- **actions**:
  - Create audit
  - Open audit
  - Reassign lead auditor
  - Reschedule
  - Cancel planned audits
  - Export CSV
  - Switch to planner
- **access**: quality.audit.view. Create and edit need quality.audit.manage. Auditee contacts see only audits where they are the auditee.

#### Audit planner `/quality/audits/planner` (Quality roll-up & audits)

See and schedule audits over the year against the audit programme.

- **layout**: Calendar with month and year views and a side panel of unscheduled audits.
- **sections**:
  - Calendar
  - Unscheduled audits panel
  - Filters
  - Auditor workload strip
- **actions**:
  - Drag to reschedule
  - Create audit from date
  - Filter by auditor or type
- **access**: quality.audit.manage

#### Create or edit audit `/quality/audits/new` (Quality roll-up & audits)

Capture the audit plan, scope, clauses, team and checklist.

- **layout**: Single-column form in a page with a sticky save bar.
- **sections**:
  - Title, type and standard
  - Clauses in scope
  - Project, site and auditee
  - Lead auditor and team
  - Planned date
  - Scope notes
  - Checklist template
- **actions**:
  - Save draft
  - Save and schedule
  - Cancel
- **access**: quality.audit.manage. Edit is locked once the audit is closed.

#### Audit detail `/quality/audits/:auditId` (Quality roll-up & audits)

Run an audit from planning through checklist, findings and closure.

- **layout**: Header with the WorkflowBar and tabbed body. The right rail shows the team and key dates.
- **sections**:
  - Audit summary and status
  - Scope and clauses
  - Audit team and auditee
  - Checklist and evidence
  - Findings and linked issues
  - Closure and verification
  - Attachments
  - Activity and audit trail
  - Dashboard snapshot
- **actions**:
  - Advance workflow
  - Complete checklist items
  - Add finding
  - Raise issue or NCR from finding
  - Verify closure
  - Close audit
  - Generate audit report
  - Add attachment
- **access**: Lead auditor, audit team and quality managers. The auditee gets a read-only view of findings and responses once the audit is issued.

#### Finding tracker `/quality/findings` (Quality roll-up & audits)

Track findings across all audits with links to their issues and corrective actions.

- **layout**: DataTable with a status board toggle (kanban by status).
- **sections**:
  - Filters (classification, status, owner, overdue, clause)
  - Findings table
  - Board view
  - Linked issue status column
- **actions**:
  - Open finding
  - Raise issue
  - Reassign
  - Verify closure
  - Export CSV
- **access**: quality.audit.view. Verify closure is limited to auditors.

#### Management reviews and objectives `/quality/management-reviews` (Quality roll-up & audits)

Record management reviews and quality objectives with the evidence behind them.

- **layout**: Two tabs, each a list with a detail drawer.
- **sections**:
  - Management review list
  - Quality objectives list with current KPI value
  - Review detail drawer with inputs, outputs and actions
- **actions**:
  - Create review
  - Add objective
  - Link KPI
  - Attach minutes
  - Export evidence pack
- **access**: quality.manage

#### Quality settings `/settings/quality` (Quality roll-up & audits)

Configure audit types, clause library, COPQ categories and rates, FTPR definition and defaults.

- **layout**: Settings page with a left sub-navigation and one form per section.
- **sections**:
  - Audit types and standards
  - ISO clause library
  - COPQ categories and cost rates
  - Cost source selection
  - FTPR definition
  - Finding classification and due-date defaults
  - Dashboard tile defaults
  - Scheduled report recipients
  - Audit numbering
- **actions**:
  - Edit and save
  - Import clause library
  - Preview FTPR on sample data
- **access**: Tenant admin or quality.settings.manage

#### Mobile audit checklist `/m/quality/audits/:auditId` (Quality roll-up & audits)

Let auditors run a checklist and log findings on site, including offline.

- **layout**: Single-column mobile screen with a stepper and a bottom action bar.
- **sections**:
  - Checklist items with pass, fail and N/A
  - Evidence photo capture
  - Quick finding form
  - Sync status
- **actions**:
  - Answer item
  - Capture photo
  - Add finding
  - Submit checklist
- **access**: Audit team members assigned to the audit
