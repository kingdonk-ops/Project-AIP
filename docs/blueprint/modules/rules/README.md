# Rules & validation engine (`rules`)

- **Group:** Inspection & quality
- **Phase:** P1

What it is
The Rules & validation engine is one place to define business rules that check data and guard workflow transitions. It sits in Inspection & quality (suggested phase P2). AIP PRD §7.3 already specifies server-side transition guard expressions; the item-type design pass §6 deferred a full rules engine until a real requirement exists. The accepted rule pack library now supplies that requirement.

What it does
Stores rules per tenant as simple expressions (JSONLogic or CEL) used for field validation, workflow guards (for example no open critical issues before approval, certificate must be valid before submit), report pre-flight and requirement checks extracted from specs or contracts. Rules are evaluated server-side only, in a sandbox, and client-evaluated results are never trusted. One expression language is shared across forms, workflow guards and the eligibility gate.

Features
- Rule definitions as data: target record type, expression, message (terminology keys allowed), severity (block or warn), trigger (field validation, workflow guard, pre-publish, bulk)
- Workflow transition guards
- Versioned rule sets per tenant or project; publishing freezes a version so runs can be reproduced
- Rule-set inheritance: tenant default, project override, scope override
- Rule test panel with sample records and saved test cases; optional requirement of passing tests before publish
- Rule impact preview showing how many existing records would fail on activation
- Time-aware evaluation as at the record's event date, so a certificate valid on test day still passes historical records
- Library of inspection-completeness rule packs: NDT readings present, DFT within spec range, hold points signed, instrument calibrated, inspector qualified for method
- Requirements register: entity-attribute-constraint triplets from specs and contracts with source document and clause, status (draft, validated, approved), applicability, convertible to rules; extraction manual first, AI-assisted later behind human review
- Requirement-to-evidence coverage matrix showing which clauses have a rule and passing evidence
- Waiver workflow reusing the approvals engine, with reason, audit trail and expiry; block-severity waivers need a separate permission
- Bulk validation runs on the job queue, with notifications (rule set published, rollback, block failures above threshold, waiver recorded, expression error)

Interactions
- Workflow & approvals engine: guards on transitions
- Form & template designer: field validation
- Certificates, competency & calibration gate: validity checks
- Report engine: pre-flight before generation
- Commissioning: gate rule set
- Quality roll-up: unverified requirements flagged
- Database & schema conventions: evaluated server-side

Data
- rule_sets (key, version, status draft/published/retired, tenant or project level, published by and at; published versions immutable by trigger)
- rules (code, target record type, entity type, trigger, workflow transition key, expression language, expression validated against whitelist on save, message, severity, active)
- requirements, validation runs, validation findings, waivers
- Context providers expose read-only data (certificate validity, open issues) through a registry without cross-imports or copying data.
- Events consumed include workflow.transition.requested, report.preflight.requested, form.submit.requested.
- Config not code: rule sets, expressions, messages, severities, assignments, requirement triplets, waiver policy, sample records.

Pages
- Rules register at /settings/rules
- Rule editor at /settings/rules/:ruleId (definition, expression editor with context picker, test panel, version diff, where used, results, waivers, audit trail)
- Rule sets at /settings/rule-sets
- Requirements register with source document preview

Access: rules.view, rules.author, rules.publish.

Decisions and notes
- Admin-only authoring; strict schema, whitelisted operators, no I/O, time and memory limits, tenant scoping; every change audited with who changed it.
- Exposed through one gate interface so adding rules never touches workflow, form or report code.
- No raw YAML exposed to tenants; configure through a UI.
- BOQ-focused checks are out; validation targets inspection completeness, ITP data, certificate expiry and generic entities.
- All six scout suggestions were accepted by the owner.

Open questions
- JSONLogic versus CEL as the single language (tech advisor says choose one; not yet decided).
- Whether to ship a fixed rule pack first (advisors suggested deferral) or the full authoring UI in P2.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
