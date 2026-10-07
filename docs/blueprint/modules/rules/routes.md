# Page specs for `rules`

#### Rules register `/settings/rules` (Rules & validation engine)

List and manage rules by target record, use, severity and rule set.

- **layout**: DataTable with a filter bar and bulk action bar.
- **sections**:
  - Filters (target type, use, severity, status, rule set, project)
  - Table (rule key, name, target, use, severity, rule set, version, status, last evaluated, 30-day fail count)
  - Bulk action bar
  - Empty state
- **actions**:
  - Create rule
  - Edit
  - Test
  - Duplicate
  - View versions
  - Activate or deactivate
  - Delete draft
  - Move to rule set
  - Export JSON
- **access**: rules.view for read. rules.author to create or edit. rules.publish to activate.

#### Rule editor `/settings/rules/:ruleId` (Rules & validation engine)

Define a rule's expression, message and severity, test it, and see where it is used.

- **layout**: Two-pane editor with the definition form on the left and the test panel on the right.
- **sections**:
  - Definition (target, expression, message, severity)
  - Expression editor with field and context-provider picker
  - Test panel with sample records and expected result
  - Version history and diff
  - Where used (forms, transitions, report pre-flight)
  - Evaluation results and trends
  - Waivers
  - Audit trail
- **actions**:
  - Save draft
  - Run test
  - Save test case
  - Publish (requires passing tests if enabled)
  - Rollback to version
  - Duplicate
- **access**: rules.author. Publish needs rules.publish. Expression errors are shown inline.

#### Rule sets `/settings/rule-sets` (Rules & validation engine)

Manage versioned rule sets at tenant and project level, and their assignment.

- **layout**: List with a detail drawer showing members and assignments.
- **sections**:
  - Rule set list (name, level, version, status)
  - Members
  - Assignments to record types, projects and transitions
  - Version history
- **actions**:
  - Create rule set
  - Publish new version
  - Rollback
  - Assign to project or workflow transition
  - Export
- **access**: rules.publish. Project-level sets can be managed by project admins when delegated.

#### Requirements register `/settings/rules/requirements` (Rules & validation engine)

Hold entity, attribute and constraint triplets extracted from specs and contracts and convert them to rules.

- **layout**: DataTable with a source document preview in a side panel.
- **sections**:
  - Requirements table (source, entity, attribute, constraint, status)
  - Source document preview
  - Conversion status
- **actions**:
  - Add requirement
  - Link to source document clause
  - Convert to rule
  - Mark as not enforceable
  - Import list
- **access**: rules.author

#### Validation runs and findings `/rules/results` (Rules & validation engine)

Review run results grouped by severity, jump to the failing record and record waivers.

- **layout**: Master-detail page with runs on the left and grouped findings on the right.
- **sections**:
  - Run list (trigger, scope, time, result)
  - Findings grouped by block and warn
  - Failing record link
  - Waiver panel
- **actions**:
  - Run bulk validation
  - Open record
  - Record waiver with reason
  - Export findings
- **access**: rules.view. Waive needs rules.waive, restricted by the configured waiver roles.

#### Rules settings `/settings/rules/config` (Rules & validation engine)

Configure language, allowed targets, limits, waiver policy and retention.

- **layout**: Settings form page.
- **sections**:
  - Expression language
  - Allowed target record types and fields
  - Waiver roles and reason requirement
  - Default rule set assignment
  - Evaluation timeout and limits
  - Log retention
  - Require test cases before publish
  - Message terminology keys
- **actions**:
  - Edit and save
- **access**: Tenant admin

#### Rule check dialog `Embedded: pre-submit and transition dialogs` (Rules & validation engine)

Show block and warn results when a user submits, approves or publishes, so they know what to fix.

- **layout**: Modal dialog launched from the WorkflowBar, forms and the publish dialog. It is not a routed page.
- **sections**:
  - Blocking failures with jump-to-field
  - Warnings with acknowledge
  - Waiver request (where permitted)
- **actions**:
  - Fix and recheck
  - Acknowledge warnings
  - Request waiver
  - Cancel
- **access**: Any user performing the guarded action. Results are evaluated server-side.
