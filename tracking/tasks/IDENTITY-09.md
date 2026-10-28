# IDENTITY-09 — Display-name lookup in the identity published interface

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | R1 |
| Size | XS |
| Depends on | PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Add `get_display_names(conn, user_ids) -> dict[UUID, str]` to `aip.modules.identity.api` (tenant members only, RLS-bound, no email or other PII beyond the display name) so reports and registers can print who signed or approved (tag: extend).

### Behaviour

- Signature: `async def get_display_names(conn: AsyncConnection, user_ids: Iterable[UUID]) -> dict[UUID, str]`,
  implemented in `repository.py` and re-exported from `api.py`. `conn` comes from the caller's `with_tenant`.
- One `SELECT id, display_name FROM app_user` filtered on the bound tenant (`app.tenant_id`) and the ids; RLS also
  applies. Duplicate ids are collapsed; an empty input returns `{}` without a query.
- Ids of another tenant, or that do not exist, are left out of the map (the caller decides on a fallback).
- Deactivated and soft-deleted users keep their name: reports and registers print historic signers.
- Only the display name is returned: no email, status or other PII.

### Acceptance and tests (`tests/test_display_names_db.py`, real Postgres as `aip_app`)

- Two tenant-A users map to their names; a repeated id appears once.
- Tenant A cannot see tenant B's user and vice versa; an unknown id is omitted.
- Deactivated and soft-deleted users are still returned.
- Empty input returns an empty map.
