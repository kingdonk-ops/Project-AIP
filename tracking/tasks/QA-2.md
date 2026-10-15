# QA-2 — Flaky ops runner test: whole-table procrastinate_jobs count races the periodic job

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | DATABASE-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. `apps/api/aip/modules/ops/tests/test_runner.py`

## Spec

`test_the_same_succeeded_job_delivered_twice_runs_the_handler_once` asserted the count of the whole
`procrastinate_jobs` table (`[("succeeded", 3)]`). Draining runs the Procrastinate worker, which can
defer the daily periodic `db.ensure_partitions` job (DATABASE-05) into the same `default` queue, so
the whole-table count intermittently sees a 4th `succeeded` row. The test was green locally but
flaked on PR #78's Python 3.12/3.13 CI jobs.

Scope the post-drain count to the test's own jobs (`task_name LIKE 'test.job.%'`, the prefix
`register_job` uses) so the periodic job can no longer perturb it. Only that one assertion runs after
a drain; the other whole-table counts in the file assert before any drain, so they are not exposed.

## Acceptance

- The test counts only its own jobs and passes whether or not the periodic job fires during the drain.
- No test is skipped, disabled or quarantined; no production code changes.
