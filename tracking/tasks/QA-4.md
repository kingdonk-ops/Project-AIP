# QA-4 — Coolify demo: project create is a 500 (bootstrapped admins have no scope row)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | ACCESS-03, TESTING-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. `apps/api/migrations/versions/202610191000_access_scope_rls.py`
3. `apps/api/aip/modules/access/roles/service.py` (`bootstrap_tenant_admin`)

## Spec

After each deploy the walking skeleton runs against the Coolify demo. Since it first reached the
demo (2026-11-01) it fails at "tenant A's admin can create a project": `POST /api/v1/projects`
answers 500. CI's fresh compose stack passes the same journey.

The demo database dates from 2026-10-13. The `admin-bootstrap` one-shot (TESTING-09) assigned
alice and bob `tenant_admin` then, before ACCESS-03 (2026-10-19) added `access_user_scope` and the
restrictive `project_scope` RLS policy on `projects`. That revision's backfill copies nothing under
RLS (its own comment says so), and on every later deploy the bootstrap finds the role "already
held" and writes nothing, so the trigger never runs. The admins pass the policy check for
`project.create`, but the insert fails the RLS `WITH CHECK`, which the API turns into a 500.

`bootstrap_tenant_admin` now touches every live tenant/project assignment in the tenant that has
no scope row, which fires `trg_access_user_scope_sync` and writes it. Dev and demo only (the
bootstrap refuses other `AIP_ENV`s); grants are unchanged, so no grants event.

## Acceptance

- Re-running the bootstrap after a scope row was lost restores it and does not assign twice
  (`test_bootstrap_restores_a_missing_scope_row`).
- After the next deploy the walking skeleton passes against the demo.
- No test is skipped, disabled or quarantined.
