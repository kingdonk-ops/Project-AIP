# TESTING-10 — Worker shutdown test waits for registration instead of a fixed sleep

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | OPS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. `apps/api/aip/modules/ops/tests/test_worker.py`

## Spec

`test_a_sigterm_stops_an_idle_worker_gracefully` slept a fixed 4 seconds and then expected the
worker to be registered. On a slower developer laptop, importing `aip.worker` alone takes about
3 seconds, so the test failed locally while CI stayed green. Wait for the registration instead.

- **files**:
  - apps/api/aip/modules/ops/tests/test_worker.py
- **steps**:
  - 1. Replace `time.sleep(4)` with a loop that polls `procrastinate_workers` every 0.25 s until one worker is registered, failing fast if the process exits and failing after a 60 s deadline.
- **acceptance**:
  - The test passes on a slow machine and on CI; it still fails if the worker exits early, never registers, or does not stop gracefully on SIGTERM.
- **tests**:
  - **unit**:
    - none (test-only change)
  - **integration**:
    - `pytest apps/api/aip/modules/ops/tests/test_worker.py` passes repeatedly on the slow laptop where the fixed sleep failed every time.
  - **e2e**:
    - none
