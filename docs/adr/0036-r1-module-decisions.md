# ADR 0036: R1 module decisions (PLAN-R1 gate)

- **Status:** proposed (accepted at the PLAN-R1 phase-entry review)
- **Date:** 2026-10-18
- **Affects:** portal, assets, item_types, forms, inspections, eligibility, scope_work, issues, report_engine, data_io, terms, uploads; PLAN-R1 and every R1 task

## Context

PLAN-R1 generates the R1 "Kaefer live" tasks (ADR 0007 §4). The just-in-time process
([docs/reviews/07-delivery.md](../reviews/07-delivery.md), step 2) gates generation on each module's README
"Open questions": answered ones become ADR lines, settled ones are recorded with the task or ADR that settled them,
and the rest go to [OPEN-QUESTIONS.md](../../tracking/OPEN-QUESTIONS.md) under "R1 gate", with any task that needs
the answer set to `blocked`. PLAN-R1's spec named this ADR 0009, but 0009 is the OCR decision, so it is 0036.

Apart from #42 (portal, answered on 2026-10-18) and #45 (already in 01-decisions), none of the R1 modules' open questions had an owner answer yet. The lines below are settled by ADRs or P0 work, or
are choices PLAN-R1 made to cut tasks; the phase-entry review accepts or changes them.

## Decision

### Owner answers

- portal: the client portal is in R1 (answered 2026-10-18, OPEN-QUESTIONS #42). This changes ADR 0007 §4, which put
  the portal after R1. The R1 portal slice is what client sign-off needs: external users and grants, sign-in on the
  portal's own origin, the portal app with a "needs my action" inbox, client review and hold-point release, witness
  attendance, client reports and the internal admin page. Share packs, subcontractor NCR responses, the onboarding
  gate, the condition dashboard, watermarking and per-client branding stay after R1 (ADR 0007 §5, defer by default).
- portal: clients sign in with their own username and password plus the second step local accounts require, and sign
  off in the portal; PIN on the inspector's tablet stays an optional route behind `holdpoint_client_pin_only`
  (answered 2026-10-10, ADR 0010 addendum part 2). This replaces ADR 0005's "magic link" row for portal users.
- portal: sign-up needs no second approval: the project admin who invites a client is the approval, and the client
  is active from their first sign-in (answered 2026-10-18; replaces the README's "named internal owner" approval).
- portal: client access is per project and expires after the project's `portal_access_days` setting, 180 days by
  default and at most 400. The project admins are reminded 30, 20, 10 and 1 days before expiry; renewing grants another
  period and stops the reminders; an ignore option stops them; with neither, the admins get a notice on the expiry day
  saying the access expired and how to renew it (answered 2026-10-18; PORTAL-01, PORTAL-07, PORTAL-08).
- portal: the witness notice period and waiver rule are project settings (answered 2026-10-18, OPEN-QUESTIONS #55;
  PROJECTS-04, PORTAL-06).
- R1 target date: 2027-03-31 still holds with the portal in R1 (answered 2026-10-18, OPEN-QUESTIONS #56).
- scope_work: access methods are Ground, Rope access, Scaffold, MEWP and Ladder (MEWP and Ladder split), as a tenant-editable list (answered in [01-decisions](../blueprint/01-decisions.md), owner decisions; the en-AU labels shipped with TERMS-01). SCOPEWORK-06 seeds them.

### Settled by earlier ADRs or P0 work

- assets: the tree stays on ltree, not a closure table (settled by ADR 0002 and DATABASE-04 `aip.platform.db.ltree`, 2026-10-14).
- assets: risk-based scheduling, P&ID linkage, label sheets, lineage merge/split and QR/RFID scanning are after R1; R1 is the tree and register (settled by ADR 0007 §4–5, 2026-10-10).
- item_types: conditional and calculated attributes, when built, use JSONLogic with the approvals allow-list, never scripts (settled by ADR 0001 "Shared rules" and ADR 0035 §1, 2026-10-18).
- forms: no designer in R1; templates are operator-authored JSON uploaded through the API, so the builder-foundation question (custom, react-jsonschema-form, SurveyJS) waits for the designer (settled by ADR 0007 §4, 2026-10-10).
- forms: JSONLogic, not CEL, with one Python and one TypeScript evaluator proven on shared golden vectors in `packages/contracts/jsonlogic-vectors/` (settled by ADR 0001 and APPROVALS-02, 2026-10-18).
- inspections: the lifecycle runs on the approvals engine (versioned definition, transition service, hash-chained decisions), not XState or a bespoke workflow table (settled by APPROVALS-01, APPROVALS-02 and APPROVALS-05).
- eligibility: reminders run as Procrastinate jobs from the OPS-13 scheduler under the OPS-17 handler role (settled by ADR 0003, OPS-13 and OPS-17).
- eligibility: expiry is evaluated in UTC with calendar-day boundaries (settled by ADR 0025, 2026-10-13); the README's AWST note is presentation only.
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
7. **Portal users are local Keycloak accounts on a separate portal client.** Following ADR 0005 (no in-app
   passwords or MFA), a client is invited through identity's invite flow into the tenant realm and signs in through a
   dedicated `aip-portal` OIDC client on the portal's own host (ADR 0026 §3). The API issues a separate portal
   session cookie with its own idle timeout, and portal sessions reach only an allow-listed set of routes. A portal
   user is an `app_user` with an external user class whose permissions come only from explicit `portal_grants`
   (project, optional asset subtree, action), never from inherited roles.
8. **INSPECTIONS-03 is the R1 midpoint** that gates PLAN-P2 (rolling horizon).
9. **A host module owns later versions of its own record type's workflow preset.** Guards must live in the
   definition, because a transition through `/api/v1/approvals` bypasses the host module's routes. APPROVALS-05 ships
   a guard-free v1 of `inspection.standard` for its lifecycle golden tests; INSPECTIONS-02 and INSPECTIONS-03 each
   publish the next version (adding the submit guards) through `ApprovalsApi.install_preset` (APPROVALS-08), as
   ISSUES-03 does for `issue.standard`. Instances stay pinned to the version they started on, which is harmless
   because no real inspections exist before INSPECTIONS-02.
10. **`move` is an edit-level verb.** `asset.move` stays a separate code an admin can withhold, and ACCESS-07 adds
    `move` to the `edit` level of the ADR 0027 expansion so default roles that edit assets can reorganise the tree.
11. **Calculated fields and repeating sections are in R1** (owner, 2026-10-18): FORMS-07 adds a forms-only
    arithmetic extension to the shared evaluator (the approvals guard allow-list stays unchanged), and FORMS-08 adds
    repeating sections and grid fields; FORMS-05's seed templates use both.
12. **Ignoring expiry reminders silences the rest of that access period,** including the expiry-day notice; renewing
    later starts a new period with reminders again. (The owner asked for "a way to ignore notifications"; this is
    PLAN-R1's reading of it.)
13. **Everything left out of R1 is listed** in [`tracking/BACKLOG.md`](../../tracking/BACKLOG.md), with its source and
    the reason.

## Consequences

- The R1 board section, its stubs and the first three full specs per module follow these lines; the task linter
  (`tools/lint_tasks.py`) enforces the Python layout on every R1 row.
- Blocked R1 rows: ITEMTYPES-05 (#40), ITEMTYPES-06 (#41), ISSUES-06 (#46), DATAIO-04 (#54), and none in the portal (#55 answered). Each becomes `todo` when the owner answers and this ADR gains the answer line.
- A change to any choice above re-runs the generator for that module only (07-delivery process step 6).
