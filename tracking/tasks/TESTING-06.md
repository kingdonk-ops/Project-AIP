# TESTING-06 — Hold-point and completion-gate scenarios on CUI data, plus golden report

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | PLAN-R1, TESTING-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Encode AIP's existing lifecycle as golden scenarios that double as customer acceptance tests.

- **depends on**:
  - TESTING-01
- **files**:
  - backend/tests/scenarios/cui_remediation/scenarios.yaml
  - backend/tests/workflow/test_hold_points.py
  - backend/tests/workflow/test_completion_gate.py
  - backend/tests/golden/test_inspection_report.py
  - backend/tests/golden/inspection_report.expected.pdf.txt
- **steps**:
  - 1. Write the YAML data: a pipe spool asset, an ITP with a hold point, an RSW scope with 3 tasks, and an inspector with an expiring certificate.
  - 2. Test: a hold point not signed blocks the next inspection step.
  - 3. Test: an RSW cannot complete while any task is open or any hold point is unsigned.
  - 4. Test: an inspector with an expired certificate is hard-blocked.
  - 5. Render the report, extract text and compare to the golden file.
  - 6. Add an env flag UPDATE_GOLDEN=1 for deliberate refreshes.
- **acceptance**:
  - All transitions in the current AIP lifecycle are covered, 100% scenario coverage on gate logic.
  - Report drift fails the test with a readable diff.
- **tests**:
  - **e2e**:
    - Playwright: raise an ITP, sign the hold point, approve the inspection; the status chips read the tenant-renamed labels.
  - **integration**:
    - Sign the hold point, then complete tasks, then RSW completion returns 200.
    - Attempt completion with 1 open task returns 409 with code scope_incomplete.
    - Inspector certificate expired yesterday: starting an inspection returns 403 certificate_expired.
    - The golden report text matches the stored file.
  - **unit**:
    - Gate function returns blocked(reason='open_hold_point') when 1 hold point is unsigned.
