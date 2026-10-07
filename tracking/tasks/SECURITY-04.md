# SECURITY-04 — Breach register with NDB clock

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | PLAN-R1, SECURITY-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Track breach incidents with the 30-day assessment deadline and notification state.

- **depends on**:
  - SECURITY-02
- **files**:
  - backend/app/modules/security/breach.py
  - backend/tests/security/test_breach.py
- **steps**:
  - 1. Add fields: aware_at, assessment_due (= aware_at + 30 days), likely_serious_harm (nullable), notified_at, status.
  - 2. Implement log_incident, record_assessment, mark_notified and close with a state-machine guard.
  - 3. Compute the clock state: ok, due_soon (7 days or fewer), overdue.
  - 4. Add a daily job that emits the 'deadline approaching' notification.
  - 5. Add endpoints under /security/breaches.
  - 6. Write the audit_log entry for every transition.
- **acceptance**:
  - Cannot close with no assessment.
  - Overdue incidents are flagged.
  - Every transition is audited.
- **tests**:
  - **e2e**:
    - Privacy officer logs an incident and sees the countdown on the detail page.
  - **integration**:
    - Close without an assessment returns 409.
    - Mark notified with likely_serious_harm=false returns 422 (not required).
    - The daily job on an incident 5 days from due creates one notification, and re-running creates no duplicate.
  - **unit**:
    - aware_at 2025-01-01 gives assessment_due 2025-01-31.
    - Clock at 2025-01-26 returns due_soon; at 2025-02-02 returns overdue.
