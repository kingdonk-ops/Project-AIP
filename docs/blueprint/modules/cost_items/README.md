# Cost items & schedule of rates (thin) (`cost_items`)

- **Group:** Commercial
- **Phase:** removed

> **REMOVED by owner. Do not build. Strip any hooks that reference it.**

What it is
A thin Commercial module holding cost codes and a schedule of rates. It replaces the full BOQ and cost database that the owner did not select. Advisors (architecture, feature and integration, delivery) all flagged that change orders, variations, site logistics and site inventory depended on the unselected BOQ and costs modules. This module gives them a concrete record to link to without importing those modules wholesale. It is asset-centric: every cost item can carry an asset_id, so cost and progress can be seen per unit, line or area. Terminology must be renamable per market. First customer is Kaefer on Rio Tinto remediation work.

What it does
It stores cost items (code, description, unit of measure, rate, budget, asset_id, WBS/CTR link) and imports client or Kaefer schedules of rates from CSV or Excel. Scope tasks and variations link to cost items. Field progress is captured as measured quantities on scope tasks and priced automatically from the schedule of rates. It produces a simple budget vs committed vs earned roll-up, including roll-up by asset subtree using the ltree hierarchy.

Features
- Cost item record: code, description, unit of measure, rate, budget, asset_id, WBS/CTR link.
- CSV/Excel import of client or Kaefer schedules of rates.
- Import mapping templates: reusable mappings for varied Excel layouts, with a validation report and rollback of a bad import.
- Versioned rate schedules with effective dates and per-contract assignment, so historical pricing stays reproducible when client or Kaefer rates change by contract and period.
- Tiered work-type pricing as rate modifiers (for example access, height, confined space or shift loadings), applied on top of unit rates.
- Measured quantity capture on scope tasks (for example m2 of insulation stripped, m recoated), priced automatically from the schedule of rates. This turns field progress into earned value and claim-ready quantities with no re-keying.
- Link scope tasks and variations to cost items.
- Simple budget vs committed vs earned roll-up.
- Cost roll-up by asset subtree using the ltree hierarchy, showing cost and progress per unit, line or area.

Interactions
- Scopes of work (RSW), disciplines and tasks: tasks map to cost codes; measured quantities are captured on tasks. The Scope Portal already carries work order, CTR, WBS and tier fields, which the cost item WBS/CTR link should reuse.
- Change orders, variations and MOC (basic): variations are priced from rates.
- Supplier catalogue, requisitions and POs: PO lines are coded to cost items, feeding the committed figure.
- Dashboards and KPI reporting: cost roll-ups.
- Asset hierarchy: asset_id and ltree subtree roll-up.
- Site logistics and site inventory: link to cost items instead of a BOQ.

Data
- cost_item: code, description, unit of measure, rate, budget, asset_id, WBS/CTR link.
- rate_schedule: name, version, effective dates, contract assignment; cost item rates belong to a schedule version.
- rate_modifier: work-type condition (access, height, confined space, shift) and its loading.
- measured_quantity: scope task, cost item, quantity, unit, date, resulting priced value.
- import_mapping_template and import_batch: mapping, validation report, rollback state.
- Roll-up values: budget, committed, earned, by cost item and by asset subtree.

Pages
- Cost item list and detail.
- Schedule of rates and version management with contract assignment.
- Import wizard: choose or build mapping template, validation report, confirm or roll back.
- Rate modifier configuration.
- Budget vs committed vs earned roll-up, filterable by asset subtree.
- Measured quantity entry within the scope task view.

Decisions and notes
- Owner selected a thin cost-item module rather than full BOQ and costs; do not import those modules wholesale.
- Owner accepted all five scout suggestions: measured quantity capture, versioned rate schedules, tiered work-type pricing, asset subtree roll-up, and import mapping templates with validation and rollback.
- Contracts and risk modules are only to be added if the change family needs them.
- Suggested phase P3.
- Market-seen abilities not accepted and therefore not in scope: rate build-ups and markup tiers, progress claims generation, multi-currency and tax handling, finance system export, and a forecast roll-up beyond budget, committed and earned.

Open questions
- None recorded where advisors conflict. Still to confirm with the owner: how a contract is represented, given that no contracts register is currently selected, for per-contract rate assignment.

> Comment: Remove this module/costs.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
