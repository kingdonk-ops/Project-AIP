# INSPECTIONS-04 — Inspection register and detail pages with the form renderer

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: full spec written 2026-11-04 (stub replaced); photo/signature capture split to INSPECTIONS-14 (owner 2026-11-04); ITP and report tabs split to INSPECTIONS-15 (task linter: size at most M) -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-04, DESIGN-09, FORMS-03, INSPECTIONS-03, INSPECTIONS-10 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md) and
   [`ui-layout.md`](../../docs/blueprint/modules/inspections/ui-layout.md) (the "Inspection register", "Create
   inspection" and "Inspection detail" pages only)
3. Task files for the API this page drives: [INSPECTIONS-01](INSPECTIONS-01.md), [INSPECTIONS-02](INSPECTIONS-02.md),
   [INSPECTIONS-03](INSPECTIONS-03.md), [INSPECTIONS-10](INSPECTIONS-10.md); the renderer
   [FORMS-03](FORMS-03.md) (including its delivery notes); the register pattern [REPORTS-04](REPORTS-04.md)
4. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0010](../../docs/adr/0010-signoff-assurance.md)
   (sign-off assurance, countersign), [0018](../../docs/adr/0018-module-groups-and-navigation.md) (Quality and
   compliance menu), [0025](../../docs/adr/0025-time-and-timezones.md) (local time only at presentation),
   [0035](../../docs/adr/0035-transition-service-implementation.md) §3–5 (401 `STEP_UP_REQUIRED`, 202 countersign),
   [0036](../../docs/adr/0036-r1-module-decisions.md), [0041](../../docs/adr/0041-inspection-completion-locks-and-submit.md)
   (section and report ticks, guarded submit)
5. DESIGN-09 (panels, tinted chips; build the pages on it). Code: `apps/api/aip/modules/inspections/{routes,schemas,service,responses,itp,acknowledgements,policies}.py`,
   `apps/api/aip/modules/report_engine/providers/inspection.py` (how it already resolves asset, form and user labels),
   `packages/form-renderer/src/{FormRenderer,adapters}.tsx`, `packages/ui/src/patterns/{RecordDetail,WorkflowBar}.tsx`,
   `apps/web/src/features/reports/` and `apps/web/src/features/identity/step-up.ts`, `config/workflows/inspection_standard.json`

## Spec

Give staff the inspection pages the demo slice drives end to end: a register at `/inspections`, a create dialog, and
a detail page at `/inspections/:id` with the workflow bar, the answers rendered and saved through the FORMS-03
renderer, the section and report tick boxes and guarded submit (INSPECTIONS-10) and the decision history (tag: extend; AIP "Register", inspection detail and
lifecycle, PRD inspections pages).

The API already does the work (INSPECTIONS-01/02/03/10); this task adds only what the page cannot get today:
human labels (asset, template, user names) and the pinned form for a viewer who has `inspection.view` but not the
template catalogue's `form.view`, plus what the caller may do on this inspection's project.

**Out of scope:** the ITP tab (steps editor, step actions, sign-off chips) and the report tab (INSPECTIONS-15, which
builds on this page and on the labels and `can` added here); photo and signature capture and the server check that such an answer names a clean stored file
(INSPECTIONS-14: until then those fields render read-only with `forms.renderer.adapter_missing`, so demo templates
must not make them required); the review queue `/inspections/review`, bulk actions, saved views and the board and
calendar toggles; the ITP progress page `/itps/:id`; the booking button on witness steps (INSPECTIONS-12); the
eligibility banner (ELIGIBILITY), issues raised, linked tasks, evidence and instruments, related inspections; the
client review step and client sign-off chips (INSPECTIONS-05); an assignee picker (the R1 lifecycle's `assign`
actions carry no assignee); the mobile step view and offline (field app); per-field answer history on the page (the
API has it; a later row).

