# TENANCY-09 — Organisation-level isolation golden tests

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 (re-scoped by PLAN-R1) |
| Size | S |
| Depends on | TENANCY-03, TENANCY-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)

## Spec

Split from TENANCY-03 (2026-10-16): the original "AIP Phase 24 golden cases" (a user in organisation X
must not see organisation Y's assets) could not run because no assets module existed. Once assets
and asset sharing (TENANCY-04) exist, prove organisation-level visibility inside one tenant.

- **steps**:
  - 1. Golden tests: users of two client organisations in one tenant each see only assets shared with their organisation, and only the field groups of their visibility profile.
- **acceptance**:
  - A user in organisation X cannot list, fetch or search organisation Y's unshared assets.
- **tests**:
  - **integration**:
    - User in client org X lists and fetches assets shared only with org Y. Expected: not listed, 404.
