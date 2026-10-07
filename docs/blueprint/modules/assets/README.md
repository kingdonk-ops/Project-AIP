# Asset hierarchy & registers (`assets`)

- **Group:** Asset core
- **Phase:** P1

What it is
The asset tree at the centre of the product (Asset core, suggested phase P0), plus the registers (people, equipment, vehicles, consumables, WPS) that use the same model. Assets are the aggregate root, not Project. The tree is owned by the tenant and projects, work packs and campaigns reference assets many-to-many. Every inspection, issue, document, certificate, calibration record, NCR and photo hangs off an asset id (plus project id), so an asset's full history follows it across projects and is not fragmented per project.

What it does
A user builds a tree per project by hand or import (for example Site > Area > Asset > RSW, or Scope Document > Line; for CUI work, site > unit > system > equipment > component/CUI circuit), using item types and categories they define. Registers for staff, vehicles, equipment, consumables and WPS are the same records shown as flat lists. A remediated CUI circuit shows its inspections, NCRs, handover status and post-handover defects in one timeline. Labels are renamable per tenant or market through the shared terminology dictionary (for example Defect, Punch or Deficiency).

Features
- Recursive tree with expand/collapse, open-item counts per node, drag to reparent or reorder (cycle-guarded, ltree path recompute in one transaction with a tenant-scoped lock)
- Context menu: Add Item, Add Module, Bulk Add (name pattern ###, start number, repeats up to 100, apply to tag number), Sort, Import
- Modules cannot be inspected; items can; components are allowed under types with allows_components
- Unique immutable internal tag from the asset id plus an editable, conflict-checked real-world Tag Number
- Asset detail page: attributes form generated from the item type, history timeline, inspections, issues, documents, certificates, child assets, projects in scope, location map, activity
- QR/barcode/RFID tags; scan to open an asset (mobile)
- Printable QR/RFID label sheets and bulk label generation from the tree (PDF rendering via the report engine)
- Criticality, status (custom status mapped to a neutral state), GPS location
- Registers: Staff, Vehicles, Equipment, Consumables, WPS as flat register pages from configuration, with expiry indicators and saved views
- 'Used in' reverse lookup on register items
- Excel/CSV import (async) and export (Excel/CSV/JSON, subtree export)
- Import validation with preview, duplicate and tag-conflict detection, mapping templates and rollback
- Asset history merge and split with lineage when equipment is replaced or renumbered (retag)
- CUI-specific asset fields and condition model: insulation type, jacket, operating temperature range, coating system, corrosion severity grade (promoted to a column so results are comparable across lines and projects)
- Line/circuit and P&ID linkage, with clickable tags on drawings opening the asset
- Risk-based inspection scheduling per asset class, generating due dates and overdue alerts
- Asset condition analytics and defect trends
- Notifications: import completed, failed or has conflicts, inspection overdue, status or criticality changed, asset moved or merged, calibration or certificate expiring, label sheet ready

Interactions
- Content types, item types and attributes: each asset has an item type defining its fields; assets pin the item type version
- Inspections, ITPs and hold points: inspections run against an asset; scheduling generates due inspections
- Traceability graph: welds and components are child assets
- Document library and control: documents attach to assets, including P&ID drawings for tag linkage
- Certificates, competency and calibration gate: people and equipment register items carry certificates
- Offline field app and sync: assets in scope sync to devices
- Projects: scope baseline links projects to assets
- Shared foundation: tenant terminology dictionary and the common state-machine/approval service; records carry tenant_id, project_id and optional asset_id

Data
- Asset: id, tenant_id, parent, ltree path, item type and version, category, internal tag, Tag Number, name, criticality, status and neutral state, GPS location, JSONB attributes validated against the item type schema, CUI fields (JSONB) with promoted corrosion grade, sort order, sync version, soft delete
- Postgres/PostGIS with ltree and JSONB (GiST and btree on path, GiST on location, GIN on attributes); asset_id indexed on inspections, certificates, calibration, documents, issues
- Registers are assets of content types, not separate tables, except the existing consumable_issuances ledger
- Lineage links for merged, split or retagged assets
- Import batches with preview and rollback state; asset tags; RBI schedules

Pages
- Asset tree and register (/assets): collapsible left panel with open-item counts; selecting a node sets the asset scope, shown as a chip that clears in one click; asset table and filters
- Create or edit asset: generated form with parent tree picker
- Asset detail page
- Register pages: Staff, Vehicles, Equipment, Consumables, WPS (/registers/:contentType)
- Import preview and export
- Label sheet generation
- Top scope bar with Tenant, Organisation, Project and Asset-subtree pickers filtering lists and dashboards

Decisions and notes
- Asset is the aggregate root; owner accepted all six scout suggestions listed above.
- Built in AIP: asset CRUD and hierarchy, real tree replacing the flat Scope Portal list (TASKS section 48, asset-hierarchy-design.md), generated attribute form and parent picker (section 16), per-item detail page (section 24), header search deep links (section 26).
- Deferred: Import from the tree context menu; parent reassignment on the detail page.
- Spec E2-S4/S5: Excel/CSV import and export.
- Solo capacity: asset tree plus terminology is sized M and is in the first group for a Kaefer pilot.
- First customer is Kaefer on Rio Tinto remediation work.
- Data advisor recommends keeping ltree (already in the repo, fits single-parent trees).

Open questions
- Closure table versus ltree: advisors named both; the data advisor and the existing repo favour ltree. Owner to confirm ltree stays.
- Phasing of the accepted L-sized items (risk-based scheduling, P&ID linkage) relative to the Kaefer pilot is not yet decided.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
