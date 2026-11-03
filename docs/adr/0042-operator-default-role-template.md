# ADR 0042: The operator edits the default role template in a platform table that overrides the shipped matrix

- **Status:** accepted (owner, 2026-11-03)
- **Date:** 2026-11-02
- **Affects:** access (ACCESS-09, ACCESS-10; ACCESS-02 seeding), ops (`platform` permission namespace), tenancy
  (TENANCY-05 provisioning); amends ADR 0020 point 3 (see "Owner acceptance" below) and the AGENTS.md table hard
  rule for these two global tables; amends nothing in ADR 0027

## Context

The 11 default tenant roles are seeded from `MATRIX` in `apps/api/aip/modules/access/roles/default_roles.py`, the
code form of `docs/blueprint/05-access-matrix.md`. ADR 0027 (with its amendments) expands each level into permission
codes by verb. Tenant admins can already edit, clone, create and reset roles in their own tenant (ACCESS-02, ADR
0020). The platform operator cannot change the defaults for every tenant without a code change, a release and
`aip-access seed-roles`. The owner asked for an operator-level editor for these default role templates.

## Decision

1. **Where the template lives.** A global table `default_role_level (module_id, role_code, level)` holds only the
   cells the operator moved away from `MATRIX`. No row means the shipped level; setting a cell back to its shipped
   level deletes its row. `templates.effective_matrix` is `MATRIX` with those rows applied, and
   `seed_default_roles` expands it, so provisioning (TENANCY-05), `aip-access seed-roles` and the role "Reset to
   default" (ADR 0020 point 1) all use the operator's template. The code stays the fallback: with an empty table
   nothing changes. The table holds no tenant data, so it is global (no `tenant_id`, no RLS), like `permission` and
   `platform_event_status`, and is on the schema-guard allow-list. ADR 0028's nil-UUID platform tenant does not
   fit: its rows are written only at deploy time by `aip_owner`, and these change at runtime.
2. **The template stores levels, never codes.** ADR 0027 still turns levels into codes, so its guards hold without
   new code: `platform.*` and portal-only codes are never granted (`never_role_held`), an unknown verb needs `admin`,
   and a Client Reviewer `approve` is view plus sign-off only.
3. **Guardrails on the template** (422, refused whole; repeated as table CHECKs):
   - only the 11 system role codes (`UNKNOWN_ROLE`) and a module the matrix or the catalogue knows (`UNKNOWN_MODULE`);
   - Client Reviewer stays sign-off only: `none`, `view` or `approve` (`SIGN_OFF_ONLY_ROLE`); `create`, `edit` and
     `admin` would add edit verbs;
   - Tenant Admin keeps `admin` on `access` (`TENANT_ADMIN_LOCKOUT`), so a new tenant always has someone who can
     manage roles (ADR 0020 "no lockout");
   - each cell once per request (`DUPLICATE_CELL`), and every change carries a `reason`.
4. **Audit, and one write path.** `aip_app` may only SELECT both tables. The only way to change the template is
   the `SECURITY DEFINER` function `access_set_default_role_level(module, role, level, shipped, actor, reason)`
   (owned by `aip_owner`, fixed `search_path`, `EXECUTE` to `aip_app` only, like `access_sync_permissions` for
   the catalogue). In one call it moves the cell (the shipped level deletes the row) and appends a row to
   `default_role_level_change` (cell, level before and after, operator id, reason, time). So a bug or an
   injection anywhere in the app cannot change every tenant's defaults without a history row, and cannot edit or
   forge history. The table CHECKs still apply inside the function. The database cannot tell an operator from
   any other `aip_app` caller: the `platform.roles.manage` check stays in the API, and the caller passes the
   shipped level because `MATRIX` lives in code. No domain event is emitted for the template itself: it is
   platform data, and `domain_events` rows belong to a tenant. A push does emit, in each tenant, the usual
   `access.role.changed` (`action: seeded`) with the operator as actor, and `access.grants_changed`.
