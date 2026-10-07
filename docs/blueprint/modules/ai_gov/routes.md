# Page specs for `ai_gov`

#### Tenant AI settings `/settings/ai` (AI governance & data controls)

Enable AI per feature, set restrictions and budgets.

- **layout**: Feature table with toggles; blade for restrictions and budget.
- **sections**:
  - Features table (Feature, Enabled, Scope restrictions, Client prohibits AI, Budget cap, Changed by)
  - Project/client exclusions
  - Agent write confirmation policy
  - Citation threshold
  - Log retention
- **actions**:
  - Enable/disable
  - Set exclusions
  - Set budget cap
  - Bulk disable
- **access**: Tenant admin with AI governance permission; off by default.

#### Platform kill switch `/admin/ai/kill-switch` (AI governance & data controls)

Disable AI features platform-wide or per feature instantly.

- **layout**: Single control panel with state banner and history.
- **sections**:
  - Current state
  - Scope selector
  - Change history
- **actions**:
  - Activate
  - Deactivate with reason
- **access**: Platform administrators only.

#### AI data-flow register `/settings/ai/register` (AI governance & data controls)

Versioned record of provider, model, region, retention and training-use terms per feature.

- **layout**: Register with detail page and version history tab.
- **sections**:
  - Register table
  - Version history
  - Zero-retention evidence files
  - Export pack
- **actions**:
  - View
  - New version
  - Retire
  - Attach evidence
  - Export PDF/JSON
- **access**: Platform admin edits; tenant admins and security reviewers read.

#### AI audit log `/settings/ai/audit` (AI governance & data controls)

Review prompts, responses and tool calls with citations and acceptance status.

- **layout**: Register with split-pane detail showing prompt, response, tools and citations.
- **sections**:
  - Call log table
  - Detail pane
  - Citation links
  - Redaction markers
  - Acceptance label
- **actions**:
  - Filter
  - Open source record
  - Export
  - Flag
- **access**: Tenant AI auditor role; entries respect source-data permissions.

#### Usage and budget dashboard `/settings/ai/usage` (AI governance & data controls)

Track AI cost and usage against caps.

- **layout**: KPI strip with charts and per-feature table.
- **sections**:
  - Spend vs cap
  - Usage by feature
  - Blocked unsupported answers
  - Red-team CI status
- **actions**:
  - Adjust cap
  - Export
  - View failing red-team case
- **access**: Tenant admin; platform admin for cross-tenant view.

#### Redaction rules `/settings/ai/redaction` (AI governance & data controls)

Configure PII and commercial rate redaction applied before sending.

- **layout**: Rules list with test panel.
- **sections**:
  - Rule list
  - Test input and redacted output
- **actions**:
  - Add rule
  - Edit
  - Test
  - Disable
- **access**: Tenant admin with AI governance permission.
