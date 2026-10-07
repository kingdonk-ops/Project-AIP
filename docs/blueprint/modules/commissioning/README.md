# Commissioning (`commissioning`)

- **Group:** Inspection & quality
- **Phase:** P4

What it is
Commissioning provides system commissioning checklists and readiness for MEP and process plant. It sits in Inspection & quality (suggested phase P4, not built in AIP). It is built on the existing form, inspection and workflow engines, reusing the inspection check engine; likely secondary for remediation work.

What it does
Groups asset nodes into systems and subsystems, generates pre-functional and functional checklists from templates, tracks an issue log, and computes a readiness score. The commission action is gated server-side until required checks are complete, no blocking NCRs are open and sign-offs are done by credentialled people.

Features
- Systems and subsystems over the asset tree, with include/exclude membership beyond the root subtree
- Pre-functional and functional checklist templates (checklists are inspection kinds)
- Readiness score with weighting by check type and risk, so a flat percentage does not hide critical items
- Gated commission action, with the gate expressed as a rule set evaluated through the rules engine
- Punch category rules deciding which open items block each gate (for example category A blocks commissioning, B can follow)
- Gate certificates (mechanical completion, ready for commissioning) as sealed report templates
- System boundary markup on P&IDs or isometrics linked to asset nodes
- Bulk check completion by tag set with an evidence requirement
- Re-open and re-test logic when an asset changes after sign-off
- Commissioning issue log
- Notifications: checklist assigned, issue assigned, blocking issue raised, system ready, gate passed, gate blocked by new NCR, sign-off requested

Interactions
- Inspections, ITPs & hold points: checklists are inspection kinds
- Asset hierarchy & registers: systems are asset nodes
- Handover, data books & submissions: readiness and gate pass feed closeout and handover status per asset
- Rules engine: gate evaluation
- Report engine: gate certificates
- Certificates, competency and calibration: credentialled sign-offs
- Documents: as-builts and certificates linked

Data
- commissioning_systems: project, parent system, root asset, code (unique per project), name, term-keyed classification, readiness weight overrides, gate rule set, workflow status, sync version, soft delete
- commissioning_system_members: include/exclude assets
- readiness_snapshot and commission_record
- Commissioning issues are rows in the existing issues table linked via asset membership, not a new table; add commissioning_system_id on issues only if the subtree query proves too slow.
- Readiness is recomputed on events and snapshotted on change.
- Events consumed: inspection.approved, inspection.rejected, issue.created, issue.closed, punch.item.closed, asset.moved, certificate.status.changed. Events emitted: commissioning.system.created, commissioning.readiness.changed, commissioning.system.commissioned.
- Config not code: checklist templates, readiness weighting, gate rule set, workflow states, classification names, required sign-off roles, issue severity list, system numbering, handover status mapping.

Pages
- Systems register at /projects/:projectId/commissioning: system tree with readiness rings plus table, with toggle
- Create or edit system with asset tree picker
- System detail: summary and ring, asset nodes, checklists, issue log, gate requirements and outstanding items pinned panel, linked documents, sign-offs, commission action and history, activity
- Checklists page (run needs inspection.execute), mobile checklist execution

Access: commissioning.view and commissioning.manage; commission action limited to credentialled sign-off roles.

Decisions and notes
- Checklist behaviour changes happen in inspections or form templates, not here.
- Build after inspections and reuse its check engine.
- All six scout suggestions were accepted by the owner.

Open questions
- None recorded; owner decisions to date are reflected above.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
