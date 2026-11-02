# ACCESS-09 — Operator default role template: edit the shipped access matrix and push it to tenants

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ACCESS-02, ACCESS-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md)
3. ADRs: 0017, 0020, 0027, 0029, 0032, 0042

## Spec

Let the platform operator view and change the default role levels (module × the 11 tenant roles → none, view,
create, edit, approve, admin) without a code change, with an audit trail, and push them to tenants (owner request,
2026-11-02).

- **files**:
  - apps/api/migrations/versions/202611021000_access_default_role_template.py
  - apps/api/aip/modules/access/tables.py
  - apps/api/aip/modules/access/roles/templates.py
  - apps/api/aip/modules/access/roles/template_routes.py
  - apps/api/aip/modules/access/roles/seed.py, roles/cli.py, api.py, manifest.toml
  - apps/api/aip/modules/ops/manifest.toml (`platform.roles.manage`), ops/api.py (`active_tenant_ids`)
  - apps/api/aip/main.py (mount the router when `platform.roles.manage` is in the catalogue)
  - apps/api/tests/schema/schema_guard_allowlist.yaml
  - apps/api/aip/modules/access/tests/roles/test_default_role_template_db.py
  - docs/adr/0042-operator-default-role-template.md
- **steps**:
  - 1. ADR 0042: where the template lives, audit, guardrails, push to tenants, who may edit, how `MATRIX` and
    `05-access-matrix.md` stay the documented default.
  - 2. Global tables `default_role_level` (moved cells only) and append-only `default_role_level_change`, with CHECKs
    for the role codes, levels, Client Reviewer sign-off-only levels and Tenant Admin `admin` on `access`.
  - 3. `effective_matrix` (shipped `MATRIX` plus moved cells) feeds `seed_default_roles`; customised roles report
    `pending` and `excess` codes of modules whose level changed since they were customised.
  - 4. Operator API under `/api/v1/platform/default-roles` (`platform.roles.manage`): `GET` cells with shipped level,
    `PATCH` changes with a reason (atomic), `GET /history`, `POST /sync` (named or every active tenant).
  - 5. Regenerate the schema snapshot, permission codes, module map and API client.
- **acceptance**:
  - The operator moves a cell; the history records who, when, why, before and after; nothing changes in a tenant
    until a sync, which updates uncustomised system roles and reports customised ones without changing them.
  - Tenant admins and every tenant role get 403 on these routes; no template change can give a role a `platform.*`
    or portal-only code, a Client Reviewer more than sign-off, or take `admin` on `access` from Tenant Admin.
  - A tenant provisioned after a change is seeded from the template.
- **tests**:
  - **unit**:
    - none beyond the existing ADR 0027 expansion tests (the template only feeds levels into it).
  - **integration**:
    - Tenant admin GET/PATCH/sync → 403; operator GET → every `MATRIX` cell at its shipped level, not overridden.
    - PATCH projects/auditor to `edit` → history row with operator, reason, view → edit; sync tenant A → auditor
      holds `project.update` (not `site.manage`), and the `access.role.changed` event names the operator.
    - PATCH back to the shipped level → row deleted, a history row; a no-op writes nothing; a stale row resets.
    - Guardrails (Client Reviewer `edit`/`admin`, Tenant Admin `access` below admin, unknown role, unknown module,
      duplicate cell, blank reason, unknown level) → 422 and nothing written.
    - `ops`/`portal` at `admin` for Project Manager → `ops.jobs.admin` but no `platform.*` / portal-only code.
    - Customised auditor and supervisor → `pending` / `excess` reported, permissions unchanged.
    - Sync with an unknown or suspended tenant → 422 `UNKNOWN_TENANT`; no `tenantIds` → every active tenant.
    - New tenant seeded after a change gets the template's codes.
    - `aip_app` cannot UPDATE or DELETE the history; CHECKs refuse bad rows.
  - **e2e**:
    - none (no page; the operator console page is ACCESS-10).
