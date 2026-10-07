# AI governance & data controls (`ai_gov`)

- **Group:** Foundations & architecture
- **Phase:** P4

What it is
The rules and controls every AI feature must follow before it can touch client data. This module is the control point for all AI in the platform: nothing calls a model provider except through it. It is part of Foundations & architecture (suggested phase P4). No AI features are built in AIP yet, and the Inspectivity reference uses no AI. The aim is to treat every AI feature as an external data flow with controls, and to make permission-aware, AU-region AI a trust differentiator for IRAP and mining-client security reviews (for example Rio Tinto-type clients, with Kaefer as the first customer).

What it does
- Keeps a versioned, append-only register of which data goes to which model provider, model, region, retention and training-use terms, per feature. No feature can call a model until it has an entry.
- Lets each tenant opt in per feature, off by default, with a platform kill switch enforced server-side.
- Routes model calls to AU-region endpoints (for example Bedrock in ap-southeast-2, Sydney) with zero-retention settings recorded as evidence for IRAP and mining clients.
- Redacts personal information and commercial rates before anything is sent.
- Applies the caller's permissions at query time during retrieval, using the same policy layer as the UI (tenant, project, team, asset subtree), never filtering after retrieval.
- Gives agents read-only tools by default, requires human confirmation for writes, and provides no outbound URL fetching or network tools.
- Logs all prompts, responses and tool calls for audit, under the same access controls as the source data and subject to legal hold.
- Treats documents, emails, inspection comments and transcripts as untrusted input and applies prompt-injection defences, content isolation and output validation.
- The gateway checks kill switch, tenant opt-in, restrictions (inherited feature, project, client, document), budget and region before any call.

Features
- Per-tenant and per-feature AI opt-in, off by default
- Platform kill switch, enforced server-side
- Model endpoint per region; zero-retention settings recorded
- Redaction of personal information and commercial rates before sending
- Retrieval filtered by the caller's permissions at query time
- Agents: read-only tools by default; writes need human confirmation; no outbound URL fetching
- All prompts, responses and tool calls logged for audit, with retention rules
- Documents, emails and transcripts treated as untrusted input
- AI data-flow register exportable as a customer security pack (PDF/JSON)
- Per-feature, per-project and per-client AI restrictions, with a 'client prohibits AI' flag that inherits down to documents, so the flag follows the data and not only the tenant
- Confidence and citation requirements: AI answers must link to source records, and unsupported answers are blocked
- AI output labelling and separation from signed records: AI-drafted text (summaries, minutes, NCR wording) is tagged and needs human acceptance before entering a published or sealed record
- Red-team test suite for injection via documents, inspection comments and emails, run in CI
- Cost and usage metering per tenant with budget caps (alerts at 80% and 100%)

Interactions
- AI assistant & agents: every AI feature calls through these controls; adding a feature means registering it and calling the gateway, and adding a provider means a new adapter plus a register entry.
- Voice notes & phone log: transcription data flow.
- Meetings & AI minutes: AI minutes.
- Security & compliance programme: part of the control set; AU-region assurance (ap-southeast-2 residency, per-tenant KMS keys, siloed deployment option, SCIM deprovisioning, tamper-evident audit logs) can be published as a compliance pack for mining and LNG procurement.
- Search, retrieval & saved views: semantic search embeddings must respect the same permission filtering and AI restrictions.
- Audit-grade (hash-chained) timeline: pairs with this module as claims evidence.
- Existing AIP permissions catalogue and activity feed: the policy layer builds on these.

Data
- AI data-flow register entries: feature, provider, model, region, data categories, retention terms, training-use terms, zero-retention evidence (linked document), version history
- Tenant, feature, project and client AI settings, including the 'client prohibits AI' flag and its inheritance to documents
- Kill switch state
- Prompt, response and tool-call logs, with retention rules
- Citation links from answers to source records; AI-generated labels and acceptance status
- Usage and cost metering and budget caps per tenant
- Red-team test cases and results

Pages
- Tenant admin AI settings (per-feature toggles, restrictions, budget cap, agent write confirmation policy, citation threshold, log retention)
- Platform kill switch control (platform admins only, with reason and history)
- Data-flow register view and export
- AI audit log viewer
- Usage and budget dashboard

Decisions and notes
- Owner accepted all six scout suggestions listed under Features.
- AI is off by default per tenant.
- Use Bedrock in ap-southeast-2 with zero-retention settings; confirm zero-retention terms in writing and review sub-processors.
- Kill switches are enforced server-side.
- Before making any competitor comparison claims, verify each competitor's IRAP and SOC 2 status and regional options.
- Tech stack advice is to defer the assistant until core revenue is in; this affects timing of dependent features, not the controls themselves.

Open questions
- Timing: the module is suggested for P4, while the tech stack advisor suggests deferring the assistant until core revenue is in. Owner has not decided the sequencing.
- Whether to offer a siloed deployment option and per-tenant KMS keys as part of the compliance pack, or treat them as separate security work (a key reference field is added to the schema only if included).

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
