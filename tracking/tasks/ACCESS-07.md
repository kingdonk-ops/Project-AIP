# ACCESS-07 — Add the `move` verb to the edit level of the default role expansion (ADR 0027 amendment)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: stub fleshed out from ADR 0027, ADR 0036 §10 and PORTAL-01 when the task was built (2026-10-28) -->

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

Add `move` to the `edit` level, and `invite` to the level project admins hold so they can invite portal clients (owner 2026-10-18), in the ADR 0027 verb expansion (amend ADR 0027), so default roles that edit assets can also move them while `asset.move` stays a separate code an admin can withhold; re-seed default roles with `aip-access seed-roles` (tag: extend).

### Behaviour

- `LEVEL_VERBS` in `apps/api/aip/modules/access/roles/default_roles.py`: `edit` adds `move`; `approve` adds `invite`.
- With the access matrix as it stands: `asset.move` goes to Tenant Admin, Project Manager, QA/QC Manager and
  Supervisor (the roles at `edit` or above on `assets`), not to Inspector (`create`) or view-only roles.
  `portal.user.invite` (PORTAL-01) goes to Tenant Admin and Project Manager (`approve` on `portal`), not to the
  `edit` roles.
- Client Reviewer stays sign-off only (ADR 0027 §4): at `approve` it gets the `view` verbs plus `approve` and
  `sign` (`SIGN_OFF_VERBS`), never `invite`.
- No schema change. `aip-access seed-roles` extends uncustomised system roles in place; customised roles report the
  new codes as pending (existing ADR 0020 behaviour).
- ADR 0027 gets an amendment section; its index line notes it.

- **files**:
  - apps/api/aip/modules/access/roles/default_roles.py
  - apps/api/aip/modules/access/tests/roles/test_default_roles.py
  - apps/api/aip/modules/access/tests/roles/test_roles_db.py
  - docs/adr/0027-default-role-permission-expansion.md
  - docs/adr/README.md
- **acceptance**:
  - The default roles that edit assets hold `asset.move`; Inspector and view-only roles do not.
  - Project Manager gets `portal.user.invite`; QA/QC Manager and Client Reviewer do not.
  - Re-seeding a tenant whose Supervisor role predates this change adds `asset.move` to it.
- **tests**:
  - **unit** (`test_default_roles.py`):
    - `expand_level("edit", ...)` includes `move` and not `invite`; `approve` includes both.
    - Assets catalogue: edit roles get `asset.move`; Inspector gets view and create only.
    - Portal catalogue: Project Manager gets view and invite; edit roles get view only.
    - Client Reviewer at `approve` gets view, approve and sign codes, not invite.
  - **integration** (`test_roles_db.py`, real Postgres):
    - Seeded system roles hold `asset.move` exactly at edit level or above.
    - A Supervisor role without `asset.move` is extended by the next seed and the policy service then allows
      `asset.move` for a user holding it.
