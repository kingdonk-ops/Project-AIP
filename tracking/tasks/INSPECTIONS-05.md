# INSPECTIONS-05 — Client review step and multi-party sign-off chips

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | APPROVALS-04, INSPECTIONS-03, PORTAL-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Add the client review step (a client signatory role fed by PORTAL-01 grants) and the row of signatory chips showing each signer's assurance level; clients act on it in the portal (PORTAL-04). It registers its client-review transition permission with `aip.modules.portal.api.register_action_permissions("sign_off", ...)` and adds `InspectionsApi.list_awaiting_party(conn, *, party, scopes, limit, after)` (each item with `assetPath`) for the portal inbox (PORTAL-03) (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
