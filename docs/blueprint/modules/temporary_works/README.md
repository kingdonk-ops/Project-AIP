# Temporary works register (`temporary_works`)

- **Group:** Safety & compliance
- **Phase:** P3

What it is
A safety-critical register governing scaffolds, propping, excavation support and other temporary works, following the BS 5975 approach: design brief, design and check, permit to load, inspections while in use, permit to strike. Not built in AIP yet (suggested phase P3). It is a configured workflow on the shared workflow engine, and BS 5975 terms are used only where the tenant chooses. Relevance to remediation work is mainly scaffold and insulation access.

What it does
Registers each temporary works item with category, risk class and the asset being accessed or supported, takes it through role-gated design, independent check and permit stages, schedules periodic inspections, and places holds on dependent work until permits and valid tags exist. The system enforces that the designer and checker are different people. Scaffold inspections tie into the access methods used by scopes of work.

Features
- Register of items with category, risk class, asset link, coordinator and stage chips on each row, with a board view by stage
- Design brief, design and calculations, and independent check records, with the designer/checker separation enforced server-side and by a deferred database trigger
- Permit to load and permit to strike with sign-off and conditions checklist
- Periodic inspection schedule per category (for example weekly scaffold tags), with overdue alerts
- Link to scopes needing scaffold access
- Hold flags that block related ITP steps or scope tasks until a permit is issued
- Competency checks for designer, checker and coordinator via the certificates gate
- Scaffold tag status linked to scope tasks as a work gate (tasks show red when the tag is expired or missing)
- Scaffold handover certificate and weekly inspection as inspection kinds
- Loading class and capacity fields, with warnings for insulation or equipment loads
- Modification and dismantle requests that re-trigger inspection and reset permit state
- Expiry and overdue dashboard with notifications to coordinator and supervisor

Interactions
- Inspections, ITPs & hold points: periodic scaffold inspections are normal inspections
- Workflow & approvals engine: permits and stages use it
- Scopes of work (RSW), disciplines & tasks: scaffold access requirement and holds
- Certificates, competency & calibration gate: competencies per role
- Documents: drawings and calculations
- Safety & HSE: events to the advanced pack; permit interplay
- Events consumed: scope.access_requirement.set, inspection.completed, certificate.status.changed, document.revision.issued, schedule.tick.daily
- Events emitted: tw.item.created, tw.design.checked, tw.permit_to_load.issued, tw.permit_to_strike.issued, tw.inspection.overdue, tw.hold.set, tw.hold.released
- Notifications: design check requested, permit to load issued, inspection due, overdue or failed, permit to strike requested, competency expired

Data
- tw_items: reference (unique per tenant and project), category, risk_class, description, asset_id, location, coordinator_id, status (workflow stage), design_brief_document_id, sync_version, soft delete
- tw_design (revision, designer_id, document_id), tw_check (checker_id), tw_permit (load/strike), tw_inspection_schedule
- Periodic inspections are normal inspections linked via last_inspection_id, not a separate table
- Workflow stages are workflow definitions, not columns
- Reuses assets, inspections, documents, certificates, tasks, disciplines
- Configuration, not code: categories and risk classes, stages and approval roles (BS 5975 default, renamable), inspection frequency per category, required competencies, permit templates, terminology per market

Pages
- Temporary works register (/projects/:projectId/temporary-works): filters, stage chips, board toggle, export, assign coordinator
- Register or edit item (/new): asset picker, inline competency check beside each person field
- TW item detail (/:twId): stage chips, WorkflowBar, tabs for brief, design, check, permit to load, inspections, permit to strike, linked scopes and ITP holds, documents, audit trail, competency status rail
- Permits list
- Permissions: tw.view, tw.manage; permit issue needs coordinator competency
- Settings: categories, competencies, separation rule, permit workflows, frequencies, hold-release behaviour, recipients

Decisions and notes
- All five advisor suggestions were accepted by the owner
- Keep as a configured workflow on the shared engine rather than a bespoke system
- For scaffold and insulation-access work, link items to the asset being accessed

Open questions
- Is the asset link mandatory for all categories (form says required, other notes say optional)?
- Default hold-release behaviour when a permit lapses?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