5. **How changes reach tenants.** Nothing changes in a tenant until the template is pushed:
   `POST /api/v1/platform/default-roles/sync` runs `seed_default_roles` in each named active tenant (every active
   tenant from `ops_active_tenant_ids()`, ADR 0032, when none is named), each in its own `with_tenant` transaction
   with the request context re-bound to that tenant, as ENT-01's operator API does. `aip-access seed-roles` does
   the same from the command line. Uncustomised system roles take the template. A customised role is never
   changed (ADR 0020 point 1): codes of a module whose level for that role changed after the role was customised
   are reported, those the new level adds as `pending` and those it removes as `excess`, beside the existing report
   of catalogue codes added since. New tenants are seeded from the template at provisioning.
6. **Who may edit.** The privileged code `platform.roles.manage`, declared by `ops` in the `platform` namespace
   (ADR 0029), operator-only: no tenant role may hold it. The routes belong to access
   (`roles/template_routes.py`, reaching ops only through `ops.api.active_tenant_ids`) and `aip.main` mounts them
   only when ops has put the code in the catalogue, like the event catalogue. Until the operator realm (OPS-12)
   issues operator principals nobody holds the code, so the routes answer 403 to everyone. This is not standing
   access to tenant data (ADR 0017 point 5, ADR 0020 point 3): the template is platform data, and a push only does
   what provisioning already does (set the tenant's defaults); it never touches custom or customised roles or
   assignments. Changing a particular tenant's roles still needs the time-boxed, audited support-access grant
   (TENANCY-06).
7. **Keeping the code and the document in step.** `MATRIX` and `05-access-matrix.md` remain the documented, shipped
   default and change only together in a PR (as PR #230 did). The template is a runtime deviation from them: the
   API returns each cell's `shippedLevel` and `overridden` (a row exists), so the operator sees every deviation. A
   deviation the owner wants permanent is moved into `MATRIX` and the document; the operator then resets the cell
   (sets it to its shipped level), which deletes the row, so later code changes reach that cell again. A row that
   already equals the shipped level still shows as `overridden` until it is reset.
8. **Not now: per-tenant templates.** A tenant that needs other defaults customises its own roles (ADR 0020). A
   per-tenant template layer would add a third source of truth for little gain; revisit if operators need to
   provision groups of tenants (for example by market pack) with different defaults.

## Owner acceptance (2026-11-03)

The merged-PR review of 2026-11-03 found two places where this decision went beyond accepted rules. The owner
accepted the ADR with both as explicit exceptions:

1. **ADR 0020 point 3 is amended.** Besides setting defaults at provisioning, an operator holding
   `platform.roles.manage` may push the default role template into existing tenants (point 5) without a
   support-access grant. The push only re-seeds uncustomised system roles and reports `pending`/`excess` for
   customised ones; it never changes a custom or customised role or an assignment. Any other change to a tenant's
   roles still needs the TENANCY-06 grant.
2. **Table hard-rule exception.** `default_role_level` and `default_role_level_change` are global platform tables:
   no `tenant_id`, no RLS, a composite text key on `default_role_level`, and setting a cell back to its shipped level
   deletes its row (the change table keeps the history). They are on the schema-guard allow-list for that reason.
   This exception covers these two tables only.

## Consequences

- The operator changes default roles for every tenant without a release, and every change has a who, when, why and
  before/after. Rollback is another change (or setting the cell back to shipped).
- `seed_default_roles` reads one more small table per run. `SeedReport` gains `excess`, and the CLI prints it.
- Access now depends on ops (for `active_tenant_ids`); ops does not depend on access, so there is no cycle.
- A code change to `MATRIX` still reaches a cell the operator overrode only when the override is reset; the
  `overridden` flag shows where that is.
- The operator console page is ACCESS-10, built on the operator origin once OPS-12 exists (ADR 0017 point 4).
