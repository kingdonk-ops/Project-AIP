# Content types, item types & attributes (`item_types`)

- **Group:** Asset core
- **Phase:** P1

What it is
The configuration layer of the platform (Asset core, suggested phase P0) that lets admins define new kinds of records and their fields without code. It is part of the existing AIP product (FastAPI, async SQLAlchemy, Postgres/PostGIS with ltree and JSONB, React/Vite/TypeScript, shadcn/ui). All type and category names are tenant-renamable so terminology can change per market (first customer: Kaefer on Rio Tinto remediation work).

What it does
Content types (Asset, Staff, Vehicles, Equipment, Consumables, RSW and others) each get a nav entry and register page generated from configuration. Beneath them, item categories and item types define the attribute schema: field types, required flags, expiry-date flags and references. A shared attributes registry lets fields be reused across types. Item types can auto-create ITPs or inspections from default templates. Schemas are versioned, can inherit from a parent type, support conditional and calculated attributes, carry units and tolerances on measurements, and can map custom statuses to neutral lifecycle states. Starter packs let new customers onboard quickly.

Features
- Content types: name (terminology key), icon, sort order, nav entry; drill-down detail page; delete only if unused
- Item categories with Applicable For: Any / Item / Module
- Item types with attribute schema, is_component, allows_components, auto_create_itp/inspection and default templates
- Field types shared with the form designer through one field-type registry: text, number, decimal, date, dropdown, multi-select, measurement, asset/user/document reference (scoped), GPS, QR, photo/video/audio, repeating table, expiry date
- Attributes registry: shared attributes with auto-merge of same label+type fields
- Template fields can sync back to an asset attribute when the inspection is approved
- Default attribute schema per content type
- Server-side validation of asset attributes against the effective schema of their type, including units and tolerances
- Item-type schema versioning: immutable versions, migration preview with impact counts on existing assets and completed inspections when attribute types change, draft, publish (optionally with approval), roll forward and deprecate; assets pin item_type_version; enables the currently deferred editable attribute type
- Starter packs for NDT/CUI, welding, insulation and coating item types and attributes, encoding the owner's domain expertise, held as versioned JSON data
- Conditional and calculated attributes via sandboxed expressions (no arbitrary scripts) with a function allow-list, for example remaining life from thickness and corrosion rate; uses the shared sandboxed evaluator
- Per-item-type custom status sets mapped to neutral lifecycle states, so markets can name statuses locally while reporting and gates rely on stable states (supersedes the earlier planned custom statuses per content type)
- Units and tolerances on measurement attributes with out-of-range flags, feeding the rules engine
- Type inheritance, for example a base Pipe type extended into Insulated Pipe, to reduce duplicated schemas; effective schema resolves parent plus child
- Notifications: schema version published, migration preview conflicts, type deprecated while assets still use it, starter pack updated, attribute merge suggestion

Interactions
- Asset hierarchy and registers: defines every asset's fields
- Form and template designer: same field-type system as inspection templates
- Inspections, ITPs and hold points: auto-create ITPs/inspections per item type
- Terminology dictionary and localisation: type names are tenant-renamable
- Rules engine: consumes tolerances and out-of-range flags
- Reporting and completion gates: rely on the neutral lifecycle states

Data
- Content type: key, name, icon, sort order, nav entry, default attribute schema
- Item category: content type, Applicable For (Any / Item / Module)
- Item type: attribute schema (JSONB), is_component, allows_components, auto_create_itp, auto_create_inspection, default templates, parent type, schema version, status set; maps to or extends the existing entity_types rather than duplicating them
- Attribute: label, field type, required flag, expiry-date flag, reference scope, unit, tolerance, expression (conditional or calculated)
- Attributes registry entries shared across types
- Status set: custom statuses mapped to neutral lifecycle states
- Starter pack definitions
- All tables carry tenant_id with RLS

Pages
- Content type list and drill-down detail page (/admin/content-types)
- Register page per content type, generated from configuration
- Item category and item type editor with attribute schema: two-pane editor with live form preview, own and inherited attributes, assets using this type
- Attributes registry
- Schema version history and migration preview: version timeline, side-by-side diff, impact counts, conflicts
- Status set editor
- Starter pack import

Decisions and notes
- Built in AIP: Content Types (TASKS section 10), drill-down, Attributes registry, Inspection Categories and Disciplines (section 47), is_component (section 34), registers polish with is_expiry_date and scoped pickers (section 19).
- Deferred: rules engine per content type, icon upload, drag reordering of content types, editable attribute type with migration (now to be addressed by schema versioning).
- Owner accepted all six scout suggestions: schema versioning with migration preview, starter packs, sandboxed conditional and calculated attributes, custom status sets mapped to neutral states, units and tolerances, type inheritance.
- OpenConstructionERP (AGPL-3.0) is a feature reference only.
- Advisor recommendations, not yet owner-confirmed: inheritance add-only with override of required, unit and tolerance; neutral states as a fixed enum in code; starter packs product-shipped as global rows plus per-tenant owner-curated imports.

Open questions
- Inheritance rules: can a child type remove or override inherited attributes, or only add? (Advisors suggest add-only, with overrides of required, unit and tolerance.)
- How are existing assets and completed inspections handled when a parent type's schema changes? (Advisors propose a migration preview with assets pinned to a version.)
- What is the sandboxed expression language and which functions are allowed?
- Which neutral lifecycle states are the fixed set for status mapping?
- Are starter packs shipped with the product or maintained as owner-curated, per-tenant importable content? (Advisors suggest both.)

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
