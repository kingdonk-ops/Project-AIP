# INSPECTIONS-15 — ITP steps and sign-off chips, and the report tab, on the inspection page

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- split from INSPECTIONS-04 on 2026-11-04 (task linter: size at most M) -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-04, REPORTS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [INSPECTIONS-04](INSPECTIONS-04.md) (the page, labels, `can`, step-up and transition handling to reuse),
   [INSPECTIONS-03](INSPECTIONS-03.md) (ITP steps, actions, sign-offs, countersign), [REPORTS-04](REPORTS-04.md)
   (render list, status chips, download link)
3. ADRs: [0010](../../docs/adr/0010-signoff-assurance.md) (sign-off assurance, countersign),
   [0025](../../docs/adr/0025-time-and-timezones.md), [0035](../../docs/adr/0035-transition-service-implementation.md) §3–5
4. Code: `apps/web/src/features/inspections/` (as INSPECTIONS-04 built it), `apps/api/aip/modules/inspections/{itp,schemas}.py`

## Spec

Add the `itp` and `report` tabs to the inspection detail page: an ITP steps editor, the steps with their hold,
witness, review and surveillance points and the actions the caller may take, the sign-off chips with signer and
assurance, and the inspection's generated reports with authorised download (tag: extend; AIP ITP/RFI template kinds,
PRD "multi-party sign-off: row of signatory chips showing auth strength").

Web only: the API (INSPECTIONS-03, plus `signerName` and `can.manageItp` from INSPECTIONS-04) already does the work.

**Out of scope:** the ITP progress page `/itps/:id`; the booking button on witness steps (INSPECTIONS-12); client
sign-off chips (INSPECTIONS-05); NCR holds raised from the page (ISSUES).

- **files**:
  - apps/web/src/features/inspections/{ItpTab.tsx,ItpStepsEditor.tsx,SignDialog.tsx,SignoffChips.tsx,ReportTab.tsx,InspectionDetail.tsx,inspections.css}
  - apps/web/src/features/inspections/__tests__/{itp,report}.test.tsx
  - config/terms/en-AU/inspections.json
  - e2e/web/inspections.spec.ts, e2e/web/inspections-live.spec.ts
- **steps**:
  - 1. **Tabs.** `itp` (only kind `itp`) and `report` (only with `report.view`) join the detail page's tab list.
  - 2. **Steps editor** (`ItpStepsEditor.tsx`): no steps and `can.manageItp` → rows of title, point type (`hold`,
    `witness`, `review`, `surveillance`), acceptance criteria, notice hours; add, remove, move up/down; seq is the row
    order × 10. Save → `POST .../itp-steps`; 409 `ITP_LOCKED` / `DUPLICATE_SEQ` and 422 show their terms. No steps
    and no `manageItp` → `inspection.itp.no_steps`.
  - 3. **Steps** (`ItpTab.tsx`, from `GET .../itp-steps`) as an ordered list (`<ol>`): seq, title, point-type badge
    (`inspection.itp.point.<type>`), status chip (`pending` neutral/clock, `ready` info/clock, `in_progress`
    info/loader, `released` success/check, `waived` warning/minus, `rejected` danger/alert), a "Held" danger badge
    when `held`, acceptance criteria and notice hours.
  - 4. **Actions** from the step's `availableActions` only: `ready`, `start`, `reopen` → `POST /itp-steps/<id>/actions`;
    `approve`, `reject`, `witnessed`, `waived` → `SignDialog` (signatory role `inspector`, `supervisor` or
    `third_party`; comment, required for `reject` and `waived`) → `POST /itp-steps/<id>/signoffs` with
    `expectedSyncVersion`. 202 → the step shows `pendingCountersign` as a pending chip; 401 `STEP_UP_REQUIRED` →
    step-up and one replay, as INSPECTIONS-04's transitions do (reuse that code); 409 stale → refetch and toast.
  - 5. **Sign-off chips** (`SignoffChips.tsx`, from `GET .../signoffs`) per step, plus an inspection-level row for
    sign-offs without a step: `signerName`, role term, decision term, assurance (`inspection.signoff.assurance.<level>`,
    `assuranceMethod` in the chip's accessible description), local time; a `pending_countersign` entry is a warning
    chip "Awaiting countersign". `chainValid: false` → a danger banner `inspection.signoff.chain_broken` naming
    `brokenAtSeq`.
  - 6. **Report tab** (`ReportTab.tsx`): `useReportsRendersList({recordType: "inspection", recordId})`; each job shows
    its variant, the REPORTS-04 status chip and, when `succeeded`, the same-origin link
    `/api/v1/reports/renders/<id>/file` named for its variant. None → `inspection.report.none`.
  - 7. Terms: `inspection.itp.*` (point types, step statuses, actions, decisions, roles, editor, no steps),
    `inspection.signoff.*`, `inspection.report.*`.
- **acceptance**:
  - On an ITP, a manager sets up steps once; a hold blocks later steps; releasing a hold shows a sign-off chip with
    the signer's name and assurance; a countersign-pending decision shows as pending; a step-up round trip completes
    the release.
  - After `performed`, the report tab offers the internal and client PDFs to a user with `report.view`.
- **tests**:
  - **unit**: editor builds `seq` from row order; actions only from `availableActions`; reject and waive need a
    comment; 202 shows the pending chip; 401 starts step-up; chips show name, role, decision, assurance; chain-broken
    banner; report tab lists jobs with download only on succeeded ones; tabs hidden for a non-ITP or without
    `report.view`.
  - **integration**: none (web only; the API is covered by INSPECTIONS-03 and INSPECTIONS-04).
  - **e2e**:
    - `inspections.spec.ts` (stub session, `page.route`): set up steps, start and release a hold → chip appears; a
      release answering 401 `STEP_UP_REQUIRED` navigates to the step-up start URL; report tab download href; axe on
      the ITP tab and the sign dialog → 0 serious/critical on desktop Chromium, mobile Chrome and iPad WebKit.
    - `inspections-live.spec.ts` (`@skeleton`): A sets up a two-step ITP (hold, then surveillance), readies and starts
      the hold; B opening the ITP tab URL gets not-found.
