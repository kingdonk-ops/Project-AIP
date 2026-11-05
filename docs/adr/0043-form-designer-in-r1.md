# ADR 0043: The form designer comes into R1 and the demo slice

- **Status:** accepted
- **Date:** 2026-11-05
- **Affects:** forms (FORMS-11, FORMS-12, FORMS-07, FORMS-08); amends ADR 0007 §4 and ADR 0036 (forms, "no designer in R1")

## Context

ADR 0007 §4 left every designer out of R1, and ADR 0036 recorded that forms ship as operator-authored JSON: FORMS-04
gives admins a register where they upload a template as JSON, check it against the server lint, publish it and compare
revisions. That works for a developer. It does not work for a Kaefer quality admin, and "publish a form template" is a
step of the demo loop (DEMO-SLICE-PLAN). The backlog held the designer with the note "No designer in R1; templates
are JSON".

On 2026-11-05 the owner asked for the designer to come into R1 and into the demo slice.

The open question that kept it out was the builder foundation: a custom builder, react-jsonschema-form or SurveyJS
Creator (forms README, "Open questions"). Since then the pieces a designer needs have shipped:

- the template contract (`packages/contracts/forms/form-template.schema.json`, FORMS-01, schemaVersion 2 from FORMS-10);
- the server lint (`POST /forms/lint`) and the draft, replace and publish API (FORMS-01);
- the shared evaluator and the `@aip/form-renderer` React renderer (FORMS-02, FORMS-03);
- the register and detail pages (FORMS-04).

## Decision

1. **The form designer is in R1 and in the demo slice**, as two tasks in the `forms` module:
   - **FORMS-11**: a three-pane designer (palette, canvas, properties) that edits a draft revision's schema with no
     JSON, a live preview through `@aip/form-renderer` at desktop and phone widths, server lint as you go, save and
     publish.
   - **FORMS-12**: the logic builder (`visibleIf`, `requiredIf`, `failWhen`, section rules) and a test console that runs
     sample answers through the shared evaluator.
2. **The foundation is a custom builder over our own contract.** react-jsonschema-form edits JSON Schema, which is not
   our template contract, and has no JSONLogic. SurveyJS Creator has its own schema and a commercial licence. A custom
   builder edits the FORMS-01 contract directly, previews with the renderer inspectors will use, and checks with the
   same lint and evaluator. So the designer cannot make a template that the API, the renderer or the evaluator reads
   differently.
3. **Drag and drop uses `@dnd-kit/core` and `@dnd-kit/sortable` (MIT)** with its keyboard sensor. Every drag has a
   button or keyboard alternative (move up and down, move to section), so the designer meets the axe and keyboard rules.
4. **JSON stays a first-class path.** The FORMS-04 upload and the designer's JSON view edit the same schema. Fields
   the designer cannot edit yet keep their values and are shown as set.
5. **Still deferred** (BACKLOG): print layout preview and report slot mapping, offline device preview, the template
   approval workflow, the reusable section and question library inside the designer (FORMS-06 builds the library
   itself), the template import assistant, and the form settings page. FORMS-07 (calculated fields) and FORMS-08
   (repeating sections and grids) each add their own palette entry and property panel when they land.

## Consequences

- R1 grows by two M web tasks. Both run in the web stream and touch only `apps/web/src/features/forms/`, so they can run
  alongside INSPECTIONS-04 without lengthening the critical path.
- FORMS-11 adds `expectedSyncVersion` to the replace-draft call (`PUT /forms/revisions/{id}`), because autosaving
  editors need a conflict check that the JSON upload did not.
- ADR 0007 §4 ("Designers ... come later") and ADR 0036 (forms: "no designer in R1") no longer apply to the form
  designer. They still apply to the other designers (workflow, report template, handover).
- The forms README's "builder foundation" question is closed.
- `tracking/BACKLOG.md` strikes the form designer row with FORMS-11 and FORMS-12 and keeps the deferred parts above.
