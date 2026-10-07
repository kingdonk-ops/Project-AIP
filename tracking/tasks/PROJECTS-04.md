# PROJECTS-04 — Work-type classification + project settings overrides

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`projects`](../../docs/blueprint/modules/projects/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | PROJECTS-01, TERMS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/projects/README.md`](../../docs/blueprint/modules/projects/README.md)
3. ADRs: 0002 (migrations, RLS), 0004 (layout), 0007 (requirement bundles feed R1)
4. Only if the step needs it: the `work_type_classifications` and `project_settings` tables in [`data-model.md`](../../docs/blueprint/modules/projects/data-model.md)

## Spec

Let a tenant define its own work types (each with a stable key and a requirement bundle) and classify projects with them. Store only the per-project overrides of tenant defaults, and expose one resolved-settings read.

- **files**:
  - db/migrations/<timestamp>_work_types_project_settings.sql
  - apps/api/src/modules/projects/classification.service.ts
  - apps/api/src/modules/projects/classification.controller.ts
  - apps/api/src/modules/projects/settings.service.ts
  - apps/api/src/modules/projects/settings.controller.ts
  - apps/api/src/modules/projects/schemas.ts
  - apps/api/src/modules/projects/events.ts
  - apps/api/src/modules/projects/api.ts
  - apps/api/src/modules/projects/tests/
- **steps**:
  - 1. Write one migration from the tenant-table template with two tables. `work_type_classifications` has id, tenant_id, key (`^[a-z][a-z0-9_]{1,40}$`, unique per tenant among live rows), requirement_bundle jsonb, version int, is_active, created_at, updated_at and deleted_at. `project_settings` has id, tenant_id, project_id (unique FK), region, timezone, currency, units, calendar jsonb, enabled_modules text[] and retention_overrides jsonb (every column nullable, where null means inherit), created_at and updated_at. Add the FK `projects.classification_id → work_type_classifications.id`. Both tables get FORCE RLS.
  - 2. Validate the requirement bundle with Zod: `{approvals: string[], itpTemplateKeys: string[], documentTypeKeys: string[], workflowKeys: string[]}`. The values are stable keys, because the referenced modules arrive in R1. Unknown properties are rejected.
  - 3. The label of a work type is the term key `projects.work_type.<key>`, resolved through TERMS-02's published `resolve`/`bulkResolve`. Never store label text in this table. On create, require that an en-AU default for the key exists or is supplied, and write it through the terms module's published API (not its tables).
  - 4. Classification endpoints: GET/POST `/api/v1/projects/work-types` and PATCH `/api/v1/projects/work-types/:id` (a bundle edit bumps version), all guarded by `project.work_types.manage` (tenant admin). Add a seed function that inserts the starter set (remediation, shutdown, cui_campaign, new_build, repair, maintenance) for a new tenant, and is idempotent.
  - 5. Add PUT `/api/v1/projects/:id/classification` with `{classificationId}`, guarded by `project.update`. Add GET `/api/v1/projects/:id/classification/preview?classificationId=`, which returns the added and removed bundle items compared with the current classification and changes nothing. On change, emit `project.classification_changed` with `{projectId, from, to, fromVersion, toVersion}`, which R1 modules use to recalculate requirements.
  - 6. In settings.service.ts, `resolveProjectSettings(projectId)` merges platform defaults (manifest `settings[]`), tenant defaults (from the tenancy module's published API, or from the project's region preset if none is exposed yet) and the project overrides. Each value carries a `source` of `platform|tenant|project`. Add GET `/api/v1/projects/:id/settings` (resolved, `project.view`), PATCH (overrides only, `project.settings.edit`) and DELETE `/api/v1/projects/:id/settings/:field` to reset a field to inherit. Emit `project.settings_changed`.
  - 7. Terminology overrides are out of scope here; they stay with TERMS-02's project level. Retention overrides are stored but not enforced: AUDIT-05 checks them against legal hold.
  - 8. Export `ProjectsApi.getResolvedSettings` and `ProjectsApi.getRequirementBundle(projectId)` from api.ts. Regenerate the API client.
- **acceptance**:
  - Two tenants can each define a `shutdown` work type with different bundles, and neither sees the other's.
  - Resolved settings report the correct source for every field. Resetting a field falls back to the tenant value.
  - Changing a project's classification emits exactly one `project.classification_changed` event, and the preview has no side effects.
  - No label text is stored in projects tables. Labels come from terms.
- **tests**:
  - **unit**:
    - The bundle schema rejects `{approvals:['x'], extra:1}` with an issue at `['extra']`.
    - The merge takes platform `{currency:'AUD'}`, tenant `{currency:'NZD'}` and project `{}` and returns `{currency:{value:'NZD', source:'tenant'}}`. A project override of `'GBP'` returns `source:'project'`.
    - The preview diff between `{approvals:['client_review']}` and `{approvals:['client_review','third_party']}` returns `added:{approvals:['third_party']}, removed:{}`.
  - **integration** (Testcontainers):
    - Seed starter work types twice for tenant A. Expected: 6 rows, not 12.
    - Tenant B lists work types after tenant A created `shutdown`. Expected: tenant B sees only its own rows.
    - PATCH settings `{currency:'USD'}` as a user without `project.settings.edit`. Expected: 403. As a project manager. Expected: 200, and GET shows `currency.source = 'project'`.
    - DELETE `/settings/currency`. Expected: GET shows the tenant value with `source:'tenant'`.
    - PUT classification remediation→shutdown. Expected: one outbox row `project.classification_changed` with fromVersion and toVersion set.
    - A project-level term override in TERMS-02 for `projects.work_type.shutdown` = "Turnaround". Expected: GET work-types with that project in context returns label "Turnaround", and other projects still get "Shutdown".
  - **e2e**:
    - Through the API as the kaefer-demo admin: create work type `cui_campaign` with label "CUI campaign", classify project L592, then preview a switch to `shutdown`. Expected: the preview lists the bundle differences and the project's classification is unchanged until the PUT.
