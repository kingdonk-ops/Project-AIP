# ARCH-09 — Event catalogue and dead-letter admin pages

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-07, DESIGN-03, DESIGN-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/ui-layout.md`](../../docs/blueprint/modules/arch/ui-layout.md) (the "Domain event catalogue", "Event detail" and "Dead-letter queue" pages)
3. ADRs: [0029](../../docs/adr/0029-platform-admin-permissions-and-event-catalogue-reads.md) (operator permission, catalogue API), [0030](../../docs/adr/0030-outbox-dispatch-semantics.md) (dead-letter semantics, `last_error` is a summary only), [0004](../../docs/adr/0004-repository-layout.md) (Vite + TanStack Router, generated `packages/api-client`)

## Spec

Build the web pages for the APIs ARCH-06 and ARCH-07 shipped: the event catalogue, the event detail and the dead-letter queue, for platform operators holding `platform.events.manage`. No backend change is expected; if one is needed, add it as its own task.

- **depends on**:
  - ARCH-07 (dead-letter API), DESIGN-03 (`RegisterTable`), DESIGN-04 (dialogs, toasts, empty/loading/error states)
- **files**:
  - apps/web/src/routes/_app/admin/platform/events/index.tsx
  - apps/web/src/routes/_app/admin/platform/events/$eventName.tsx
  - apps/web/src/routes/_app/admin/platform/events/dead-letter.tsx
  - apps/web/src/features/platform-events/ (pages, columns, the discard dialog, nav entry)
  - apps/web/src/features/platform-events/__tests__/
  - e2e/web/platform-events.spec.ts
  - terminology keys for every label (no hard-coded strings)
- **steps**:
  - 1. **Catalogue** (`/admin/platform/events`, `GET /api/v1/admin/platform/events`): `RegisterTable` with columns event, version, owning module, status chip, subscribers, published 24h, failed 24h; filters module, status, version (URL state). A row opens the event detail.
  - 2. **Event detail** (`/admin/platform/events/:eventName`, `GET .../events/{eventName}`): one tab or section per version with its status, subscribers and the JSON Schema (read-only, monospace). "Deprecate" (`POST .../versions/{version}/deprecate`) asks for confirmation in a dialog and shows a toast; hidden when the version is already deprecated.
  - 3. **Dead-letter queue** (`/admin/platform/events/dead-letter`, `GET .../dead-letter`): columns event ID (mono, copyable), event and version, tenant, attempts, last error, dead-lettered at. Keyset paging with `limit`/`after`/`nextAfter` through `RegisterTable`'s cursor pagination. Row actions: Retry (`POST .../{id}/retry`) and Discard (`POST .../{id}/discard`) through a dialog whose reason field is required (trimmed, 1–1000 characters; the API returns 422 otherwise). On success, toast and refetch; a 404 means another operator already acted, so show that and refetch. Bulk "Retry selected" calls retry once per row and reports how many succeeded.
  - 4. Add the three pages to the nav rail's platform/admin section (ADR 0018 job-area menu), shown only when the user holds `platform.events.manage`. A direct visit without it shows the standard 403 state.
  - 5. Use the generated orval hooks from `packages/api-client` only; regenerate the client if it is stale.
- **out of scope** (separate tasks when wanted): replay range and replay jobs, "Register event" form, catalogue CSV export, recent-events panel, a payload drawer (the API never returns payloads; ADR 0030), a tenant-admin view of their own dead letters (needs a tenant-scoped API), the dead-letter summary strip.
- **acceptance**:
  - An operator can find an event, read its schema, deprecate a version, and retry or discard (with a reason) a dead letter, using the keyboard only.
  - A user without `platform.events.manage` sees none of the nav entries and gets a 403 state on direct visits; no admin API call succeeds for them.
  - axe reports no serious or critical violations on the three pages in empty, loading, error and populated states.
- **tests**:
  - **unit** (Vitest + Testing Library):
    - The discard dialog's submit is disabled for an empty or whitespace-only reason and enabled for "x".
    - A 404 from retry shows the "already handled" message and triggers a refetch.
    - Nav entries are hidden without `platform.events.manage`.
  - **e2e** (Playwright; desktop Chromium, mobile Chrome, iPad WebKit):
    - As the fixture operator: open the catalogue, filter by module, open an event and see its schema; deprecate a version and see the status chip change.
    - With a seeded dead letter: retry it and see it leave the list; discard another with a reason and see it leave the list.
    - As a plain `tenant-a` user and as a `tenant-b` user: the pages show the 403 state (cross-tenant check).
    - axe check on each page.
