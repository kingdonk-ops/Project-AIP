# ACCESS-05 — Users & Roles UI, permission matrix page and export

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-02, DESIGN-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md) ("Pages")
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`apps/web/src/features/<module>/`, orval client)
4. Only if the step needs it: [`routes.md`](../../docs/blueprint/modules/access/routes.md), [`ui-layout.md`](../../docs/blueprint/modules/access/ui-layout.md), [`docs/blueprint/05-access-matrix.md`](../../docs/blueprint/05-access-matrix.md)

## Spec

Give tenant admins a Users & Roles register, a role editor and a role × module permission matrix with CSV/JSON export as review evidence. Every page hides actions the viewer cannot perform.

- **files**:
  - apps/api/src/modules/access/users-access.controller.ts
  - apps/api/src/modules/access/matrix/matrix.service.ts
  - apps/api/src/modules/access/matrix/matrix.controller.ts
  - apps/web/src/features/access/UsersAndRolesPage.tsx
  - apps/web/src/features/access/UserAccessDrawer.tsx
  - apps/web/src/features/access/AssignRoleDialog.tsx
  - apps/web/src/features/access/RolesPage.tsx
  - apps/web/src/features/access/RoleEditor.tsx
  - apps/web/src/features/access/PermissionMatrixPage.tsx
  - apps/web/src/features/access/useAbilities.ts
  - apps/web/src/app/(app)/settings/users/page.tsx
  - apps/web/src/app/(app)/settings/roles/page.tsx
  - apps/web/src/app/(app)/settings/access/matrix/page.tsx
  - e2e/web/access/users-and-roles.spec.ts
  - apps/api/src/modules/access/tests/matrix/
- **steps**:
  - 1. `GET /api/v1/access/users?q=&status=&roleId=&projectId=&cursor=` requires `identity.user.read` and `access.role_assignment.read`. It returns 50 rows per page with `{userId, displayName, email, userClass, status, mfaEnrolled, scimStatus, lastLoginAt, assignments:[{assignmentId, role:{code,name}, scope, validTo, source}]}`, built from identity's `api.ts` `listUsers` plus assignments, with a next cursor.
  - 2. `GET /api/v1/access/matrix?projectId=` (`access.role.read`) returns `{roles:[{code,name}], modules:[{id,name}], cells:{[roleCode]:{[moduleId]:{level, permissions[]}}}}`. The level is derived back from `role_permission` as the highest level whose permission set is fully covered. `GET /api/v1/access/matrix/export?format=csv|json` (`access.matrix.export`) streams a file named `access-matrix-<tenantSlug>-<YYYYMMDD>.<ext>`. The CSV header is `role,module,level,permissions`. The response carries `X-Content-SHA256`, and the export writes the outbox event `access.matrix.exported` so the audit trail holds the evidence.
  - 3. `/settings/users` uses the DESIGN-03 register table: columns Name, Email, Class, Roles, MFA, SCIM, Last sign-in and Status; filters role, project and status; server pagination; the standard CSV export. A row opens `UserAccessDrawer`, which lists assignments with scope, valid-until and source and a Remove action. `AssignRoleDialog` offers role, scope (Tenant / Project picker) and valid-until. Privileged roles carry a badge. When the API answers `STEP_UP_REQUIRED`, the dialog runs the IDENTITY-04 MFA verification and retries.
  - 4. `/settings/roles` lists system and custom roles. System roles are read-only with a "Clone" action. `RoleEditor` groups permissions by module, marks privileged ones with a lock icon and a text label, and saves with PATCH.
  - 5. `/settings/access/matrix` shows a role × module grid with text-labelled level chips (never colour alone), a project filter, and Export CSV / Export JSON buttons.
  - 6. `useAbilities` reads `/api/v1/access/me/abilities`, so controls the viewer cannot use are not rendered rather than failing with 403. All strings use terminology keys. The three pages must pass axe with no serious or critical violations.
- **acceptance**:
  - A tenant admin can find a user, see why they hold each role, assign or remove tenant or project roles, and edit custom roles, all without leaving the register.
  - The matrix for a freshly seeded tenant matches `05-access-matrix.md` for every module that has catalogue permissions.
  - The export is reproducible (same data gives the same SHA-256) and is recorded for audit.
  - An auditor sees everything read-only with no write controls.
- **tests**:
  - **unit**:
    - `deriveLevel(['read','create'])` returns `create`. `deriveLevel(['read','create','update','delete','approve','sign'])` returns `approve`. `deriveLevel([])` returns `none`. `deriveLevel(['read','approve'])` returns `view` (gap at create).
    - `toCsvField('Client, reviewer')` returns `"Client, reviewer"` with the quotes.
    - React Testing Library: in `AssignRoleDialog`, choosing Project scope without picking a project leaves Save disabled.
  - **integration**:
    - `GET /access/matrix` for a seeded tenant. Expected: 11 roles, and cell inspector × inspections has level `create`, matching the access matrix.
    - Export CSV. Expected: the first line is `role,module,level,permissions`, there are roles × modules data rows, `X-Content-SHA256` equals the SHA-256 of the body, an `access.matrix.exported` outbox row exists, and two exports of unchanged data have equal hashes.
    - As an auditor: `GET /access/users` returns 200 and `POST /access/role-assignments` returns 403.
    - With 51 users, `/access/users` returns 50 rows and a next cursor. `?roleId=<inspector>` returns only users holding inspector.
  - **e2e**:
    - Playwright: the tenant admin opens `/settings/users`, filters by Inspector, opens alice's drawer and assigns Supervisor on P1. Expected: a success toast and the row shows "Supervisor (P1)". On `/settings/access/matrix`, Export CSV downloads a file whose name starts with `access-matrix-kaefer-`. An axe scan of the three pages reports 0 serious or critical violations.
    - An auditor opens `/settings/users`. Expected: the register renders with no "Assign role" button and no Remove actions.
    - The admin assigns `tenant_admin` to alice without a fresh step-up. Expected: the MFA prompt appears, and after TOTP the assignment succeeds.
