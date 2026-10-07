# Form & template designer (`forms`)

- **Group:** Inspection & quality
- **Phase:** P1

What it is
The no-code builder for every checklist, inspection, ITP, permit and test report. Admins build templates from sections and fields, with conditional logic, calculations and validation, then publish a frozen revision. Field inspections always keep the revision they started on. It covers real-world reports such as coating and blasting ITRs, UTT thickness surveys, vehicle pre-starts, generator maintenance, bolt torque, welding, spraying, concrete pours and CUI inspections. This is the core wedge: complex engineering inspections tied to asset ID, calibrated instruments and signer qualifications are poorly served by competitors such as SafetyCulture, Procore Forms and Fieldwire.

What it does
Provides full form design with control options, validation and customisation, and custom layout, so complete inspections can be digitised. The owner's request for 'Java validation' is read as scripting-style validation; it is delivered as sandboxed declarative expressions, never user-authored code.

Features
- Sections and grid/tabular layouts; custom layout per template
- Field types: text, long text, number, decimal, date, datetime, boolean, dropdown, multi-select, radio, measurement (value+unit), asset/user/document reference, photo, video, audio, signature, GPS, QR/barcode, repeating table, calculated; instrument/calibration reference
- Conditional visibility/required (visible_if, required_if) with a condition-builder UI
- Calculated fields with a restricted formula language (e.g. corrosion rate, DFT average) and a function allow-list
- Validation rules per field and per row in repeating tables; sandboxed expressions (JSONLogic/CEL) rather than arbitrary scripts, evaluated server-side
- Template lifecycle: draft > approved > retired; multi-draft revision history; clone, archive, export/import; delete/restore; optional approval workflow
- Template kinds: inspection, ITP, RFI (also permit and test report); concurrent inspections allowed per template
- Required competency and default frequency per template
- Shared evaluator (TypeScript package, Python port tested on the same fixtures) used by web and mobile so logic behaves identically
- Reusable section and question library (e.g. DFT readings, environmental conditions, weld details), versioned
- Instrument-reference field with calibration check: a reading cannot be recorded with an out-of-calibration gauge, and the instrument appears in the traceability chain
- Context auto-fill and prefilled fields (asset tag, RSW number, location, procedure)
- Test-fill and publish checks: run formulas and rules on sample answers, flag broken references, block publish when tests fail
- Print-accurate report layout mapping from fields to designed PDF slots
- Spreadsheet or PDF template import assistant with AI-assisted field detection and human review

Interactions
- Inspections, ITPs and hold points: every inspection is a filled template pinned to template_revision_id; failures can raise NCRs and tasks
- Content types, item types and attributes: shares the field-type registry
- Rules and validation engine: validation expressions
- Report engine and published records: report templates map form fields to report slots; PDF to documents
- Offline field app and sync: templates sync to devices
- Certificates, competency and calibration gate: inspector competency and instrument checks
- Terminology: labels via the tenant terms dictionary

Data
- form_templates: tenant, unique code, name, kind, discipline_id, entity_type_id, default_frequency, required_competency, status, current_revision_id, archived_at, sync_version, soft delete
- form_revisions: template_id, revision_no, status, frozen JSONB schema (sections, fields, layout, conditions, formulas, validations), schema_hash (sha256 at publish), evaluator_version; a trigger blocks updating schema once status is not draft; submitted records are immutable
- Reuses disciplines, entity_types, documents
- Template seed library as data: coating/blasting ITR, UTT survey, vehicle pre-start, generator maintenance, bolt torque, welding, spraying, concrete pour, CUI; new industry templates are seeds only; new field types need a registry entry, a runtime component and an evaluator entry
- Definition lint: field references, calculation cycles, expression parse check
- Settings: approval and approver roles, allowed field types, expression limits, default units by market, option lists, revision retention, enabled and renamable template kinds, mandatory fields on create, layout defaults, starter packs
- Built: Template Designer (TASKS 5), field-type expansion (12), real coating ITR template (13), media field types (23), delete/restore (29), multi-draft history (39)
- Deferred: visible_if/required_if, calculated fields, sandboxed expressions (E3-S2/S3/S4), signature field, grid layout

Pages
- Template register (/templates): filters by kind, category, status, competency; deleted toggle
- Create template (/templates/new): basics, start from blank, clone or starter pack
- Template detail (/templates/:id): summary, revision history and compare, usage, report slot mapping, audit trail
- Designer (/templates/:id/revisions/:rev/design): three panes (palette, canvas, properties and validation) with logic builder, print preview, mobile/offline preview, test console and lint results
- Revision comparison with restore as new draft
- Located under Inspection and Quality > Form Builder and Library
- Notifications: draft submitted, revision approved or rejected, template retired with inspections in flight, failing tests, deleted or restored, shared list changed

Decisions and notes
- Owner's comment (full design, validation, custom layout, full inspections) stands; all advisors agree to replace arbitrary script with CEL or JSONLogic, so PRD's quickjs/isolated-vm option is dropped.
- Never execute user-supplied code in the API process; freeze each revision as data.
- Phase 1 flagship; every submission anchors to an asset node.
- All six scouted suggestions accepted.

Open questions
- Builder foundation: custom builder, react-jsonschema-form or SurveyJS Creator (commercial licence); not decided.
- CEL versus JSONLogic: advisors name both; not chosen.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
