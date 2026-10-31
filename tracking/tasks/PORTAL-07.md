# PORTAL-07 — External users admin: register, invite with grant builder, access expiry and renewal (/admin/portal/users)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: full spec written 2026-10-31 once PORTAL-01 merged (was a stub) -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-03, PORTAL-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md) and
   [`routes.md`](../../docs/blueprint/modules/portal/routes.md) (the three `/admin/portal/users` pages only)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope),
   [0036](../../docs/adr/0036-r1-module-decisions.md) ("Owner answers" portal lines: the inviting project admin is
   the only approval; per-project access period with renewal)
4. Code: [`PORTAL-01`](PORTAL-01.md)'s routes, service and repository in `apps/api/aip/modules/portal/`; the
   register pattern in `apps/web/src/features/reports/` (REPORTS-04) and `features/projects/` (form, server errors);
   `features/identity/step-up.ts` (IDENTITY-04); `features/assets/ParentPicker.tsx` (asset subtree picker)

## Spec

Build the internal admin pages for external (portal) users on PORTAL-01's API: a register with each user's
earliest grant expiry and an "expiring soon" filter, an invite form with a grant builder (project, optional asset
subtree, actions), and a detail page to renew, add and revoke grants and to suspend and reinstate the user. The
project admin who invites is the only approval, so there is no approval tab or approver field (ADR 0036, which
replaces routes.md's "pending approvals", "internal owner" and "submit for approval"); the expiry is the project's
`portal_access_days` and is never typed in (tag: extend).

Out of scope: expiry reminders and the ignore option (PORTAL-08); sessions and devices, audit trail, onboarding gate,
share packs, download policy, resend invite, PIN reset and export (not in R1 per ADR 0036, or later tasks).

- **files**:
  - apps/api/aip/modules/portal/repository.py, service.py, routes.py (list filters)
  - apps/api/aip/modules/portal/tests/test_admin_filters_db.py
  - apps/web/src/features/portal/{nav.ts,search.ts,columns.tsx,format.ts,PortalUsersRegister.tsx,InviteForm.tsx,
    GrantBuilder.tsx,PortalUserDetail.tsx,GrantsTable.tsx,actions.ts,portal.css}
  - apps/web/src/features/portal/__tests__/{portal-users.test.tsx,invite.test.tsx,detail.test.tsx,search.test.ts}
  - apps/web/src/routes/_app/admin/portal/users/{index.tsx,new.tsx,$portalUserId.tsx}
  - apps/web/src/router.ts, apps/web/src/features/shell/dev/dev-session-stub.ts
  - config/terms/en-AU/portal.json
  - e2e/web/portal-users.spec.ts
  - packages/api-client (regenerated)
- **steps**:
  - 1. API, list filters (the only API change). `GET /api/v1/admin/portal/users` gains
    `expiringWithinDays` (integer 1–400) and `projectId` (uuid). `expiringWithinDays=N` keeps users with at least one
    live grant (not revoked, not soft-deleted) whose `expires_at` is in `(now, now + N days]`; `projectId=P` keeps
    users with an unrevoked grant on P. Both are `EXISTS` subqueries on `portal_grants` under RLS and combine with
    `status`, `q` and the cursor. Same permission (`portal.user.view`). Regenerate the client.
  - 2. Nav: "External users" under Settings (ADR 0018, module-groups doc: "Settings > Portal users"), permission
    `portal.user.view`, no release flag (the portal is R1 demo-slice scope, not a deferred module; DESIGN-15 flags only
    gate deferred modules such as `bim` and `ai`).
  - 3. Register `/admin/portal/users` on `RegisterTable`: columns email, company, status (`effectiveStatus` chip:
    invited, active, suspended, expired), projects (count of grants that are not revoked), next expiry (the earliest
    live grant's `expiresAt`, with an "expiring soon" chip within 30 days), first sign-in (hidden by default). Filters
    in the URL: `status` (quick; invited, active, suspended), `expiring` (quick; 7, 30 or 90 days → `expiringWithinDays`),
    `project` (select of the tenant's projects → `projectId`), and `q` search (email or company). Cursor paging, column
    chooser. "Invite external user" shows only with `portal.user.invite`. Enter on a row opens the detail.
  - 4. Invite `/admin/portal/users/new` (needs `portal.user.invite`, else a denied panel): email, first name, last name,
    company, and the grant builder: 1–20 rows of project (draft or active projects only), optional asset subtree
    (`ParentPicker`, "Whole project" as the empty choice) and action checkboxes (view always on and disabled;
    sign off, witness, download). A note says access lasts for each project's access period and that the inviter's
    invitation is the approval. Client validation uses the generated Zod schema (`schemas.PortalUsersInviteBody`).
    Server answers: 409 `USER_EXISTS`, `EMAIL_IN_OTHER_TENANT`, `PORTAL_USER_EXISTS` on email; 409 `GRANT_EXISTS`,
    422 `PROJECT_CLOSED`, `ASSET_NOT_FOUND` on the grant row they name (else on the builder); 403 → denied panel;
    401 `STEP_UP_REQUIRED` → `startStepUp` with the form values saved, and on return the form is refilled and offers
    to send again. 201 → the detail page of the new user.
  - 5. Detail `/admin/portal/users/$portalUserId` on `RecordDetail`: header with email, company and the status chip;
    tabs Details (name of company, status, invited, first sign-in, suspended reason) and Access (the grants table:
    project, asset subtree, actions, state chip live/expired, expires, renewed). Actions, each shown only with its
    permission: renew a live or expired grant (`portal.grant.manage`; step-up, retried after return), revoke a grant
    (`portal.grant.manage`; confirm dialog), add a grant (`portal.grant.manage`; one grant-builder row in a dialog),
    suspend with a reason (`portal.user.suspend`; dialog, 1–500 chars) and reinstate (`portal.user.suspend`; step-up).
    A 404 shows a not-found panel (another tenant's id looks the same as a missing one).
  - 6. Terms for every label, state, action and error code in `config/terms/en-AU/portal.json` (`portal.admin.*`);
    the stub session's alice gets the four internal portal permissions.
- **acceptance**:
  - The register lists only this tenant's external users, with each user's next expiry; "expiring within 30 days"
    shows only users with a live grant ending in that window; filters and search survive a reload (URL).
  - Inviting a client with two grants creates the user and grants through PORTAL-01's API, with no expiry field and
    no approver; a closed project or an existing email shows its error on the right field and nothing is created.
  - Renewing an expired grant makes it live again for another access period; revoking removes it from the list;
    suspend and reinstate change the status chip.
  - Without `portal.user.view` the nav item is hidden and the API's 403 shows the denied state; without
    `portal.user.invite` / `portal.grant.manage` / `portal.user.suspend` their buttons are hidden.
- **tests**:
  - **unit** (vitest + MSW, through the real router):
    - `toListParams` maps `status`, `expiring=30`, `project` and `q`; invalid values are dropped by `validateSearch`.
    - Register: rows show company, email, status chip and next expiry; "expiring soon" chip within 30 days; the
      expiring filter sends `expiringWithinDays=30`; the invite link needs `portal.user.invite`; axe has no
      serious or critical violation.
    - Invite: the body sent has the grants built (view always present) and no expiry; 422 `PROJECT_CLOSED` lands on
      that grant row; 409 `USER_EXISTS` on email; 401 `STEP_UP_REQUIRED` saves the form and navigates to the step-up
      URL; on return the form is refilled.
    - Detail: renew posts to `.../grants/{id}/renew` and the state chip turns live; revoke asks to confirm then
      sends `DELETE`; suspend needs a reason; buttons hidden without their permission; 404 shows not found.
  - **integration** (testcontainers Postgres, `kaefer-demo` and `tenant-b`):
    - Users A (grant expiring in 5 days), B (grant expiring in 100 days), C (only grant expired), D (grant expiring in
      5 days but revoked) → `expiringWithinDays=30` returns A only; `=400` returns A and B.
    - `projectId=P1` returns users with an unrevoked grant on P1 only; combined with `status=invited` narrows further.
    - `expiringWithinDays=0` and `=401` → 422. A `tenant-b` admin filtering by a `kaefer-demo` project gets 0 rows.
  - **e2e** (Playwright, stub session, API answered with `page.route` as reports.spec.ts does):
    - Register journey: filter by expiring and status, both in the URL; open a user; renew an expired grant.
    - Invite journey: build two grants and submit; the request body has no expiry.
    - Cross-tenant: bob (tenant-b, no portal permission) sees no "External users" nav item and the page shows the
      denied state; a detail id answered 404 shows not found.
    - axe (serious/critical) on register, invite and detail; the register fits a phone without horizontal scroll.
