# PORTAL-01 — External portal users and grants: external user class, project-admin invitations, per-project access expiry, grant provider

<!-- hand-edited: owner answers 2026-10-18 (project admin invites, no second approval; per-project access period 180 to 400 days with renewal) -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ASSETS-01, PLAN-R1, PROJECTS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md) and
   [`data-model.md`](../../docs/blueprint/modules/portal/data-model.md) (`portal_users`, `portal_grants` only)
3. ADRs: [0036](../../docs/adr/0036-r1-module-decisions.md) ("Owner answers" portal lines and choice 7),
   [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (tail note: portal in R1),
   [0005](../../docs/adr/0005-identity-architecture.md) (Keycloak holds passwords and second factors),
   [0034](../../docs/adr/0034-invites-and-step-up-implementation.md) (invites, step-up),
   [0020](../../docs/adr/0020-role-management-and-guardrails.md) (access version),
   [0002](../../docs/adr/0002-data-access-and-migrations.md) (`with_tenant`, templates),
   [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox in the same transaction)
4. Code: `apps/api/aip/platform/access/policy.py` (`PolicyService.register`, `AccessPrincipal`, `Resource`,
   `_matches`), `apps/api/aip/platform/access/grants.py`, `apps/api/aip/modules/access/roles/grant_provider.py`
   (`RoleGrantProvider`, the pattern to copy), `apps/api/aip/modules/identity/api.py` (`create_invite`,
   `InviteError`, `get_user`, `set_user_status`, `revoke_all_for_user`, `step_up`), `apps/api/aip/main.py`
   (`identity_access_principal`, where providers are registered), `apps/api/aip/modules/projects/` (module pattern)

## Spec

Give the tenant an external user class for clients: a `portal_users` row 1:1 with identity's `app_user`
(`user_class = 'portal'`), invited by a project admin through identity's invite flow and active from their first
sign-in with no second approval, plus explicit `portal_grants` (project, optional asset subtree, actions) that expire
after the project's access period (default 180 days, a project setting of up to 400) unless the project admin renews
them, and that reach the policy service through a grant provider registered with `PolicyService.register` as the only
source of a portal user's permissions (tag: extend).

Owner answers (2026-10-18, ADR 0036): the project admin who invites is the only approval; access is per project and
expires after `portal_access_days` (a PROJECTS-04 project setting, default 180, at most 400); renewal grants another
period. The expiry reminders and the ignore option are PORTAL-08.

Out of scope: portal sign-in, the portal session and the route allow-list (PORTAL-02); the portal app and inbox
(PORTAL-03); the admin page (PORTAL-07); client sign-off actions (PORTAL-04); witness (PORTAL-06); client reports
(PORTAL-05). Not in R1 at all (ADR 0036): share packs, magic links and PINs (`portal_credentials`), subcontractor
NCR responses, onboarding gate, condition dashboard, watermarking and download policy, per-client branding,
`portal_settings`. Audit goes to the main audit chain (events plus `AuditApi.record_security_event`), so no
`portal_audit_events` table.

- **files**:
  - apps/api/migrations/versions/<timestamp>_portal_users_grants.py
  - apps/api/aip/modules/portal/__init__.py
  - apps/api/aip/modules/portal/manifest.toml
  - apps/api/aip/modules/portal/tables.py
  - apps/api/aip/modules/portal/schemas.py
  - apps/api/aip/modules/portal/repository.py
  - apps/api/aip/modules/portal/service.py
  - apps/api/aip/modules/portal/grant_provider.py
  - apps/api/aip/modules/portal/policies.py
  - apps/api/aip/modules/portal/events.py
  - apps/api/aip/modules/portal/routes.py
  - apps/api/aip/modules/portal/api.py
  - apps/api/aip/modules/portal/tests/conftest.py
  - apps/api/aip/modules/portal/tests/test_unit.py
  - apps/api/aip/modules/portal/tests/test_portal_users_db.py
  - apps/api/aip/modules/portal/tests/test_grant_provider_db.py
  - apps/api/aip/platform/access/grants.py
  - apps/api/aip/platform/access/policy.py
  - apps/api/aip/platform/access/tests/test_policy.py
  - apps/api/aip/main.py
  - config/terms/en-AU/portal.json
  - packages/api-client/openapi.json
- **steps**:
  - 1. Scaffold the module with `python tools/new_module.py portal` (it copies `apps/api/aip/modules/_template/`).
    `manifest.toml`: `id = "portal"`, `depends_on = ["tenancy", "identity", "access", "projects", "assets", "audit"]`,
    `permission_namespaces = ["portal"]`, `subscribes = [{ name = "project.archived", version = 1 }]`. Permissions,
    each with a description:
    - internal (assignable through roles, ACCESS-02; ACCESS-07 maps `invite` so project admins get it):
      `portal.user.view`, `portal.user.invite`, `portal.user.suspend`, `portal.grant.manage`;
    - external (given only by portal grants, step 4): `portal.record.view`, `portal.record.sign_off`,
      `portal.record.witness`, `portal.report.download`.

    Events (each with a version and a Pydantic payload in `events.py`): `portal_user.invited` v1,
    `portal_user.status_changed` v1, `portal_grant.created` v1, `portal_grant.renewed` v1, `portal_grant.revoked` v1.
    Payloads carry ids, codes and timestamps only (no email, no company name), e.g.
    `portal_grant.revoked` = `{grantId, portalUserId, projectId, assetId, reason}`.
  - 2. Migration `<timestamp>_portal_users_grants.py`, both tables rendered from `db/templates/tenant_table.sql.tpl`
    (FORCE RLS, fail-closed `NULLIF` policy, `aip_app` grants, `created_at`/`updated_at`/`deleted_at`):
    - create `portal_users` with `user_id uuid NOT NULL` (the identity `app_user` id; no cross-module FK, checked
      through `aip.modules.identity.api.get_user`), `company_name text NOT NULL` (1–200 chars, CHECK),
      `organisation_id uuid NULL` (passed through to identity's invite), `status text NOT NULL`
      `CHECK (status IN ('invited','active','suspended'))`, `invited_by uuid NOT NULL`,
      `first_signed_in_at timestamptz NULL`, `suspended_at timestamptz NULL`, `suspended_reason text NULL`,
      `sync_version`; `UNIQUE (id, tenant_id)`; unique `(tenant_id, user_id) WHERE deleted_at IS NULL`; index `(tenant_id, status)`.
    - create `portal_grants` with `portal_user_id uuid NOT NULL`, `FOREIGN KEY (portal_user_id, tenant_id)
      REFERENCES portal_users (id, tenant_id)`, `project_id uuid NOT NULL`, `asset_id uuid NULL` (subtree root),
      `actions text[] NOT NULL` with
      `CHECK (cardinality(actions) BETWEEN 1 AND 4 AND actions <@ ARRAY['view','sign_off','witness','download']::text[] AND 'view' = ANY(actions))`,
      `access_days integer NOT NULL CHECK (access_days BETWEEN 1 AND 400)` (the project's period when granted or last
      renewed), `expires_at timestamptz NOT NULL`, `renewed_at timestamptz NULL`, `renewed_by uuid NULL`,
      `revoked_at timestamptz NULL`, `revoked_by uuid NULL`,
      `revoked_reason text NULL CHECK (revoked_reason IN ('manual','project_closed','user_suspended'))`,
      `CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL))`, `created_by uuid NOT NULL`; indexes
      `(tenant_id, portal_user_id) WHERE revoked_at IS NULL AND deleted_at IS NULL`, `(tenant_id, project_id)`,
      `(tenant_id, expires_at) WHERE revoked_at IS NULL AND deleted_at IS NULL` (for the PORTAL-08 reminder job), and
      unique `(tenant_id, portal_user_id, project_id, coalesce(asset_id, '00000000-0000-0000-0000-000000000000'))
      WHERE revoked_at IS NULL AND deleted_at IS NULL` (one live grant per user, project and subtree).
    - `downgrade()` drops both tables.
  - 3. Platform access (the only platform changes):
    - `grants.py`: add `AssetSubtreeScope(project_id, asset_id)` to `GrantScope`.
    - `policy.py`: `Resource` gains `asset_path: str | None = None` (the ltree path text of the record's asset);
      `_matches` accepts an `AssetSubtreeScope` only when `resource.project_id` equals the scope's project **and**
      `resource.asset_path` has a label equal to `asset_id.hex` (asset path labels are the node id without dashes,
      ASSETS-01 `ck_assets_path_leaf`); a missing `asset_path` never matches (fail closed).
    - `AccessPrincipal` gains `external: bool = False`. `PolicyService._grants` asks, for an external principal,
      only providers whose class sets `serves_external = True`, and for an internal one only providers that do not.
      So `RoleGrantProvider` can never give a portal user a role permission, even if an assignment row exists.
    - `main.py`: `identity_access_principal` sets `external = principal.user_class == "portal"`, and
      `create_app` registers `PortalGrantProvider()` next to `RoleGrantProvider()`.
  - 4. `grant_provider.py`: `PortalGrantProvider` (`serves_external = True`). For an external principal it reads, in
    its own `with_tenant(principal.tenant_id)` transaction, the caller's `portal_users` row and live grants and returns
    nothing unless the user's status is `active` (step 6) and identity's `get_user` says `active`.
    Each live grant (not revoked, not soft-deleted, `expires_at` in the future) gives, for each action, the
    permission codes of `ACTION_PERMISSIONS[action]` at `ProjectScope(project_id)` (no `asset_id`) or
    `AssetSubtreeScope(project_id, asset_id)`. `ACTION_PERMISSIONS` starts as `view → portal.record.view`,
    `sign_off → portal.record.sign_off`, `witness → portal.record.witness`, `download → portal.report.download`.
    `register_action_permissions(action, codes)` (exported from `api.py`) lets a host module add its own codes to an
    action (INSPECTIONS-05 adds the client-review transition permission to `sign_off`); an unknown action raises
    `ValueError`, and a code missing from the catalogue fails app start. Without `DATABASE_URL` it grants nothing,
    as `RoleGrantProvider` does.
  - 5. Invite (`service.invite_portal_user`), route `POST /api/v1/admin/portal/users`
    `{email, firstName, lastName, companyName, organisationId?, grants: [{projectId, assetId?, actions}]}`,
    declared `requires("portal.user.invite")` plus identity's `step_up` dependency. In one `with_tenant` transaction:
    - (a) `grants` has 1–20 entries; each project is checked with `ProjectsApi.get_project` (missing or another
      tenant's → 404; status not `draft`/`active` → 422 `PROJECT_CLOSED`); each `assetId` with
      `aip.modules.assets.api.AssetsApi.get_asset` (missing → 422 `ASSET_NOT_FOUND`); the inviter needs
      `portal.user.invite` and `portal.grant.manage` on each project (`PolicyService.can` with
      `Resource(project_id=...)`, else 403). That project-admin invitation is the only approval (owner, 2026-10-18).
    - (b) No second approver.
    - (c) Each grant's `access_days` is the project's `portal_access_days` setting, read with
      `aip.modules.projects.api.ProjectsApi.get_setting(conn, project_id, "portal_access_days")` (PROJECTS-04; an
      integer from 1 to 400, default 180; a value outside that range is treated as 180 and logged), and
      `expires_at` = now + `access_days`. The body cannot set an expiry.
    - (d) Call `aip.modules.identity.api.create_invite(conn, tenant_id=..., email=..., user_class="portal",
      first_name=..., last_name=..., organisation_id=..., invited_by=actor)`. An `InviteError` returns its own
      `status_code` and `code` (e.g. 409 `USER_EXISTS`, 409 `EMAIL_IN_OTHER_TENANT`) and rolls everything back.
    - (e) Insert the `portal_users` row (`status = 'invited'`) and the grants, emit `portal_user.invited` v1 and one
      `portal_grant.created` v1 per grant, and call `aip.modules.access.api.bump_access_version(conn)` (ADR 0020), all
      in the same transaction. 201 `{id, userId, status: "invited", expiresAt, grants: [...]}`.
  - 6. Lifecycle. `grant_state(grant, now)` (pure): `revoked` when `revoked_at` is set, `expired` when
    `expires_at <= now`, else `live`; reads and the provider use it, so expiry needs no job. A user's
    `effectiveStatus` is `suspended` or `invited` as stored, `expired` when active with no live grant and at least one
    expired grant, else `active`. Routes (all `/api/v1/admin/portal/users/{id}/...`, another tenant's id → 404, each
    emitting its event and bumping the access version in the same transaction):
    - `POST .../grants/{grantId}/renew` (`portal.grant.manage` on the grant's project + `step_up`): allowed while
      the grant is live or expired (not revoked, else 409 `REVOKED`); re-reads the project's `portal_access_days`
      and sets `access_days`, `expires_at` = now + `access_days`, `renewed_at`, `renewed_by`; emits
      `portal_grant.renewed` v1 `{grantId, portalUserId, projectId, expiresAt, renewedBy}`. Renewing an expired
      grant restores access at once.
    - `POST .../suspend {reason}` (`portal.user.suspend`): from `invited` or `active`; sets
      `suspended`, `suspended_at`, `suspended_reason` (1–500 chars) and calls identity's
      `revoke_all_for_user(conn, user_id, "portal_suspended")`; emits `portal_user.status_changed` v1.
    - `POST .../reinstate` (`portal.user.suspend` + `step_up`): `suspended` → `active` when the user has signed in
      before, else → `invited`.
    - `POST .../grants` (`portal.grant.manage` on the project) and `DELETE .../grants/{grantId}` (revokes with reason
      `manual`, `revoked_by` = actor; 204; a second delete → 404).
    - `GET /api/v1/admin/portal/users?status=&q=&cursor=&limit=` (`portal.user.view`; cursor paging as in projects,
      `q` matches company name or identity email) and `GET /api/v1/admin/portal/users/{id}` (with live grants).
      Both return `effectiveStatus`.
    - `api.mark_signed_in(conn, user_id)` (for PORTAL-02): `invited` → `active` and stamps `first_signed_in_at`;
      idempotent; any other status unchanged.
  - 7. Project close: `events.py` subscribes `@subscriber("project.archived", 1)`; the handler revokes every live grant
    of that project with reason `project_closed` and emits one `portal_grant.revoked` v1 per grant. It is idempotent
    on the event (already revoked grants are skipped). A portal user left with no live grant keeps their account but
    gets no permissions.
  - 8. `api.py` publishes `PortalApi` with `get_portal_user_by_user_id(conn, user_id)`, `mark_signed_in`,
    `live_grants(conn, user_id)` (for PORTAL-02/03), `grants_expiring_between(conn, start, end)` (for PORTAL-08),
    `grant_state`, `effective_status`, `register_action_permissions`,
    `PortalGrantProvider` and the action codes. Term keys (en-AU defaults, `config/terms/en-AU/portal.json`) for the
    user statuses, the three grant states, the four actions and every error code above; states stay stable codes. Regenerate
    `packages/api-client/openapi.json` (no drift, STACK-03).
- **acceptance**:
  - A portal user's permissions come only from live, unexpired `portal_grants` of an active user: with a
    role assignment row inserted for the same user, `PolicyService.can` still denies the role's permission.
  - An internal user never gets a portal grant's permission, and the portal provider is never asked for one.
  - An asset-subtree grant allows a record under that asset and denies its sibling, its parent and a record with no
    asset path.
  - Invite, renew, suspend, reinstate, grant and revoke each write their event in the same transaction as the row
    change (so the audit writer records them) and bump the access version; a refused call writes nothing.
  - Archiving a project revokes its grants; an expired grant grants nothing without any job running, and renewing it
    restores access for another project access period.
  - A grant's period comes from its project's `portal_access_days` (default 180, at most 400).
- **tests**:
  - **unit**:
    - `_matches(Grant("portal.record.view", AssetSubtreeScope(P, A)), "portal.record.view", Resource(project_id=P, asset_path=f"{root.hex}.{A.hex}.{child.hex}"))` → `True`; with `asset_path=f"{root.hex}.{sibling.hex}"` → `False`; with `asset_path=None` → `False`; with project `Q` → `False`.
    - `grant_state` of a grant with `expires_at` 1 s in the past → `expired`; expiring tomorrow → `live`; revoked →
      `revoked`. `effective_status` of an active user whose only grant expired → `expired`; with one live grant left →
      `active`; a suspended user → `suspended`.
    - `register_action_permissions("countersign", ["x.y"])` → `ValueError`; `register_action_permissions("sign_off",
      ["inspection.client_review.sign"])` then expanding `["view","sign_off"]` → `{"portal.record.view",
      "portal.record.sign_off", "inspection.client_review.sign"}`.
    - `PolicyService` with a fake internal provider and a fake external provider: an `external=True` principal sees
      only the external provider's grants; an internal one only the internal provider's.
    - The invite body with an unknown key `{"role": "admin", ...}` → 422 (strict schema); `actions: ["view","delete"]`
      → 422; `actions: ["sign_off"]` (no `view`) → 422.
  - **integration** (testcontainers Postgres, TESTING-01 tenants `kaefer-demo` and `tenant-b`, identity's Keycloak
    calls replaced by the ops job registry, as identity's own tests do):
    - A `kaefer-demo` admin with `portal.user.invite`, `portal.grant.manage` and a fresh step-up POSTs an invite for
      `client.a@rio.example` with one grant on project P1 (`portal_access_days` unset) `actions ["view","sign_off"]` →
      201 `status: "invited"`, the grant's `access_days` 180 and `expires_at` now + 180 days; 1 `portal_users` row,
      1 `portal_grants` row, 1
      identity `app_user` with `user_class = 'portal'` and `status = 'invited'`; `domain_events` gains 1
      `portal_user.invited` and 1 `portal_grant.created` row; the tenant's access version is +1.
    - With P2's `portal_access_days` set to 365, a grant on P2 has `access_days` 365. A body with `expiresAt` → 422
      (unknown key). An inviter without `portal.user.invite` on P1 → 403; a project of `tenant-b` → 404; an archived
      project → 422 `PROJECT_CLOSED`; in each case
      `SELECT count(*) FROM portal_users` is unchanged and no `app_user` was created.
    - The invite without step-up → 401 `STEP_UP_REQUIRED`.
    - `mark_signed_in` → `active` with no other approval; calling it again changes nothing.
    - Renew: set the P1 grant's `expires_at` to now − 1 s (as the test owner) → the provider returns 0 grants and the
      user shows `effectiveStatus: "expired"`; `POST .../grants/{id}/renew` by the P1 project admin → 200 with
      `expires_at` ≈ now + 180 days, the provider returns the grant again, and 1 `portal_grant.renewed` event; a
      renew by an admin of another project only → 403; renewing a revoked grant → 409 `REVOKED`.
    - Grant provider: the active user's `AccessPrincipal(external=True)` → `can("portal.record.view", Resource(project_id=P1))`
      allowed, on P2 denied, `can("project.view", Resource(project_id=P1))` denied; after inserting an ACCESS-02 role
      assignment of `project_viewer` on P1 for that user, `project.view` is still denied.
    - Before the first sign-in (`invited`) the provider returns 0 grants; after `suspend` it returns 0 grants and
      `SELECT count(*) FROM user_session WHERE user_id = :u AND revoked_at IS NULL` is 0.
    - `UPDATE portal_grants SET expires_at = now() - interval '1 second' WHERE project_id = :p1` (as the test owner)
      → no permission on P1 while the live grant on P2 still gives one.
    - Deliver a `project.archived` v1 event for P1 through the dispatcher → the P1 `portal_grants` row has
      `revoked_reason = 'project_closed'` and 1 `portal_grant.revoked` event; delivering it again changes nothing.
    - `DELETE .../grants/{id}` → 204 and `revoked_reason = 'manual'`; again → 404.
    - A `tenant-b` admin with every portal permission: `GET /api/v1/admin/portal/users/{kaefer user id}` → 404; the
      list returns 0 rows of `kaefer-demo`.
    - With `app.tenant_id` unset, `SELECT count(*) FROM portal_grants` → 0 (fail-closed RLS).
    - Two live grants for the same user, project and no asset → the second insert fails with the unique index (409
      `GRANT_EXISTS` through the route).
  - **e2e**:
    - None in this task (API-only, and every route needs a step-up session that the Playwright API project cannot
      create without the Keycloak browser flow). The integration tests above cover the routes, including the
      `tenant-b` 404, on real Postgres; the browser journeys, the cross-tenant check and the cross-grant check on the
      portal host come with PORTAL-03, and the admin page journeys with PORTAL-07.
