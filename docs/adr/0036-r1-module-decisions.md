# ADR 0036: R1 module decisions (PLAN-R1 gate)

- **Status:** proposed (accepted at the PLAN-R1 phase-entry review)
- **Date:** 2026-10-18
- **Affects:** assets, item_types, forms, inspections, eligibility, scope_work, issues, report_engine, data_io, terms, uploads; PLAN-R1 and every R1 task

## Context

PLAN-R1 generates the R1 "Kaefer live" tasks (ADR 0007 §4). The just-in-time process
([docs/reviews/07-delivery.md](../reviews/07-delivery.md), step 2) gates generation on each module's README
"Open questions": answered ones become ADR lines, settled ones are recorded with the task or ADR that settled them,
and the rest go to [OPEN-QUESTIONS.md](../../tracking/OPEN-QUESTIONS.md) under "R1 gate", with any task that needs
the answer set to `blocked`. PLAN-R1's spec named this ADR 0009, but 0009 is the OCR decision, so it is 0036.

None of the R1 modules' open questions had an owner answer yet. The lines below are settled by ADRs or P0 work, or
are choices PLAN-R1 made to cut tasks; the phase-entry review accepts or changes them.

## Decision

### Settled by earlier ADRs or P0 work

- assets: the tree stays on ltree, not a closure table (settled by ADR 0002 and DATABASE-04 `aip.platform.db.ltree`, 2026-10-14).
- assets: risk-based scheduling, P&ID linkage, label sheets, lineage merge/split and QR/RFID scanning are after R1; R1 is the tree and register (settled by ADR 0007 §4–5, 2026-10-10).
- item_types: conditional and calculated attributes, when built, use JSONLogic with the approvals allow-list, never scripts (settled by ADR 0001 "Shared rules" and ADR 0035 §1, 2026-10-18).
- forms: no designer in R1; templates are operator-authored JSON uploaded through the API, so the builder-foundation question (custom, react-jsonschema-form, SurveyJS) waits for the designer (settled by ADR 0007 §4, 2026-10-10).
- forms: JSONLogic, not CEL, with one Python and one TypeScript evaluator proven on shared golden vectors in `packages/contracts/jsonlogic-vectors/` (settled by ADR 0001 and APPROVALS-02, 2026-10-18).
- inspections: the lifecycle runs on the approvals engine (versioned definition, transition service, hash-chained decisions), not XState or a bespoke workflow table (settled by APPROVALS-01, APPROVALS-02 and APPROVALS-05).
- eligibility: reminders run as Procrastinate jobs from the OPS-13 scheduler under the OPS-17 handler role (settled by ADR 0003, OPS-13 and OPS-17).
- eligibility: expiry is evaluated in UTC with calendar-day boundaries (settled by ADR 0025, 2026-10-13); the README's AWST note is presentation only.
- scope_work: access methods are Ground, Rope access, Scaffold, MEWP and Ladder (MEWP and Ladder split), as a tenant-editable list (answered in [01-decisions](../blueprint/01-decisions.md), owner decisions; the en-AU labels shipped with TERMS-01). SCOPEWORK-06 seeds them.
- issues: cost impact does not flow to cost-of-poor-quality or variations in R1, because neither module is in R1 (settled by ADR 0007 §4).
- data_io: R1 data_io is the import of Kaefer's records plus generic CSV/XLSX import; tenant export stays with TENANCY-07, and restore, scheduled and project-scoped exports are after R1 (settled by ADR 0007 §1 and §4, ADR 0022).

### Choices PLAN-R1 made (accepted or changed at the phase-entry review)

1. **Answers live in inspections.** ADR 0007 puts "append-only responses" in the forms slice. Only inspections
   fill forms in R1, so `inspection_responses` (append-only, DATABASE-05 template) and the
   `inspection_current_responses` view belong to inspections (INSPECTIONS-02). Forms owns templates, frozen
   revisions and the evaluator (FORMS-01, FORMS-02).
2. **Assets start untyped.** ASSETS-01 builds the tree without item-type columns so the critical path starts in
   R1 wave 1; ASSETS-02 adds the pinned `item_type_version_id` and validated attributes.
3. **A field-type registry in item_types** (ITEMTYPES-01), published as JSON in `packages/contracts/field-types/`,
   is the one list both item-type attributes and form fields use.
4. **Server-side file access is an uploads task.** report_engine must store a generated PDF and data_io must read
   an uploaded file; neither may touch uploads tables. UPLOADS-08 adds `store_generated_file`, `get_stored_file`
   and `open_stored_file` to the uploads published interface.
5. **Reports store a hash only.** Until the sealing questions are answered (OPEN-QUESTIONS #47–#49), an issued PDF
   is pinned to its template version and data snapshot and records its sha256; no seal or external signature.
6. **TERMS-06 is narrowed to import aliases** (`resolve_alias`, `map_headers` over the TERMS-01 `term_alias` table). Glossary tooltips and search
   expansion wait for a search module.
7. **No portal or client-review step in R1** until OPEN-QUESTIONS #42 is answered: ADR 0007 keeps the portal out of
   R1, while the owner's 2026-10-10 answer (PLAN-R1 "Carried forward, part 2") says clients sign hold points in the
   portal. INSPECTIONS-05 is `blocked` on it.
8. **INSPECTIONS-03 is the R1 midpoint** that gates PLAN-P2 (rolling horizon).

## Consequences

- The R1 board section, its stubs and the first three full specs per module follow these lines; the task linter
  (`tools/lint_tasks.py`) enforces the Python layout on every R1 row.
- Blocked R1 rows: ITEMTYPES-05 (#40), ITEMTYPES-06 (#41), INSPECTIONS-05 (#42), ISSUES-06 (#46),
  DATAIO-04 (#54). Each becomes `todo` when the owner answers and this ADR gains the answer line.
- A change to any choice above re-runs the generator for that module only (07-delivery process step 6).
