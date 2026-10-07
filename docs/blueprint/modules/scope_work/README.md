# Scopes of work (RSW), disciplines & tasks (`scope_work`)

- **Group:** Asset core
- **Phase:** P1

What it is
The work packages executed against assets: Return-to-Service Worksheets (RSW), their disciplines and ordered tasks. The RSW label is renamable per market.

What it does
An RSW groups disciplines (welding, coating, NDT...) each with an ordered task chain (test > measure > blast > weld). Tasks can require an inspection, ITP, RFI or consumable issuance; the RSW cannot be completed until every requirement is in an accepted state. It carries the commercial and access data from the Scope Portal: work order, CTR, WBS, tier, priority, planned and earned hours, delay hours and reasons, access method.

Features
- RSW fields: RSW no./rev, location, corrosion environment, observation, remedial works, notification no., mandated completion date, priority P1-P4
- Disciplines and tasks as real tables with sequence; requires_itp/inspection/rfi/consumables flags
- Auto-create linked ITP/RFI/inspection from task flags; unique hold-point link per task
- Progress roll-up (% of requirements accepted) and hard completion gate; gate evaluations stored for audit; completed_at set only when the gate passes
- Commercial: work order, order no., CTR, WBS, tier, estimated hours, metres to scan
- Planned vs earned hours (PV/EV), actual and delay hours (0.5h steppers), delay reasons (Weather, Access, Permit, SIMOPS, Equipment)
- Access methods: Ground, Rope Access, Scaffold, MEWP/Ladder (vocabulary to reconcile)
- Inspection technique per scope (X-Arm, C-Arm, Viken, RT, UT) and procedure references (ISO, P&ID)
- Scope Portal v1 split view and v2 unified WBS grid with slide-over blade; v2 KPI strip (active scopes, earned hours, QA/QC backlog, pending client review)
- Cross-RSW task reporting ('every task still needing an ITP') as a first-class endpoint with saved views, grouped by area
- RSW templates by asset class and environment that generate disciplines, ordered tasks, flags and ITPs
- Constraints and readiness checklist per RSW: permit, access, materials, scaffold and competent-personnel readiness visible before work starts
- Quantity-based progress and earned value (m2, metres, items) alongside hours
- Scope revision comparison (diff view) and change flag, with approval of scope changes tied to variations
- Bulk import and sync of scopes from client portal exports, with mapping, validation, dry run and error report

Interactions
- Asset hierarchy and registers: an RSW belongs to an asset
- Inspections, ITPs and hold points: tasks spawn inspections/ITPs/RFIs
- Stock, consumables and materials: consumable issuance per task
- Cost items and schedule of rates (thin): tasks can map to cost codes
- Dashboards and KPI reporting: PV/EV and progress KPIs
- Traceability graph: ScopeTask.component_asset_id links tasks to components
- The gate reads other modules' state via events and service interfaces (inspection approved/rejected, hold point state, RFI closed, stock issued)

Data
- Reuses assets, disciplines, tasks, inspections, consumable_issuances, documents; adds the RSW-specific layer (rsw_disciplines, scope_tasks, hours, delays), migrating rather than duplicating if scope_tasks overlaps the existing tasks table
- RSW record: tenant, project, asset, rsw_number, revision, location, corrosion_environment, observation, remedial_works, notification_no, mandated_completion_date, priority, computed_deadline (deferred), work_order, order_no, ctr, wbs, tier, estimated_hours, metres_to_scan, access_method and inspection_technique (vocabulary keys), procedure_refs (JSONB document ids), status, progress_pct (cached), completed_at, sync_version
- Vocabularies in scope_vocabularies; configuration not code: delay reasons, access methods, techniques, priority levels, discipline definitions and default task chains, requirement defaults per discipline, RSW numbering, terminology labels, gate requirement set, hour increment
- Built: Scope tab with RSW fields and priority (TASKS 8.4), disciplines/tasks tables (17), progress and completion gate (21), consumables in gate (32), hold-point uniqueness (37)

Pages
- RSW register (/scopes): KPI strip, table, filters by priority, status, discipline, WBS
- Create or edit RSW (/scopes/new)
- RSW detail (/scopes/:id): header with progress and gate status; scope details, disciplines and tasks, requirements and gate, linked ITPs/inspections/RFIs/hold points, consumables, commercial, hours, access and technique, documents and procedures, revision history, activity
- Scope Portal WBS grid (/scopes/portal) with blade, split-view toggle and inline hours editing
- Notifications: RSW created or assigned, requirement auto-created, completion blocked, completed, mandated date approaching or overdue, delay on P1/P2, consumables shortfall

Decisions and notes
- All six scouted suggestions accepted.
- Deferred in repo: dedicated cross-RSW reporting endpoint (now accepted) and computed deadlines from priority.
- Gate logic lives only in gate.py.

Open questions
- Access methods vocabulary (Ground, Rope Access, Scaffold, MEWP/Ladder) needs reconciling.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
