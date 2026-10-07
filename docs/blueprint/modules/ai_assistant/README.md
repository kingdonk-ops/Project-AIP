# AI assistant & agents (`ai_assistant`)

- **Group:** Reporting, search & AI
- **Phase:** P4

What it is
AI assistant & agents lets users ask questions of their project data in plain language and lets AI draft work that a person reviews and applies. It sits in Reporting, search & AI, suggested phase P4. It is not built in AIP today and is deferred until the core is paid for. It is always behind the AI governance controls. The differentiator over generic assistants (Procore and Autodesk are rolling out assistants, and Microsoft Copilot sits over generic data; current product states are unconfirmed) is asset-scoped answers over inspection, ITP and NCR history while enforcing the caller's own permissions. Terminology must be renamable per market.

What it does
A chat reads through permission-aware tools and answers questions such as 'which ITPs on Area 3 are waiting on a hold point?' or 'which RFIs are overdue on the Unit 3 piping?'. Every answer cites the records it used. Changes, such as creating a task or reassigning an RFI, are only ever proposals that a person applies through the normal module APIs and audit. Agents run bounded multi-step tasks (reason, call tool, observe), for example drafting an inspection summary or preparing a reinspection list, using read-only tools by default. Extraction and drafting abilities (certificates, MTRs, NCRs) always end in human verification or approval.

Features
- Chat over project data with citations to records and source links on every answer
- Answer cards showing the filters, record counts and time range used, so counts are not misleading and users can confirm the question was interpreted correctly
- Proposed changes with human apply: target record, diff and status, applied only via normal API calls under the user's identity, with confirmation
- Agent loop with tool registry (read or write, scope) and run history, with step and cost limits
- Certificate and MTR extraction from scans (heat numbers, grades, expiry dates) with human verification, feeding traceability and eligibility checks
- NCR and corrective action drafting from inspection findings and photos, producing a draft with asset, clause and evidence that the inspector approves
- Prompt-injection screening for retrieved document and email content; all retrieved text is treated as untrusted data and cannot steer tool use or expose information
- Evaluation set of domain questions (ITP, hold point and asset queries) run on every model or prompt change
- Per-tenant opt-in and kill switch
- Per-tenant AI usage and data-flow dashboard showing what data went to which model and region, to support governance reviews
- Logging of all prompts and tool calls

Interactions
- AI governance & data controls: all controls apply
- Search, retrieval & saved views: retrieval
- Roles, permissions & teams: permission-aware tools, with authorisation enforced at retrieval and tool level, not just in the prompt
- Tools wrap other modules' APIs (search, retrieval, deadlines, RFI, submittals, inspections, NCR, tasks, documents, reporting) under the calling user's permissions
- Shared LLM gateway: AU-region endpoints, model routing, redaction, logging and per-tenant kill switch; this dependency does not yet exist and must be built as a thin service
- Activity feed and timeline: all agent runs are written to the timeline

Data
- Chat session
- Message
- Tool call log
- Proposed change (target record, diff, status)
- Agent definition
- Tool registry entry (read or write, scope)
- Run (prompt, steps, tool calls, outputs, tokens, user)
- Evaluation set and results
- Extraction result with verification status
- Tenant AI usage and data-flow records

Pages
- Chat panel with source links and answer cards
- Proposed-change review card (approve or discard)
- History view of chats and runs
- Agent run console with step trace, start and stop
- Tool permission admin
- Run history
- Per-tenant AI usage and data-flow dashboard
- Extraction and draft verification screens

Decisions and notes
- Deferred until governance and permission-aware retrieval are tested.
- Tools run as the calling user, never a service account.
- Writes are only human-applied proposals; agents are read-only by default.
- No URL-fetching or outbound network tools; no external fetching.
- Step limits, spend caps and full run logging apply to agents.
- Test for prompt injection through documents and correspondence.
- Owner accepted the six scout suggestions listed under Features.
- For this audience trust beats autonomy.

Open questions
- Advisors differ on agents: exclude from v1 or ship read-only (security advisor), versus defer entirely to v2 (competitor researcher). The owner has set P4 but has not decided whether agents ship with the chat or later.
- Which models and providers sit behind the gateway, and whether tenants may choose the model.
- Competitor product states are unverified.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
