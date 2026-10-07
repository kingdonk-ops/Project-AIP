# Page specs for `ai_assistant`

#### Assistant chat `/p/:projectId/assistant` (AI assistant & agents)

Ask plain-language questions over project data and receive cited, permission-scoped answers.

- **layout**: Docked right-side panel expandable to full page; message thread with composer at the bottom, history rail on the left when expanded.
- **sections**:
  - Message thread
  - Answer card (filters, record counts, time range)
  - Citations and source links
  - Proposed-change cards inline
  - Composer with scope chip (project/asset subtree)
  - AI disabled or kill-switch banner
- **actions**:
  - Ask question
  - Open cited record
  - Edit filters and re-run
  - Copy answer
  - Flag answer as wrong
  - Start new chat
  - Open proposed change
- **access**: Users with the ai.use permission in a tenant that has opted in; results limited to the caller's own permissions.

#### Chats and runs history `/p/:projectId/assistant/history` (AI assistant & agents)

Find and reopen prior chats and agent runs.

- **layout**: Filterable table with a preview drawer.
- **sections**:
  - Filter bar (type, date, user, status)
  - History table
  - Preview drawer with transcript and citations
- **actions**:
  - Reopen chat
  - Delete own chat (subject to legal hold)
  - Open run console
  - Export transcript
- **access**: Users see their own history; tenant AI admins and auditors can see all, with audit logging.

#### Proposed change review `/p/:projectId/assistant/proposals/:proposalId` (AI assistant & agents)

Review an AI-proposed change and apply or discard it under the user's identity.

- **layout**: Single card page: target record header, diff view, evidence side panel, confirm bar.
- **sections**:
  - Target record summary and link
  - Before/after diff
  - Evidence and citations
  - Status timeline
  - Confirm bar
- **actions**:
  - Approve and apply via module API
  - Edit before applying
  - Discard
  - Open target record
- **access**: The requesting user, and only if they hold write permission on the target record; applying runs under their identity.

#### Agent run console `/p/:projectId/assistant/runs/:runId` (AI assistant & agents)

Start, watch and stop bounded agent runs with a full step trace.

- **layout**: Two-pane: agent picker and parameters on the left, live step trace with tool calls and outputs on the right, limits bar on top.
- **sections**:
  - Agent selector and parameters
  - Step limit, token and spend meters
  - Step trace (reason, tool call, observation)
  - Outputs and drafts
  - Proposed changes produced
- **actions**:
  - Start run
  - Stop run
  - Open cited record
  - Send output to verification
  - Download run log
- **access**: Users with the ai.agents.run permission; read-only tools by default; the feature is shown only if agents are enabled for the tenant.

#### Extraction and draft verification `/p/:projectId/assistant/verify/:extractionId` (AI assistant & agents)

Human verification of extracted certificate/MTR fields and AI-drafted NCRs before they enter records.

- **layout**: Split view: source scan or photo viewer on the left, editable extracted fields or draft form on the right, with confidence flags.
- **sections**:
  - Source viewer with highlighted regions
  - Extracted fields (heat number, grade, expiry) with confidence
  - NCR draft (asset, clause, evidence, description)
  - Validation warnings (e.g. expired or mismatched)
  - Verification status bar
- **actions**:
  - Edit field
  - Verify and save
  - Reject
  - Send NCR draft to inspector approval
  - Re-run extraction
- **access**: Inspectors, QA and document controllers with create permission on the target record type; output stays unverified until approved.

#### Tool permission admin `/admin/ai/tools` (AI assistant & agents)

Control which tools exist, whether they read or write, and who may use them.

- **layout**: Registry table with detail drawer.
- **sections**:
  - Tool list (read/write, scope, status)
  - Role and team assignment
  - Limits per tool
  - Change history
- **actions**:
  - Enable or disable tool
  - Set scope
  - Assign roles
  - Review change history
- **access**: Tenant AI admin; write tools can be enabled only with an explicit confirmation step.

#### AI usage and data-flow dashboard `/admin/ai/usage` (AI assistant & agents)

Show what data went to which model and region and at what cost, for governance reviews.

- **layout**: Dashboard with KPI tiles, charts and a drill-down table.
- **sections**:
  - Usage and spend tiles
  - Data-flow map (data category, model, region)
  - Injection-screen hits
  - Evaluation results trend
  - Per-user and per-agent table
- **actions**:
  - Filter by period and project
  - Export report
  - Open prompt log (audited)
  - Set spend cap
- **access**: Tenant AI admin, security and compliance roles, and auditors (read-only).

#### AI settings and kill switch `/admin/ai/settings` (AI assistant & agents)

Per-tenant opt-in, model routing and emergency disable.

- **layout**: Settings form with a prominent kill-switch card.
- **sections**:
  - Opt-in status
  - Model and region routing (read-only if not tenant-selectable)
  - Spend and step limits
  - Evaluation set status
  - Kill switch
- **actions**:
  - Opt in or out
  - Set limits
  - Run evaluation set
  - Trigger kill switch
- **access**: Tenant admin; changes are audited, and the kill switch is also available to the platform operator.

#### Evaluation sets and results `/admin/ai/evals` (AI assistant & agents)

Maintain domain test questions and view results for each model or prompt change.

- **layout**: Master-detail: sets on the left, results table and comparison on the right.
- **sections**:
  - Question sets
  - Last-run pass rate
  - Per-question result with citations check
  - Run comparison
- **actions**:
  - Add question
  - Run evaluation
  - Compare runs
  - Export results
- **access**: Tenant AI admin and platform AI maintainers.

#### Mobile assistant `/m/assistant` (AI assistant & agents)

Ask quick questions and verify extractions on a phone in the field.

- **layout**: Full-screen chat with a bottom composer; verification screens are stacked cards.
- **sections**:
  - Chat thread with compact answer cards
  - Pending proposals list
  - Pending verifications list
  - Offline notice (assistant needs a connection)
- **actions**:
  - Ask question
  - Open record
  - Apply or discard proposal
  - Verify extraction
- **access**: Same as the desktop chat; unavailable offline.