- **files**:
  - apps/api/aip/modules/inspections/labels.py (new: batch label lookups through the published APIs)
  - apps/api/aip/modules/inspections/schemas.py
  - apps/api/aip/modules/inspections/service.py
  - apps/api/aip/modules/inspections/responses.py
  - apps/api/aip/modules/inspections/itp.py
  - apps/api/aip/modules/inspections/acknowledgements.py
  - apps/api/aip/modules/inspections/routes.py
  - apps/api/aip/modules/inspections/tests/test_labels_db.py
  - apps/api/aip/modules/inspections/tests/test_form_route_db.py
  - apps/api/tests/access/idor_routes.toml
  - config/terms/en-AU/inspections.json
  - packages/api-client/** (regenerated)
  - packages/form-renderer/src/FormRenderer.tsx, FormSection.tsx, FormRenderer.test.tsx (`lockedSections` prop)
  - apps/web/src/features/inspections/{nav.ts,search.ts,columns.tsx,states.ts,InspectionsRegister.tsx,CreateInspectionDialog.tsx,InspectionDetail.tsx,AnswersTab.tsx,AcknowledgementBar.tsx,TransitionDialog.tsx,HistoryTab.tsx,adapters.ts,inspections.css}
  - apps/web/src/features/inspections/__tests__/{register,detail,answers}.test.tsx
  - apps/web/src/routes/_app/inspections/{index.tsx,$inspectionId.tsx}
  - apps/web/src/router.ts
  - e2e/web/inspections.spec.ts, e2e/web/inspections-live.spec.ts
- **steps**:
  - 1. **Labels on reads** (`labels.py`, used by `service.py`, `responses.py`, `itp.py`, `acknowledgements.py`). One
    lookup per request, deduplicated by id, only through published interfaces (`AssetsApi.get_asset`,
    `AssetsApi.get_ancestor_names`, `FormsApi.get_revision`, `FormsApi.get_template`,
    `identity.api.get_display_names`); never another module's tables.
    - `InspectionOut` (list and detail) gains `assetLabel` (`"<tagNumber> <name>"`, or `name` when there is no tag;
      `null` if the asset is gone), `templateCode`, `templateName`, `revisionNo` and `createdByName`.
    - `InspectionDetail` also gains `assetPath` (the ancestors' names, root first, as the report provider builds
      them) and `can: {respond, reviewEdit, acknowledge, manageItp, reinspect}`: what the caller may do on this
      inspection's project **now** (permission and state together: `respond` = `inspection.respond` and state in
      `RESPOND_STATES`; `reviewEdit` = `approvals.inspection.review` and state in `REVIEW_EDIT_STATES`; `acknowledge`
      = `respond`; `manageItp` = `itp.manage` and kind `itp` and no step started; `reinspect` = `inspection.create`
      and state `performed`). The web never guesses permissions from the tenant-wide list.
    - `AnswerOut` and `ResponseEntry` gain `respondedByName`; `InspectionDecision` gains `actorName`; `SignoffEntry`
      gains `signerName`; `AcknowledgementState` gains `byName`. A user unknown to identity gives `null`, never an
      error.
    - The list stays one query plus at most one lookup per distinct asset and revision on the page (limit ≤ 100).
      Note in the PR that a batch `AssetsApi.get_assets` would remove the per-asset calls (a follow-up row, not
      this task).
  - 2. **Pinned form route** `GET /api/v1/inspections/{id}/form` (operation `inspections_form`, `inspection.view` on
    the project) → 200 `{revisionId, templateCode, templateName, revisionNo, schemaHash, schema}` from
    `FormsApi.get_revision(template_revision_id)`. Another tenant's inspection → 404 (RLS, before any permission
    check); a revision `get_revision` no longer returns → 404 `REVISION_NOT_FOUND` (logged with the inspection id).
    Add it to `tests/access/idor_routes.toml` (`inspections`).
  - 3. **Renderer section locks** (`packages/form-renderer`): `FormRendererProps` gains
    `lockedSections?: ReadonlySet<string>`. A locked section renders read-only (values and fail chips, no controls)
    with a visible `forms.renderer.section_locked` note; the rest stay editable. Default empty: existing callers are
    unchanged. Export-list test unchanged (a prop, not an export).
  - 4. **Nav and routes.** Nav item `inspections` in section `quality` (ADR 0018), icon `check`, term
    `inspection.register.nav`, permission `inspection.view`. Routes `routes/_app/inspections/index.tsx` and
    `$inspectionId.tsx`, registered in `router.ts`. The e2e stub session (`e2e/web/stub-session.ts`) supplies the
    inspection permissions; the shell's dev stub is not changed here.
  - 5. **Register** `/inspections` (`InspectionsRegister.tsx`, copying the reports register): `RegisterTable`
    (`id="inspections"`) over the generated `useInspectionsList`, newest first, cursor paging, URL state through
    `decodeRegisterQuery` / `encodeRegisterQuery`: `state` and `kind` (quick select filters), `projectId`,
    `assetId` (set by links from an asset; shown as a removable filter chip with the asset label), `cursor`,
    `limit`, `cols`. No free-text search and no sortable columns (the API has neither).
    - Columns: Asset (`assetLabel` linking to `/inspections/<id>`, accessible name includes the template; falls back
      to the id in mono), Template (`templateName` or `templateCode`, then `rev <revisionNo>`), Kind
      (`inspection.kind.<kind>`), Status (`StatusChip` from `states.ts`, label `workflow.inspection.state.<state>`),
      Created (`createdAt` in the viewer's zone, `<time dateTime>`), Created by (`createdByName`, hidden by default).
    - `states.ts` maps every state of `inspection_standard.json` to a tone and icon: `draft`, `assignable`,
      `assigned` neutral/clock; `in_progress`, `in_progress_sitesync`, `inspector_review` info/loader;
      `clarification_required`, `rework_required` warning/warning; `supervisor_review` info/shield; `performed`
      success/check; `retired` neutral/minus. An unknown state shows neutral with the raw code (never a crash).
    - Empty state "No inspections yet." with the create button; error state shows the request id (DESIGN-03).
  - 6. **Create dialog** (`CreateInspectionDialog.tsx`, opened by "New inspection" when the principal has
    `inspection.create`; URL `?new=1` so it can be linked): asset (`Combobox` over `useAssetsList` with `q`),
    template (published templates from `useFormsTemplatesList` with `status=published`; the template's kind sets
    `kind`), optional project. Submit posts `POST /inspections` with a fresh `clientGeneratedId` kept for the dialog's
    life (a double click or retry replays to the same row, 200), then navigates to the new detail page. 422/404 codes
    (`ASSET_NOT_FOUND`, `TEMPLATE_NOT_PUBLISHED`, `NO_INSPECTION_WORKFLOW`) show as the field's error via
    `inspection.error.*`. A principal without `form.view` sees `inspection.create.no_template_access` instead of the
    template picker (no request that would 403).
  - 7. **Detail page** `/inspections/:id` (`InspectionDetail.tsx`) on `RecordDetail`:
    - Title `assetLabel` · `templateName rev N`; breadcrumb `assetPath`; status chip as in the register; kind and
      `createdByName`/`createdAt` in the header.
    - **Workflow bar**: steps = the main path `draft → assigned → in_progress → supervisor_review → performed`
      (`supervisor_review` omitted when `hasSupervisorReview` is false; a state off the path, e.g.
      `rework_required`, is shown as the current label beside the bar). Actions = `availableTransitions` with
      `allowed: true`, label `labelKey`, `retire` and `request_rework` with tone `danger`. Each not-allowed
      transition with a `reasonKey` (e.g. `inspection.guard.submit_not_ready`) shows that text under the bar, so the
      inspector sees why submit is missing.
    - **Taking an action** (`TransitionDialog.tsx`): `requiresComment` → a dialog with a required comment (≤ 2000);
      `critical` → `confirm()` naming the action; then `POST .../transition` with `expectedSyncVersion =
      instanceSyncVersion`. 200 → refetch and a toast; 202 → refetch, an info banner
      `inspection.transition.pending_countersign` while `pendingCountersign` is set; 401 `STEP_UP_REQUIRED` →
      `startStepUp` with the pending action, and on return `takePendingStepUp` replays it once; 409 stale → refetch
      and toast `inspection.error.stale`; 422 `GUARD_FAILED` → its `messageKey`; 403 → `ui.error.forbidden`.
    - Tabs (`?tab=` in the URL, `RecordDetail`): `answers` (default) and `history`; INSPECTIONS-15 adds `itp` and
      `report`. The tab list is an array the page builds, so adding tabs is additive.
    - Another tenant's or a missing id → the page's not-found state (the API's 404), never the error state.
  - 8. **Answers tab** (`AnswersTab.tsx`, `AcknowledgementBar.tsx`): loads `GET .../form`, `GET .../responses` and
    `GET .../acknowledgements` in parallel and renders `FormRenderer` with the schema, the current values, mode
    `draft`, `readOnly` unless `can.respond || can.reviewEdit`, and `lockedSections` = the sections whose
    acknowledgement is `locked` (all of them while the report is ticked).
    - **Saving**: changed fields are queued and saved 1.5 s after the last change and on blur of the form (one
      `POST .../responses` per batch, ≤ 200 answers, each with a new `clientId`; a retry resends the same
      `clientId`s, so a lost response never doubles a row). A "Saving…" / "Saved" / "Not saved" status line with
      `aria-live="polite"`. 422 `errors[]` → `serverErrors` on the renderer, nothing written (the API's rule);
      409 `INSPECTION_NOT_EDITABLE` or `SECTION_LOCKED` → refetch and toast. Leaving the page with unsaved changes
      asks to confirm.
    - **Section ticks**: under each section a checkbox "Section complete" (`can.acknowledge`). Ticking posts
      `.../sections/<key>/acknowledgement`; 422 `SECTION_INCOMPLETE` lists `missingRequired`, `invalid` and
      `ruleFailures` (rule ids through their label) in an error summary that links to the fields. A ticked section
      shows `byName` and the local time; unticking is offered only to the ticker (others see it disabled with
      `inspection.ack.ticked_by`), and 403 `NOT_ACKNOWLEDGER` / 409 `REPORT_ACKNOWLEDGED` show their terms.
    - **Report tick** at the end: "Report complete", enabled when every visible section is ticked; 422
      `SECTIONS_NOT_ACKNOWLEDGED` lists the sections. Once it is ticked the submit action appears in the workflow bar
      (the API's guard; the page does not compute it).
  - 9. **History tab** (`HistoryTab.tsx`): `GET .../history` as a list, newest first: action term, from → to state
    terms, `actorName`, `authStrength`, comment, local time; `chainValid: false` → the same danger banner style.
  - 10. **Terms** (`config/terms/en-AU/inspections.json`, manifest `term_keys`): `inspection.register.*` (nav,
    title, caption, filters, column headers, empty/loading/error/paging), `inspection.create.*`,
    `inspection.detail.*` (tabs, header labels), `inspection.save.*` (saving, saved, not saved, leave confirm),
    `inspection.ack.*`, `inspection.history.*`, `inspection.transition.*`, `inspection.error.stale`,
    `inspection.error.revision_not_found`; and `forms.renderer.section_locked` in `forms.json`. State and action
    labels reuse `workflow.inspection.state.*` and `workflow.inspection.action.*` (approvals.json).
- **acceptance**:
  - A user with `inspection.view` finds inspections on `/inspections` by state, kind, project or asset, sees asset,
    template and names (never only uuids), and the URL reopens the same view.
  - A coordinator creates an inspection from an asset and a published template and lands on its detail page; a
    double submit creates one inspection.
  - An inspector with `inspection.respond` but **without** `form.view` sees and answers the pinned form; answers
    autosave, invalid values show the server's errors and write nothing, and a ticked section cannot be edited.
  - Submit appears only once the sections and report are ticked (and no ITP step is open); the inspector sees why
    when it is not available; a critical action goes through step-up and completes after the round trip.
  - Tenant B gets a 404 on every inspection route and the page shows not-found; no page shows another tenant's data.
- **tests**:
  - **unit** (vitest, the reports register harness and `packages/form-renderer` tests):
    - renderer: a section in `lockedSections` renders values as text with the locked note while another section's
      inputs stay editable; default props unchanged (existing tests green).
    - register: rows show asset label (id fallback), template name and rev, kind and state chips for every state in
      `inspection_standard.json` plus an unknown code; filters write the URL; empty and error states; no nav item
      without `inspection.view`; no create button without `inspection.create`.
    - detail: workflow bar shows only allowed actions, hides `supervisor_review` when `hasSupervisorReview` is
      false, shows a not-allowed transition's reason; a `requiresComment` action needs a comment; a critical action
      confirms first; 401 `STEP_UP_REQUIRED` calls `startStepUp` and a pending action replays once; 202 shows the
      countersign banner; 404 shows not-found.
    - answers: edits are batched after 1.5 s into one POST with unique `clientId`s, a retry resends the same ids;
      422 errors land on the fields; read-only when neither `can.respond` nor `can.reviewEdit`; tick and untick
      requests; `SECTION_INCOMPLETE` lists the missing fields; untick disabled for a non-ticker.
  - **integration** (pytest, real Postgres from Testcontainers, `kaefer-demo` and `tenant-b`, the INSPECTIONS-10
    fixtures):
    - `test_labels_db.py`: list and detail carry `assetLabel = "P-101 Feed pump"`, `templateCode`, `templateName`,
      `revisionNo`, `createdByName`; detail `assetPath` root first; answers carry `respondedByName`, history
      `actorName`, sign-offs `signerName`, acknowledgements `byName`; a soft-deleted asset gives `assetLabel: null`,
      not an error; `can` for an inspector in `in_progress` (`respond` and `acknowledge` true, `manageItp` false), a
      supervisor in `supervisor_review` (`reviewEdit` true) and a viewer (all false); a page of 50 inspections on 3
      assets makes at most 3 asset lookups (counting spy on the published API).
    - `test_form_route_db.py`: a user with `inspection.view` and no `form.view` gets the pinned revision's schema and
      `schemaHash` (equal to the revision's); after a new revision is published the route still returns the pinned
      one; tenant B → 404; a user without `inspection.view` on the project → 403; the IDOR test covers the route.
  - **e2e**:
    - `e2e/web/inspections.spec.ts` (stub session, `page.route` fakes like `reports.spec.ts`): register filters land
      in the URL and a copied URL reopens the view; create dialog posts once and navigates; answering a field
      autosaves one POST; ticking every section and the report reveals submit; `submit_report` answering 401
      `STEP_UP_REQUIRED` navigates to the step-up start URL; the 390 px
      layout scrolls in its own regions; axe on the register, the answers tab (editable and read-only) and the
      transition dialog → 0 serious/critical, on desktop Chromium, mobile Chrome and iPad WebKit.
    - `e2e/web/inspections-live.spec.ts` (`@skeleton`, compose stack): A creates an asset and publishes a two-section
      template through the API (no required photo or signature), creates an inspection from `/inspections`, takes
      `quick_inspect`, answers through the renderer, ticks both sections and the report, takes
      `request_supervisor_review` and sees `supervisor_review` in the workflow bar and the history tab; B opens A's
      `/inspections/<id>` → not-found and `GET /api/v1/inspections/<id>` → 404; axe on the detail page.
