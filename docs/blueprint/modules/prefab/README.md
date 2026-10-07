# Prefab & off-site manufacture (`prefab`)

- **Group:** Handover & asset lifecycle
- **Phase:** P4

What it is
Prefab & off-site manufacture tracks off-site manufactured units (spool pieces, insulation or cladding panels, scaffold components, skids, modules, later pods) from design release through production, transport, receipt and installation. Each unit is an asset and carries an ordered stage register with inspection hold points at the factory and on arrival. It sits in the Handover & asset lifecycle group (suggested phase P4). It is not yet built in AIP, and the delivery advisor had deferred it. It is niche for remediation work, so it stays low priority. It is useful to Kaefer for fabricated insulation and scaffold components, and to later markets for pods and modules. The differentiator against Procore, Autodesk Construction Cloud, Trimble tools, Tekla, schedulers and spreadsheets is that every unit is tied to an asset node with inspection and ITP hold points.

What it does
- Registers units with type, mark number, revision, destination asset and status.
- Runs each unit through an ordered stage register (fabrication, QA, pack, dispatch, transport, receipt, installation) with hold points at the factory and on arrival.
- Generates the ITP automatically from a stage template per unit type.
- Blocks dispatch and installation while holds, NCRs or expired inspector or welder certificates are open.
- Records shipments, loads and receipt checks with evidence.
- On installation, creates or updates the destination asset and carries the unit's records to it.
- Produces the off-site delivery inspection list and report, and a handover check that all documents, MDR and files have been handed over.

Features
- Unit register with stages and a status pipeline.
- Stage templates per unit type that instantiate ITPs automatically on unit creation, reusing the existing inspection engine.
- Factory inspections and receipt inspections.
- Release-for-dispatch and release-for-install gates, reusing the RSW completion gate and certificate hard-block pattern.
- Unit BOM linked to component, material and certificate traceability (heat number to unit to asset).
- Receipt inspection on arrival with damage photos and auto-NCR.
- Shipment and load records with packing list and QR/barcode labels, working offline in the field app and updating unit status.
- Transport tracking.
- Installation sign-off.
- On installation, create or update the destination asset and carry fabrication history to it.
- Pre-fab off-site delivery inspection list and report (owner request).
- Handover check that all documents, MDR and files have been handed over (owner request).

Interactions
- Asset hierarchy & registers: units are assets; installed units create or update the destination asset.
- Inspections, ITPs & hold points: stage inspections and generated ITPs.
- Documents: shop drawings and handover files.
- Certificates: inspector and welder expiry checks in the gates.
- Components and weld tracking: BOM, heat numbers, MTRs and weld maps.
- Issues and corrective actions: NCR raised on failed inspection or receipt damage.
- Projects and users, notifications.
- Also suggested by earlier advisor notes (modules to confirm): schedule_advanced for install windows, procurement for material orders and suppliers, site_logistics for laydown and delivery slots, and site_inventory for arrivals.
- Closeout evidence (as-built, test certificates) feeds the handover data book and later CUI inspection.

Data
- PrefabUnit: type, mark number, revision, destination asset_id, status, sequence, design-release status.
- ProductionStage: fabrication, QA, pack, dispatch, defined by stage templates per unit type with sequence dependencies.
- TransportLoad / shipment: packing list, carrier reference, status events, ETA, QR/barcode labels.
- Receipt check: results, damage photos, linked NCR.
- InstallationSlot.
- Unit BOM: components, materials, heat numbers, MTRs, certificates.
- Handover document checklist per unit.

Pages
- Unit register with status pipeline.
- Production and sequence board.
- Delivery and install tracker.
- Off-site delivery inspection list and report.
- Handover completeness view.

Decisions and notes
- Owner accepted all six feature suggestions: stage templates with auto-ITP, dispatch and install gates, BOM traceability, receipt inspection with auto-NCR, shipment records with QR/barcode, and asset create/update on installation.
- Owner comment: the module must provide a pre-fab off-site delivery inspection list and report, and handover must ensure all documents, MDR and files have been handed over.
- Terminology must be renamable per market.
- Competitor information is uncertain; the researcher was unsure of exact competitor features.

Open questions
- Should witness notification to client and third-party inspectors at factory hold points be included? The feature scout saw it in the market, but nobody has proposed it and the owner has not decided.
- Should percent-complete rollup and install slot planning against crane and laydown windows be in scope, or deferred with schedule_advanced and site_logistics?
- Should procurement and site_inventory integrations be included, given those modules may not exist in AIP?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
