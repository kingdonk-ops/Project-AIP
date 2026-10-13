# TESTING-11 — JIT membership test uses the database date, not the local date

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | IDENTITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. `apps/api/aip/modules/identity/tests/test_jit_db.py`

## Spec

`test_user_without_a_current_membership_is_refused` built an expired membership with
`date.today()` (the local date), while the product checks validity against Postgres
`current_date` (UTC in the test containers). In Perth, between midnight and 08:00 local time the
local date is a day ahead of UTC, so "expired yesterday" was still valid in the database and the
test failed. CI runs in UTC and never saw it.

- **files**:
  - apps/api/aip/modules/identity/tests/test_jit_db.py
- **steps**:
  - 1. Read `SELECT current_date` on the test connection and build `valid_from`/`valid_to` from it.
- **acceptance**:
  - The test passes at any local time of day on any machine timezone, and on CI.
- **tests**:
  - **unit**:
    - none (test-only change)
  - **integration**:
    - `pytest apps/api/aip/modules/identity/tests/test_jit_db.py` passes at 07:26 AWST, inside the window where it failed before.
  - **e2e**:
    - none
