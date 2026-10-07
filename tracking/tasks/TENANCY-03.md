# TENANCY-03 — Organisations and project-scoped role assignment

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-03, TENANCY-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Model owner, client and subcontractor organisations and activate user_roles.project_id.

- **depends on**:
  - DATABASE-03
  - TENANCY-01
- **files**:
  - migrations/versions/0140_org_types_project_roles.sql
  - apps/api/src/modules/tenancy/organisations.controller.ts
  - apps/api/src/modules/tenancy/organisations.service.ts
  - apps/api/src/modules/tenancy/membership.service.ts
- **steps**:
  - 1. Add organisations.type (owner|client|subcontractor), registration_number and status, defaulting existing rows to owner.
  - 2. Add CRUD endpoints with permission checks and a unique name per tenant.
  - 3. Enforce user_roles.project_id: a role assigned with a project applies only inside that project.
  - 4. Replace the Phase 24 application-level org joins with RLS-backed queries and delete the old join helpers once the tests pass.
  - 5. Add golden tests copied from existing AIP org-isolation behaviour.
- **acceptance**:
  - A project-scoped role grants nothing in other projects.
  - Existing org isolation behaviour is unchanged, with the old helpers removed.
  - Duplicate organisation names within a tenant are rejected.
- **tests**:
  - **e2e**:
    - As tenant admin, create a subcontractor organisation and invite a user. Expected: the organisation shows in the list and the invite email is queued.
  - **integration**:
    - Create Rio Tinto as type client in Kaefer's tenant. GET /settings/organisations. Expected: it is listed with type 'client'.
    - Assign inspector on P1 and GET P2 inspections. Expected: 403.
    - Run the AIP Phase 24 golden cases (user in org X must not see org Y's assets). Expected: all pass with the helpers deleted.
  - **unit**:
    - hasRole(user, 'inspector', projectP1) is true with a P1 assignment and false for P2.
    - Organisation type 'other' fails validation.
