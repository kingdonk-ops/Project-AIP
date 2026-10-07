# Traceability graph: components, materials & certificates (`components`)

- **Group:** Asset core
- **Phase:** P1

What it is
The traceability graph is the core differentiator of the platform. It links everything about a piece of work into one searchable chain: the component, the materials and their certificates, the people who installed and inspected it and their qualifications, the equipment used and its calibration, the task, the ITPs and inspections, and the documents. A weld or repaired component is a child asset carrying welder, WPS, rod and steel details through scoped reference fields. Materials carry digital passports (EN 10204 certificates, batch/heat numbers). Every link is a real reference, so users can ask 'what has this welder worked on', 'where was this batch used' or 'which instrument measured this' and see one chain. Target position: a mid-market alternative to heavy, expensive EPC tools (Hexagon/Intergraph Smart Construction and Completions, Bentley, InEight, Aconex), covering materials, EN 10204 certificates, installer qualifications, calibrated equipment and ITPs per asset.

What it does
All items link together: materials and certificates, the jobs they are used on, the people who installed or inspected (with qualifications), equipment and its calibration certificates, the task, and the asset the task belongs to. All ITPs, inspections and documents relating to a job, equipment item or consumable are linked, recorded and searchable. It supports forward and backward genealogy (heat or batch to every component, and the reverse) and impact analysis when a batch or instrument is found faulty.

Features
- Weld/component item type with welder (Personnel), WPS, rod (Consumables) and steel references
- ScopeTask.component_asset_id: several tasks over time can point at the same component
- Material passports: certificate type (EN 10204 3.1/3.2, CE/UKCA), number, heat/batch, supplier, standard/grade, linked document, use-by date and status (valid, quarantined, superseded, expired)
- Material usage records: to asset, work package and task
- Reverse lookups: 'Used in' for people, consumables, equipment, WPS
- Traceability tab on any record showing the linked graph, with filters by type and depth
- Acceptance criteria and inspection requests (MIR, WIR, IR, hidden works) from construction_control, with a request queue
- Search across the chain (by heat number, welder, instrument serial), permission-aware
- Batch quarantine and impact analysis: one action on a heat, rod batch or instrument lists every affected component, task and inspection and raises NCRs
- Point-in-time validity snapshot on each link: records whether the welder, instrument or material was valid at time of use, frozen (trigger blocks updates to snapshot columns); corrections add a new link and set superseded_by, so later expiry or supersession cannot rewrite history
- Weld map / joint register view, tabular and drawing-based, with welder, WPS, consumable batch, NDT percentage, NDT status, repair count and rejection rate
- Certificate data extraction and cross-check: OCR of EN 10204 certificates with human review, checking heat numbers and grades against the material record to catch wrong or forged certificates
- Welder performance and repair-rate analytics by welder, WPS and consumable batch
- Indexed evidence pack export of the chain as a bookmarked PDF/ZIP with a hash manifest so a client can verify nothing changed after issue

Interactions
- Asset hierarchy and registers: components are child assets; asset_id is the primary anchor
- Certificates, competency and calibration gate: each linked person and instrument must be valid at time of use; expiry alerts raised there; expiry hidden for items marked unavailable
- Stock, consumables and materials: materials and consumables issued; stock status read
- Inspections, ITPs and hold points: ITPs and inspections on the component; NCR written on rejected materials or failed acceptance
- Document library and control: certificates and reports
- Search, retrieval and saved views: chain-aware search
- Procurement and supplier catalogues: supplier and delivery data read where available
- Report engine and signing: evidence pack generation
- Upload/ingestion: OCR extraction of scanned certificates

Data
- Postgres relational model with foreign keys and recursive CTEs; no graph database
- Typed entity_links table: tenant_id, project_id, asset_id (anchor), from/to type and id, link_type (welded_by, uses_wps, uses_batch, measured_with, inspected_by, evidenced_by), used_at, valid_at_use, validity_snapshot (JSONB: certificate ids, expiry dates, calibration status), source_inspection_response_id, superseded_by, sync_version, soft delete; indexed by from, to and asset, with a uniqueness rule on active links
- Material passport, material usage, acceptance criteria, inspection request and quarantine action records
- Existing: weld/component tracking (TASKS section 20), consumables ledger (section 18), 'Used in' column, scoped reference pickers (section 19); reuses assets, certificates, documents, inspections, inspection_responses, issues, consumable_issuances, tasks
- Backend module backend/app/modules/components with links, graph, passports, cert_extraction, quarantine, weld_map, analytics and evidence_pack components; new link types and certificate kinds are configuration rows
- Settings: link types and allowed relationships, snapshot rules, OCR provider and review requirement, cross-check tolerances, quarantine permissions and auto-NCR behaviour, acceptance criteria templates, evidence pack format and retention, search permission scope

Pages
- Material and Certificate Passports page under Inspection and Quality (/quality/passports): search-first register with filters (certificate type, status, supplier, project, linked document, OCR review pending)
- New passport with OCR review (split view: document viewer and extracted fields with confidence and cross-check results)
- Passport detail: summary, certificate viewer, traceability graph, forward and backward genealogy, validity snapshots, linked inspections/ITPs/NCRs, documents, quarantine history, activity
- Traceability graph view for an asset, task, batch, person or instrument (/trace/:type/:id), permission-aware with masked or hidden nodes and a table fallback
- Traceability tab on any record
- Inspection request queue
- Weld map / joint register
- Quarantine impact report and evidence pack export
- Notifications: OCR ready for review, cross-check mismatch, batch quarantined, impact report ready, NCR raised, inspection request assigned or overdue, expiring certificate or use-by, evidence pack ready

Decisions and notes
- Owner's construction_control comment defines the linkage and takes precedence.
- No dependency on bim_hub; BIM/element links are deferred and optional, and asset_id is the anchor.
- Postgres relational model, not a graph database.
- Accepted: batch quarantine and impact analysis, point-in-time validity snapshot, weld map/joint register, certificate extraction and cross-check, welder performance analytics, indexed evidence pack.

Open questions
- Typed entity-link table (architecture advisor) versus explicit foreign keys per relationship (lead programmer): not decided. The data model advisor suggests a hybrid, with entity_links for the cross-cutting graph and search plus typed tables (weld_records, material_usages) for high-volume weld relationships; the owner has not chosen. The choice stays hidden behind links.py and graph.py.
- Phase: P1 (brief, data model advisor) or Phase 2 (delivery manager).
- OCR approach and review workflow for certificate extraction.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
