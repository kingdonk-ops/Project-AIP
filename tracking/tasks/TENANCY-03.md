# TENANCY-03 — Organisations and project-scoped role assignment
<!-- hand-edited: converted to Python backend per ADR 0001 and narrowed to the API (2026-10-16); the page and invite e2e moved to TENANCY-08, org-isolation golden tests to TENANCY-09 -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | PROJECTS-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0020](../../docs/adr/0020-role-management-and-guardrails.md)
4. Only if the step needs it: `data-model.md` (organisations) and `routes.md` (`/settings/organisations`)

## Why this was narrowed

The original spec (NestJS paths) asked to replace the old AIP "Phase 24" application-level org joins
and delete those helpers. This repo is greenfield: those helpers never existed here, and there is no
assets module yet, so the golden "org X must not see org Y's assets" cases cannot run. Project-scoped
role assignment (`role_assignment.scope_type`/`project_id`) was already built by ACCESS-02; this task
proves it with the spec's tests and adds a `has_role` helper. The `/settings/organisations` page and
the "create a subcontractor and invite a user" e2e need IDENTITY-04 and move to TENANCY-08.

## Spec

Model owner, client and subcontractor organisations inside a tenant, and prove that a project-scoped
role grants nothing outside its project.

- **files**:
  - apps/api/migrations/versions/202610161200_tenancy_organisations.py
  - apps/api/aip/modules/tenancy/tables.py
  - apps/api/aip/modules/tenancy/organisations/ (repository, service, routes, schemas)
  - apps/api/aip/modules/tenancy/manifest.toml
  - apps/api/aip/modules/access/api.py (`has_role`)
  - apps/api/aip/modules/access/roles/repository.py
  - apps/api/aip/modules/tenancy/seed.py
  - apps/api/aip/modules/tenancy/tests/organisations/
- **steps**:
  - 1. Migration `202610161200_tenancy_organisations`: `organisations` (id, tenant_id, name, org_type owner|client|subcontractor, registration_number, status active|inactive, sync_version, timestamps, soft delete), FORCE RLS on tenant_id, unique `(tenant_id, lower(name)) WHERE deleted_at IS NULL`, btree `(tenant_id, org_type)`, no DELETE for `aip_app`. FORCE RLS hides `tenants` from the migration role, so the owner organisation of each fixture tenant comes from the tenancy seed, and of a real tenant from provisioning (TENANCY-05).
  - 2. `GET/POST /api/v1/settings/organisations` (filters `type`, `status`), `GET/PATCH /api/v1/settings/organisations/{id}`; deactivate is a PATCH of `status` with `syncVersion`. `tenancy.organisation.read` and `tenancy.organisation.manage` in the manifest; the access matrix gives tenant_admin both and project_manager and auditor read (ADR 0027). Duplicate name → 409 `ORGANISATION_NAME_TAKEN`; unknown type → 422; another tenant's id → 404; stale version → 409. Emit `tenancy.organisation_created` / `_updated` v1 through the outbox.
  - 3. `has_role(user_id, role_code, project_id)` on the access module API: true for a tenant-scoped assignment or a project assignment on that project, false otherwise.
- **acceptance**:
  - A project-scoped role grants nothing in other projects.
  - Duplicate organisation names within a tenant are rejected.
  - Organisations are invisible across tenants.
- **tests**:
  - **integration**:
    - Create Rio Tinto as type client in Kaefer's tenant. GET /settings/organisations. Expected: it is listed with type 'client'.
    - Assign a project-scoped role on P1 and GET P2. Expected: 403 (already covered by ACCESS-02: `test_a_project_role_grants_only_in_its_project`).
    - Tenant B lists organisations and fetches tenant A's organisation id. Expected: none listed, 404.
    - Creating a second "rio tinto" in the same tenant. Expected: 409.
  - **unit**:
    - has_role(user, 'inspector', P1) is true with a P1 assignment and false for P2.
    - Organisation type 'other' fails validation.
