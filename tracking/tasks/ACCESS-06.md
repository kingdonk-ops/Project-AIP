# ACCESS-06 — Project permission overrides, operator support-access gate, lockout on user removal

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-02, PROJECTS-03, TENANCY-06 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md)
3. ADRs: 0020 (role management), 0027 (default role expansion)
4. [`ACCESS-02.md`](ACCESS-02.md), section "Amended requirement and guardrails" (the source of this task)

## Spec

Split out of ACCESS-02 (2026-10-13) because each part needs work that did not exist yet: project admins
(PROJECTS-03), support-access grants (TENANCY-06) and the user lifecycle routes (IDENTITY-04/05).

- **steps**:
  - 1. `project_permission_override` (tenant template, FORCE RLS, soft delete): role or user, permission, project,
    granted_by, timestamps. A project owner or project admin (PROJECTS-03) may add overrides for their project only.
    They cannot edit tenant-wide roles, cannot grant a permission they do not hold in that project
    (403 `GRANT_EXCEEDS_GRANTOR`) and can never grant `access.role.*` or `access.role_assignment.*`. The
    `RoleGrantProvider` (or a second provider) turns live overrides into `ProjectScope` grants.
  - 2. Operators (ADR 0017) can change tenant roles only inside an active support-access grant (TENANCY-06);
    otherwise 403 and an audit event.
  - 3. Deactivating or deleting the last user who holds `access.role.manage` at tenant scope returns 409
    `LAST_ROLE_MANAGER` (and the last tenant_admin, 409 `LAST_TENANT_ADMIN`), under the same per-tenant lock
    ACCESS-02 uses (`lock_tenant_roles`). Hook it into identity's status changes and SCIM deprovisioning.
  - 4. Bump the tenant access version and emit an outbox event for every override change (before and after sets).
- **tests**:
  - **integration**:
    - A project admin grants punchlist close for P1: the grantee can close in P1 but not in P2.
    - The same admin grants a permission they lack: 403 `GRANT_EXCEEDS_GRANTOR`; edits `inspector` tenant-wide: 403.
    - An operator without a support-access grant changes a role: 403 and an audit event.
    - Deactivating the only role manager: 409 `LAST_ROLE_MANAGER`.
