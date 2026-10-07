# Service & maintenance (`service`)

- **Group:** Handover & asset lifecycle
- **Phase:** P4

What it is
Service & maintenance is the post-handover module in the Handover & asset lifecycle group (suggested phase P4). It covers service contracts, tickets, work orders and preventive maintenance against assets. For the first customer, Kaefer on Rio Tinto remediation work, it is adapted to recurring inspection, repair and re-coating campaigns on assets rather than a general operations CMMS. It reuses the existing AIP inspection and ITP machinery (inspection programmes, E4-S1 in the spec, power recurring checks) instead of building a parallel system.

What it does
It lets a contractor hold service contracts with SLA targets, raise tickets and work orders against assets in the hierarchy, schedule preventive maintenance and recurring inspections, assign qualified technicians, and track SLA performance. Findings from inspections can flow straight into repair work orders. Each asset gets a full lifecycle history from construction through service. Scope is deliberately light: PM and work orders on the asset tree. A full CMMS competition with IBM Maximo is deferred. Contract and SLA terms are configurable labels so terminology can be renamed per market.

Features
- Service contracts and SLAs (client, term, scope, SLA targets).
- Tickets and work orders against assets, with tasks, labour, materials and sign-off.
- Preventive maintenance schedules by asset or asset class, with frequency and next due date.
- Technician assignment.
- Risk-based inspection interval scheduling per asset class and condition, with next due recalculated from the last finding (CUI and integrity programmes use condition-driven intervals rather than fixed calendars).
- Auto-create work orders from inspection findings above a severity threshold, carrying photos, location and recommended repair.
- Recurring campaign templates (strip, inspect, repair, reinsulate, recoat) with stage gates and ITP binding.
- Skills and certificate matching on technician assignment using the existing eligibility gate, so only qualified NDT, coating or rope-access personnel can be assigned.
- Asset history timeline merging construction ITPs, handover baseline, inspections and work orders.
- SLA clocks that pause on client hold or access restrictions, with reason capture.
- Defects received from defects liability convert into work orders.

Interactions
- Asset hierarchy & registers: all work is against assets; PM can be set per asset or asset class and viewed by subtree.
- Inspections, ITPs & hold points: recurring programmes drive PM and recurring inspection types; inspections are triggered from schedules; findings above threshold create work orders; campaigns bind to ITPs.
- Equipment & fleet: maintenance of plant, and plant used on work orders.
- Contacts: client and site contacts.
- Users and teams: assignment; certificates and eligibility gate for qualification checks.
- Resources: labour.
- Tasks and forms: raised for field execution.
- Notifications: written on SLA breach.
- Defects liability: defects convert into work orders.
- Closeout: handed-over assets arrive from closeout with a handover baseline.
- Procurement and variations: costs can feed these when work is out of scope.

Data
- ServiceContract: client, term, scope, SLA targets (labels configurable).
- Ticket: asset_id, priority, status, SLA clock (with pause intervals and reasons for client hold or access restriction).
- WorkOrder: tasks, labour, materials, sign-off, source (ticket, inspection finding, defect, schedule or campaign), photos, location, recommended repair.
- PreventiveSchedule: asset or asset class, frequency, next due, condition-based recalculation from last finding.
- CampaignTemplate: ordered stages (strip, inspect, repair, reinsulate, recoat), stage gates, ITP binding.
- Asset history timeline: a merged view of existing records, not a separate store.

Pages
- Ticket queue with SLA countdown.
- Work order detail with form completion.
- PM calendar by asset subtree.
- Campaign template designer and campaign progress view.
- Asset history timeline.
- Service contract and SLA setup.

Decisions and notes
- All six scout suggestions were accepted by the owner and are included above.
- Keep scope light; defer a full CMMS fight with Maximo. Competitors (Maximo, ServiceNow, Fiix, UpKeep, ServiceM8, Procore service tooling, the latter's depth uncertain) are built for operations teams, so the differentiator is linking maintenance to construction-phase inspection history.
- Reuse inspection programmes (E4-S1) rather than a new scheduler for recurring checks.
- Terminology for contracts, SLAs and campaigns must be renamable per market.

Open questions
- Market abilities not accepted or decided: meter-based PM, failure codes, offline mobile work order completion and service entitlement management. Include any of these?
- Severity threshold for auto-created work orders: fixed or configurable per client or asset class?
- Whether the SLA pause reasons are a fixed list or configurable.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
