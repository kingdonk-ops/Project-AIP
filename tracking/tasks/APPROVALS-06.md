# APPROVALS-06 — Approvals inbox API + page

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | APPROVALS-04, DESIGN-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md) (`apps/web/src/features/<module>/`, orval client)
4. Only for the page layout: [`routes.md`](../../docs/blueprint/modules/approvals/routes.md) ("Approvals inbox `/approvals`")

## Spec

Give every user one place to see and decide the approval steps waiting on them, whether assigned directly, by role or by team. The page is built on the DESIGN-03 register table, with a preview pane and batch approve or reject (tag: extend).

- **files**:
  - apps/api/src/modules/approvals/inbox/inbox.service.ts
  - apps/api/src/modules/approvals/inbox/inbox.controller.ts
  - apps/api/src/modules/approvals/inbox/summary-providers.ts
  - apps/api/src/modules/approvals/api.ts
  - apps/api/src/modules/approvals/tests/inbox.int.spec.ts
  - apps/web/src/app/(app)/approvals/page.tsx
  - apps/web/src/features/approvals/pages/ApprovalsInbox.tsx
  - apps/web/src/features/approvals/components/InboxPreview.tsx
  - apps/web/src/features/approvals/components/DecisionDialog.tsx
  - apps/web/src/features/approvals/tests/ApprovalsInbox.test.tsx
  - e2e/web/approvals-inbox.spec.ts
- **steps**:
  - 1. `GET /api/v1/approvals/inbox?recordType=&projectId=&due=overdue|today|week&cursor=&limit=` (default limit 25, max 100):
    - It returns pending steps the caller can decide, using `pendingStepsQuery(actor)` from APPROVALS-04 (user steps, role steps within the role's scope, team steps).
    - It keeps only projects that `PolicyService` allows, with RLS as the second layer.
    - Rows are `{instanceId, stepId, recordType, recordId, title, projectId, requestedBy, stepOrder, dueAt, ageHours}`, ordered by `dueAt asc nulls last, created_at asc`, with cursor pagination.
    - Delegation and value-band filters are out of scope until delegation exists.
  - 2. `GET /api/v1/approvals/inbox/count` returns `{pending, overdue}` for the nav badge.
  - 3. `summary-providers.ts`: `registerRecordSummaryProvider(recordType, (ctx, ids[]) => Promise<Map<id, {title, href}>>)`, exported through `api.ts`. It is batched, with one call per record type per page. Without a provider, `title` is the term key `approvals.inbox.untitled` plus the record id.
  - 4. `POST /api/v1/approvals/inbox/batch-decide {items: [{instanceId, stepId}] (1..50), decision, comment?}`. It runs APPROVALS-04 `decide` per item, each in its own transaction, and returns `{results: [{stepId, status: 200|403|409, code?}]}`, so partial success is explicit. A reject needs a comment.
  - 5. Page `/approvals` (`ApprovalsInbox.tsx`) uses the DESIGN-03 register table with:
    - filters (type, project, due)
    - server pagination
    - row selection and a batch bar (Approve or Reject; Reject opens `DecisionDialog`, where the comment is required)
    - a right-hand `InboxPreview` (summary, step, due, Approve, Reject, Open record)
    - empty, loading and error states

    All strings use `t('approvals.inbox.*')` keys. Data comes from the regenerated `packages/api-client` (orval). The page has no hand-written fetch.
  - 6. Add the nav-rail entry with the count badge in the approvals feature's nav registration, using the DESIGN-02 extension point. Do not edit shell internals.
- **acceptance**:
  - A user sees exactly the steps they can decide: direct, by role in scope, or by team. They never see other projects' or tenants' steps.
  - A batch decision reports each item's outcome, and a failure doesn't roll back the others.
  - The page passes axe with no violations and works by keyboard alone (select a row, open the preview, approve).
- **tests**:
  - **unit**:
    - The `due=overdue` filter with now `2026-10-07T10:00:00Z` includes `dueAt 09:00Z` and excludes `11:00Z`.
    - A batch body with 51 items → Zod error `too_big` at `['items']`.
    - `DecisionDialog` (Vitest + Testing Library) with Reject and an empty comment → the Confirm button is disabled. Typing `'wrong revision'` enables it.
    - `ApprovalsInbox` with MSW returning 0 rows → the `approvals.inbox.empty` text renders.
  - **integration**:
    - Testcontainers Postgres with `kaefer-demo` seeded so that:
      - U1 has 2 direct steps, 1 role-QA step in P1 and 1 team-Client step.
      - A QA step in P2 exists where U1 has QA only on P1.
      - 1 step belongs to U2 only.

      `GET /inbox` as U1 → 4 rows, ordered by due date. The P2 step and U2's step are absent.
    - `GET /inbox/count` as U1 → `{pending:4, overdue:<seeded overdue count>}`.
    - `batch-decide approve` over 3 items where one was already decided → results `[200, 200, 409]`. Two steps are now `approved`.
    - A `tenant-b` user calling `GET /inbox` → 0 rows.
    - With a registered summary provider for `demo` → `title` comes from the provider. Without one → the fallback key.
  - **e2e**:
    - Playwright `web` project. Sign in as the `kaefer-demo` approver fixture and open `/approvals`. The seeded inspection step is listed. Select it, the preview shows the step, click Approve, then a toast appears and the row disappears. The nav badge count drops by 1.
    - Reject a second row with no comment → the dialog blocks submission. Enter a comment → the row disappears.
    - A `tenant-b` user on `/approvals` → the empty state.
    - The axe scan on `/approvals` → 0 violations.
