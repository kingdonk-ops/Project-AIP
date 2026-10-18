# APPROVALS-07 — Workflow transition API journeys on the compose stack (carried forward from APPROVALS-02)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | APPROVALS-02, TESTING-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0035](../../docs/adr/0035-transition-service-implementation.md) (why these journeys were
   carried forward), [0034](../../docs/adr/0034-invites-and-step-up-implementation.md)
4. `tracking/tasks/APPROVALS-02.md`, the two **e2e** blocks

## Spec

Run APPROVALS-02's two Playwright API journeys against a whole deployment (the compose stack in CI
lane `e2e-skeleton`, the Coolify demo after a deploy). APPROVALS-02 proved the same HTTP flows
in-process. They could not run deployed yet, because no record type exists whose workflow,
permissions and fixture users a stack can seed (ADR 0035 §9).

- **files**:
  - a dev/test-only seed (refuses `AIP_ENV=production`) that publishes a `demo` workflow in
    `kaefer-demo` with real catalogue permissions, or that uses APPROVALS-05's inspection preset
    if it has landed, and grants them to the submitter fixture user
  - a dev/test-only guard facts provider for that record type, with a fixture switch for
    `allPhotosClean`
  - `e2e/web/approvals-transition.spec.ts`
- **steps**:
  - 1. Add the seed and run it in the compose stack's fixture step.
  - 2. Add the journeys to the skeleton projects (`@skeleton`; `@staging` too if the demo can
       run the seed).
- **acceptance**:
  - Both journeys are green in CI lane `e2e-skeleton`.
- **tests**:
  - **e2e**:
    - Sign in as the `kaefer-demo` submitter. `POST /api/v1/approvals/instances`, transition
      `submit`, then `GET /history`: 1 entry, a 64-hex `entryHash`, and `chainValid: true`. The
      same GET as a `tenant-b` user → 404.
    - The guarded flow: `approve` is refused with 422 `GUARD_FAILED`. After the fixture flips
      `allPhotosClean`, `approve` (with a fresh aal 2 sign-in, or after a step-up) → 200, and
      `GET /history` shows `chainValid: true`.
