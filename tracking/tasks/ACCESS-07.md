# ACCESS-07 — Add the `move` verb to the edit level of the default role expansion (ADR 0027 amendment)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | R1 |
| Size | XS |
| Depends on | PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Add `move` to the `edit` level in the ADR 0027 verb expansion (amend ADR 0027), so default roles that edit assets can also move them while `asset.move` stays a separate code an admin can withhold; re-seed default roles with `aip-access seed-roles` (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
