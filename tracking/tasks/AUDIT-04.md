# AUDIT-04 — Activity/timeline API + project activity tab

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`audit`](../../docs/blueprint/modules/audit/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, AUDIT-02, DESIGN-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/audit/README.md`](../../docs/blueprint/modules/audit/README.md)
3. ADRs: 0002 (RLS, Kysely), 0004 (apps/web features, packages/ui)
4. Only if the step needs it: the project timeline and activity tab sections in [`routes.md`](../../docs/blueprint/modules/audit/routes.md) and [`ui-layout.md`](../../docs/blueprint/modules/audit/ui-layout.md)

## Spec

Make history visible. Add cursor-paginated timeline and per-record activity endpoints over audit_log, filtered by the viewer's permissions, and a reusable ActivityTab mounted as the History tab of the project detail.

- **files**:
  - apps/api/src/modules/audit/timeline.service.ts
  - apps/api/src/modules/audit/timeline.controller.ts
  - apps/api/src/modules/audit/schemas.ts
  - apps/api/src/modules/audit/tests/
  - apps/web/src/features/audit/ActivityTab.tsx
  - apps/web/src/features/audit/ActivityItem.tsx
  - apps/web/src/features/audit/__tests__/
  - apps/web/src/app/(app)/projects/[projectId]/activity/page.tsx
  - config/terms/en-AU/audit.json
- **steps**:
  - 1. Add GET `/api/v1/audit/timeline` with `?projectId=&module=&actorId=&from=&to=&cursor=&limit=`, and GET `/api/v1/audit/records/:table/:id/events`. Both read as aip_app inside `withTenant`, from the `audit` stream only. The opaque cursor encodes `(occurred_at, seq)` and results are ordered by occurred_at desc, seq desc. limit is 1–100 (default 50). The response is `{items, nextCursor}`.
  - 2. Permission filter: the route needs `audit.activity.view`. Each item also needs view permission on its source. Batch by `source_module` and project: call `PolicyService.can(principal, '<module>.view', {projectId})` once per distinct (module, project) in the page. Drop items that are denied, and keep fetching until the page is full or the data is exhausted, with a cap of 5 internal fetches, then return a partial page plus a cursor. Never reveal a count of hidden items. `audit.log.read` (the full log) is not granted by tenant admin by default; it is checked here only to skip the per-item filter.
  - 3. Item DTO: `{id, seq, occurredAt, actor:{id, displayName}, eventType, summaryKey, summaryParams, recordRef:{table, id}, changes:[{field, before, after}], flags, reasonForChange, supersedesId}`. Changes are computed from payload before/after as a field-level diff. Actor display names come from the identity module's published API in one batched call. Superseded items carry `supersededById`, so the UI shows both entries and never hides the corrected one.
  - 4. Build ActivityTab.tsx as a reusable component taking `{recordRef}` or `{projectId}` and using the generated hooks. It renders a day-grouped list with actor, `t(summaryKey, params)`, relative and absolute time (tenant timezone), an expandable field diff, flag chips (on-behalf-of, force-unlock, override) and "Load more". Add filters for module, person and date range in the URL. Use DESIGN-04's EmptyState, LoadingState and ErrorState.
  - 5. Mount ActivityTab as the `history` tab of a project RecordDetail at `/projects/[projectId]/activity` (with header code, name and status from ProjectsApi via the client). If a project detail page already exists, add the tab there instead.
  - 6. Add term keys `audit.summary.project.created|updated|archived` and others with ICU params (for example `{actor} changed status from {from} to {to}`), plus the filter and flag labels.
  - 7. Regenerate the API client.
- **acceptance**:
  - A project member sees its activity, newest first, with field-level diffs. Stable cursors mean no duplicates or gaps while new events arrive.
  - Items whose source the viewer cannot view never appear, and their existence is not inferable from counts.
  - Tenant B can never read tenant A's events, even with a guessed id or cursor.
  - Corrections show both the original and the superseding entry, linked.
- **tests**:
  - **unit**:
    - The diff of `before:{name:'A', status:'draft'}` and `after:{name:'A', status:'active'}` is `[{field:'status', before:'draft', after:'active'}]`.
    - The cursor codec round-trips `{occurredAt:'2026-10-07T01:00:00.000001Z', seq:42}` and rejects garbage with 400 `INVALID_CURSOR`.
    - ActivityItem with flags `['override']` renders an Override chip with an icon and a label. A superseded item shows the "superseded" chip and a link to the replacement.
  - **integration** (Testcontainers, with AUDIT-02's writer):
    - Make 30 project.updated events on P1 and page with limit=10. Expected: 3 pages, no duplicates, strictly descending (occurred_at, seq). Insert a new event between page 1 and page 2. Expected: page 2 has no duplicates.
    - User U has `audit.activity.view` but not `inspections.view`. Seed 5 project events and 5 `inspections.*` events on P1. Expected: U sees 5 items and no total count.
    - As tenant B, GET `/audit/records/projects/<A's project id>/events`. Expected: 200 with an empty list (RLS), not an error that leaks existence.
    - Request without `audit.activity.view`. Expected: 403.
  - **e2e** (Playwright):
    - As the kaefer-demo admin, create project `E2E-ACT-<run>`, rename it, then open `/projects/<id>/activity`. Expected: two entries, "created" and "changed name from … to …". Expanding the second shows the name diff.
