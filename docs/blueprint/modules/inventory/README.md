# Stock, consumables & materials (`inventory`)

- **Group:** Field operations
- **Phase:** P1

What materials and consumables are on site, issued to which task, and how much is left.

A movement ledger (received, issued to a task, wasted, transferred) keeps live stock per location. Consumable issuances satisfy the RSW 'requires consumables' flag. Stock status (in stock, out of stock, unavailable) also controls whether expiry and use-by reminders fire.

Features:
- Stock items from the Consumables content type with quantity and unit
- Movements: receipt (from delivery docket), issue to task, waste/shrinkage, transfer
- Consumable issuance per scope task (issued by, quantity, batch)
- Live stock levels, reorder points
- Use-by tracking with suppression when out of stock or unavailable
- Batch/heat traceability into the traceability graph

Interacts with:
- Scopes of work (RSW), disciplines & tasks: issuance per task
- Supplier catalogue, requisitions & POs: receipts from POs
- Certificates, competency & calibration gate: use-by dates
- Traceability graph: components, materials & certificates: batch traceability

AIP repo status and plans:
- Built: consumables ledger (TASKS §18), consumable issuance delete/correct (§33), requires_consumables in the RSW gate (§32)
- Deferred: decrement the asset's own quantity attribute on issuance (real inventory)

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
