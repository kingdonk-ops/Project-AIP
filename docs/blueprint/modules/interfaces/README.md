# Interface management (`interfaces`)

- **Group:** Collaboration & coordination
- **Phase:** P4

What it is
Interface management is a register of hand-offs between work packages, contractors and disciplines, including client and subcontractor handovers. It records who must provide what to whom by when on multi-package projects, with status, sign-off and escalation. It is asset-centric: each interface point is tied to an asset node and, where relevant, a scope task, so users can see exactly what is blocking a scope of work. Suggested phase: P4 (Collaboration and coordination). AIP repo status: not built. Interface registers are standard on megaprojects and are usually run in Primavera Unifier, InEight, Aconex workflows, Excel or bespoke tools; Procore has no mainstream equivalent, so this is a real opportunity for EPC audiences.

What it does
- Tracks each interface from raising through agreement, delivery and acceptance.
- Shows who is waiting on whom, by when, and how late it is.
- Escalates overdue interfaces automatically up a configurable ladder.
- Surfaces interface delays as visible constraints on RSW tasks and the look-ahead.
- Provides defensible proof that a handover happened and was accepted by both parties.
- Differentiator: who-provides-what-to-whom by date, linked to asset nodes, work packages and deadlines, with overdue escalation and interface-point sign-off.

Features
- Interface points with provider, receiver, deliverable and need date.
- Asset-linked interface points (for example scaffold handover, insulation strip, coating access, isolation ready) tied to the asset node and scope task.
- Interface templates for common remediation handoffs with default providers, receivers and lead times, to speed setup on new projects and standardise what Kaefer and later customers track.
- Status stages: identified, agreed, delivered, accepted.
- Actions: raise, agree, deliver, accept, escalate.
- Two-party acceptance with signed attestation and evidence attachments (photos, certificates, inspection records).
- Automatic escalation ladder with configurable levels (responsible person, package manager, project manager), with inclusion in the next meeting agenda.
- Blocked-by relationships that surface on RSW tasks and look-ahead as a visible constraint; these also feed advanced scheduling for risk to dates.
- Interface ageing and heat-map view by package pair.
- Interface matrix by package or contractor.
- Party-scoped visibility so each side sees only its own interfaces.
- Reports on overdue and at-risk interfaces.
- Links to RFIs, submittals and documents.

Interactions
- Tasks, deadlines and my work: writes need dates to deadlines; escalation items become tasks.
- RFIs and submittals: related questions and submittals link to interfaces as evidence or context.
- Documents: linked as deliverable evidence.
- Meetings: escalated interfaces go into the next meeting agenda.
- Notifications: sent to both provider and receiver.
- RSW scopes and look-ahead: blocked-by constraints appear on tasks.
- Schedule (advanced): blocked-by relations feed risk to dates.
- Reads projects, contacts, and the asset and work package structure.
- Reporting and timeline: interface data is reported to both.

Data
- Interface: provider party, receiver party, package, asset node, scope task, deliverable, required date, status, escalation level.
- Interface agreement.
- Deliverable evidence link (photos, certificates, inspection records, documents).
- Acceptance record: signed attestation by provider and receiver.
- Interface template: default provider, receiver, lead time.
- Blocked-by relation between interfaces and tasks.
- Escalation ladder configuration: levels and roles.
- Links to RFIs, submittals and documents.
- Terminology must be renamable per market.

Pages
- Interface matrix by package.
- Interface list with ageing.
- Interface detail with evidence, comments and sign-off.
- Ageing and heat-map view by package pair.
- Template and escalation ladder configuration.

Decisions and notes
- The owner accepted all six feature suggestions: asset-linked points, templates, blocked-by constraints, two-party acceptance, escalation ladder and ageing heat-map.
- Competitor research is less certain about dedicated interface products beyond those named.
- First customer is Kaefer on Rio Tinto remediation work, so templates should reflect remediation handoffs.

Open questions
- None currently conflicting; the owner has not specified default escalation timings or whether external parties get logins for party-scoped views.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
