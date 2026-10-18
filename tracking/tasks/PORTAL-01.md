# PORTAL-01 — External portal users and grants: external user class, invitations with a named internal approver, grant provider

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ASSETS-01, PLAN-R1 |
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
(`user_class = 'portal'`), invited through identity's invite flow and activated only after a named internal owner
approves it, plus explicit `portal_grants` (project, optional asset subtree, actions) that reach the policy service
through a grant provider registered with `PolicyService.register` and are the only source of a portal user's
permissions (tag: extend).

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
    - internal (assignable through roles, ACCESS-02): `portal.user.view`, `portal.user.invite`,
      `portal.user.approve`, `portal.user.suspend`, `portal.grant.manage`;
    - external (given only by portal grants, step 4): `portal.record.view`, `portal.record.sign_off`,
      `portal.record.witness`, `portal.report.download`.

    Events (each with a version and a Pydantic payload in `events.py`): `portal_user.invited` v1,
    `portal_user.approved` v1, `portal_user.status_changed` v1, `portal_grant.created` v1, `portal_grant.revoked` v1.
    Payloads carry ids, codes and timestamps only (no email, no company name), e.g.
    `portal_grant.revoked` = `{grantId, portalUserId, projectId, assetId, reason}`.
  - 2. Migration `<timestamp>_portal_users_grants.py`, both tables rendered from `db/templates/tenant_table.sql.tpl`
    (FORCE RLS, fail-closed `NULLIF` policy, `aip_app` grants, `created_at`/`updated_at`/`deleted_at`):
    - create `portal_users` with `user_id uuid NOT NULL` (the identity `app_user` id; no cross-module FK, checked
      through `aip.modules.identity.api.get_user`), `company_name text NOT NULL` (1–200 chars, CHECK),
      `organisation_id uuid NULL` (passed through to identity's invite), `status text NOT NULL`
      `CHECK (status IN ('invited','pending_approval','active','suspended','expired'))`, `invited_by uuid NOT NULL`,
      `owner_user_id uuid NOT NULL` (the named internal owner), `approved_by uuid NULL`, `approved_at timestamptz NULL`,
      `first_signed_in_at timestamptz NULL`, `suspended_at timestamptz NULL`, `suspended_reason text NULL`,
      `expires_at timestamptz NOT NULL`, `sync_version`; CHECKs
      `ck_portal_users_owner_not_inviter CHECK (owner_user_id <> invited_by)`,
      `ck_portal_users_active_approved CHECK (status NOT IN ('active','suspended') OR (approved_by = owner_user_id AND approved_at IS NOT NULL))`;
      `UNIQUE (id, tenant_id)`; unique `(tenant_id, user_id) WHERE deleted_at IS NULL`; index `(tenant_id, status)`.
    - create `portal_grants` with `portal_user_id uuid NOT NULL`, `FOREIGN KEY (portal_user_id, tenant_id)
      REFERENCES portal_users (id, tenant_id)`, `project_id uuid NOT NULL`, `asset_id uuid NULL` (subtree root),
      `actions text[] NOT NULL` with
      `CHECK (cardinality(actions) BETWEEN 1 AND 4 AND actions <@ ARRAY['view','sign_off','witness','download']::text[] AND 'view' = ANY(actions))`,
      `expires_at timestamptz NULL`, `revoked_at timestamptz NULL`, `revoked_by uuid NULL`,
      `revoked_reason text NULL CHECK (revoked_reason IN ('manual','project_closed','user_suspended','user_expired'))`,
      `CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL))`, `created_by uuid NOT NULL`; indexes
      `(tenant_id, portal_user_id) WHERE revoked_at IS NULL AND deleted_at IS NULL`, `(tenant_id, project_id)`, and
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
    nothing unless the user's **effective status** is `active` (step 6) and identity's `get_user` says `active`.
    Each live grant (not revoked, not soft-deleted, `expires_at` null or in the future) gives, for each action, the
    permission codes of `ACTION_PERMISSIONS[action]` at `ProjectScope(project_id)` (no `asset_id`) or
    `AssetSubtreeScope(project_id, asset_id)`. `ACTION_PERMISSIONS` starts as `view → portal.record.view`,
    `sign_off → portal.record.sign_off`, `witness → portal.record.witness`, `download → portal.report.download`.
    `register_action_permissions(action, codes)` (exported from `api.py`) lets a host module add its own codes to an
    action (INSPECTIONS-05 adds the client-review transition permission to `sign_off`); an unknown action raises
    `ValueError`, and a code missing from the catalogue fails app start. Without `DATABASE_URL` it grants nothing,
    as `RoleGrantProvider` does.
  - 5. Invite (`service.invite_portal_user`), route `POST /api/v1/admin/portal/users`
    `{email, firstName, lastName, companyName, organisationId?, ownerUserId, expiresAt?, grants: [{projectId, assetId?, actions, expiresAt?}]}`,
    declared `requires("portal.user.invite")` plus identity's `step_up` dependency. In one `with_tenant` transaction:
    - (a) `grants` has 1–20 entries; each project is checked with `ProjectsApi.get_project` (missing or another
      tenant's → 404; status not `draft`/`active` → 422 `PROJECT_CLOSED`); each `assetId` with
      `aip.modules.assets.api.AssetsApi.get_asset` (missing → 422 `ASSET_NOT_FOUND`); the inviter also needs
      `portal.grant.manage` on each project (`PolicyService.can`, else 403).
    - (b) The owner must be an active `staff` user (`get_user`), not the inviter (422 `OWNER_IS_INVITER`), and hold
      `portal.user.approve` (`PolicyService.can` with an internal `AccessPrincipal` for the owner; else 422
      `OWNER_NOT_APPROVER`).
    - (c) `expiresAt` defaults to now + 180 days and may not exceed now + 400 days (422 `EXPIRY_TOO_LONG`); a grant's
      `expiresAt` may not exceed the user's.
    - (d) Call `aip.modules.identity.api.create_invite(conn, tenant_id=..., email=..., user_class="portal",
      first_name=..., last_name=..., organisation_id=..., invited_by=actor)`. An `InviteError` returns its own
      `status_code` and `code` (e.g. 409 `USER_EXISTS`, 409 `EMAIL_IN_OTHER_TENANT`) and rolls everything back.
    - (e) Insert the `portal_users` row (`status = 'invited'`) and the grants, emit `portal_user.invited` v1 and one
      `portal_grant.created` v1 per grant, and call `aip.modules.access.api.bump_access_version(conn)` (ADR 0020), all
      in the same transaction. 201 `{id, userId, status: "invited", expiresAt, grants: [...]}`.
  - 6. Lifecycle. `effective_status(row, now)` (pure): `expired` when `expires_at <= now` and the stored status is not
    `suspended`, else the stored status; reads and the provider use it, so expiry needs no job. Routes (all
    `/api/v1/admin/portal/users/{id}/...`, another tenant's id → 404, each emitting its event and bumping the access
    version in the same transaction):
    - `POST .../approve` (`portal.user.approve` + `step_up`): only from `pending_approval` (else 409
      `INVALID_STATUS`); only the named owner (else 403 `NOT_NAMED_OWNER`); sets `active`, `approved_by`,
      `approved_at`; emits `portal_user.approved` v1.
    - `POST .../suspend {reason}` (`portal.user.suspend`): from `invited`, `pending_approval` or `active`; sets
      `suspended`, `suspended_at`, `suspended_reason` (1–500 chars) and calls identity's
      `revoke_all_for_user(conn, user_id, "portal_suspended")`; emits `portal_user.status_changed` v1.
    - `POST .../reinstate` (`portal.user.approve` + `step_up`, named owner only): `suspended` → `active` when it was
      approved before, else → `pending_approval`; refused for an expired user (409 `EXPIRED`).
    - `POST .../grants` (`portal.grant.manage` on the project) and `DELETE .../grants/{grantId}` (revokes with reason
      `manual`, `revoked_by` = actor; 204; a second delete → 404).
    - `GET /api/v1/admin/portal/users?status=&q=&cursor=&limit=` (`portal.user.view`; cursor paging as in projects,
      `q` matches company name or identity email) and `GET /api/v1/admin/portal/users/{id}` (with live grants).
      Both return `effectiveStatus`.
    - `api.mark_signed_in(conn, user_id)` (for PORTAL-02): `invited` → `pending_approval` and stamps
      `first_signed_in_at`; idempotent; any other status unchanged.
  - 7. Project close: `events.py` subscribes `@subscriber("project.archived", 1)`; the handler revokes every live grant
    of that project with reason `project_closed` and emits one `portal_grant.revoked` v1 per grant. It is idempotent
    on the event (already revoked grants are skipped). A portal user left with no live grant keeps their account but
    gets no permissions.
  - 8. `api.py` publishes `PortalApi` with `get_portal_user_by_user_id(conn, user_id)`, `mark_signed_in`,
    `live_grants(conn, user_id)` (for PORTAL-02/03), `effective_status`, `register_action_permissions`,
    `PortalGrantProvider` and the action codes. Term keys (en-AU defaults, `config/terms/en-AU/portal.json`) for the
    five statuses, the four actions and every error code above; states stay stable codes. Regenerate
    `packages/api-client/openapi.json` (no drift, STACK-03).
- **acceptance**:
  - A portal user's permissions come only from live `portal_grants` of an active, unexpired, approved user: with a
    role assignment row inserted for the same user, `PolicyService.can` still denies the role's permission.
  - An internal user never gets a portal grant's permission, and the portal provider is never asked for one.
  - An asset-subtree grant allows a record under that asset and denies its sibling, its parent and a record with no
    asset path.
  - Invite, approve, suspend, reinstate, grant and revoke each write their event in the same transaction as the row
    change (so the audit writer records them) and bump the access version; a refused call writes nothing.
  - Archiving a project revokes its grants; an expired user or grant grants nothing without any job running.
- **tests**:
  - **unit**:
    - `_matches(Grant("portal.record.view", AssetSubtreeScope(P, A)), "portal.record.view", Resource(project_id=P, asset_path=f"{root.hex}.{A.hex}.{child.hex}"))` → `True`; with `asset_path=f"{root.hex}.{sibling.hex}"` → `False`; with `asset_path=None` → `False`; with project `Q` → `False`.
    - `effective_status` of an `active` row with `expires_at` 1 s in the past → `expired`; of a `suspended` row past
      expiry → `suspended`; of an `active` row expiring tomorrow → `active`.
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
      `client.a@rio.example` with owner = a second admin holding `portal.user.approve`, one grant on project P1
      `actions ["view","sign_off"]` → 201 `status: "invited"`; 1 `portal_users` row, 1 `portal_grants` row, 1
      identity `app_user` with `user_class = 'portal'` and `status = 'invited'`; `domain_events` gains 1
      `portal_user.invited` and 1 `portal_grant.created` row; the tenant's access version is +1.
    - The same invite with owner = the inviter → 422 `OWNER_IS_INVITER`; owner without `portal.user.approve` → 422
      `OWNER_NOT_APPROVER`; a project of `tenant-b` → 404; an archived project → 422 `PROJECT_CLOSED`; in each case
      `SELECT count(*) FROM portal_users` is unchanged and no `app_user` was created.
    - The invite without step-up → 401 `STEP_UP_REQUIRED`.
    - `mark_signed_in` → `pending_approval`; approve by the non-owner admin → 403 `NOT_NAMED_OWNER`; approve by the
      owner → 200 `active`, `approved_by` = owner; approving again → 409 `INVALID_STATUS`.
    - Grant provider: the active user's `AccessPrincipal(external=True)` → `can("portal.record.view", Resource(project_id=P1))`
      allowed, on P2 denied, `can("project.view", Resource(project_id=P1))` denied; after inserting an ACCESS-02 role
      assignment of `project_viewer` on P1 for that user, `project.view` is still denied.
    - Before approval (`pending_approval`) the provider returns 0 grants; after `suspend` it returns 0 grants and
      `SELECT count(*) FROM user_session WHERE user_id = :u AND revoked_at IS NULL` is 0.
    - `UPDATE portal_users SET expires_at = now() - interval '1 second'` (as the test owner) → the provider returns 0
      grants and `GET /api/v1/admin/portal/users/{id}` shows `effectiveStatus: "expired"`.
    - A grant with `expires_at` in the past gives no permission while another live grant on P2 still does.
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
