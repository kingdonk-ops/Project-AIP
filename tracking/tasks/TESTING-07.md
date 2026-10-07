# TESTING-07 — Offline sync convergence property tests

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

Hypothesis tests show that random interleavings of edits, retries and conflicts converge.

- **depends on**:
  - TESTING-01
- **files**:
  - backend/tests/sync/test_convergence_property.py
  - backend/tests/sync/sync_model.py
- **steps**:
  - 1. Build a pure in-memory model of the cursor-pull and idempotent-push protocol that uses sync_version.
  - 2. Define Hypothesis strategies for operations: edit(device, record, value), push, pull, retry_push, go_offline, go_online.
  - 3. Run random sequences across 2-4 devices.
  - 4. After a final full sync, assert all devices and the server hold identical state.
  - 5. Assert a retried push with the same idempotency key applies only once.
  - 6. Pin discovered failures with @example.
- **acceptance**:
  - 500 generated examples pass in CI.
  - Duplicate pushes are never double-applied.
- **tests**:
  - **e2e**:
    - Playwright with the network offline: capture an inspection, reconnect, and the server shows it once.
  - **integration**:
    - Two devices edit the same record offline; after sync both show the server-resolved value and the loser's edit is logged as a conflict.
  - **unit**:
    - Push the same idempotency key twice: version increments by 1.
