# TERMS-05 — Terms admin: API, permissions, i18n provider and dictionary admin screen

<!-- hand-edited: merged TERMS-08 (Part B) per board slim 2026-10-17 -->
<!-- hand-edited: permission codes use dots (ACCESS-01) -->

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | L |
| Depends on | TERMS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`packages/terms`, `packages/api-client`, Vite + TanStack Router), [0001](../../docs/adr/0001-greenfield-python-backend.md) (Python backend; TS frontends; shared golden vectors); plus any ADR naming this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` / `routes.md` in the module folder

> Part A (was TERMS-05) is the admin API and permissions; Part B (was TERMS-08) is the frontend i18n
> provider and dictionary admin screen that consumes it. Part B depended only on Part A, so they are one task.

## Part A — terms admin API and permissions (was TERMS-05)

Expose dictionary, override, pack and locale endpoints with catalogue permissions.

- **files**:
  - backend/app/modules/terms/router.py
  - backend/app/modules/terms/permissions.py
  - backend/tests/terms/test_router.py
- **steps**:
  - 1. Add GET /terms/keys with search, filters and effective text.
  - 2. PUT/DELETE /terms/overrides with level validation (market pack, tenant, client, project only if allowed by settings).
  - 3. Pack endpoints: import, dry-run, apply, rollback, export.
  - 4. GET/PUT /terms/locale-settings.
  - 5. Register permissions terms.view and terms.admin in the catalogue.
  - 6. Write an audit log entry for each change.
- **acceptance**:
  - A non-admin cannot override.
  - An override at a disallowed level returns 422.
  - Each override is audited with before and after.
- **tests**:
  - **e2e**:
    - Admin searches 'Hold point', overrides it, previews it on the email surface and saves.
  - **integration**:
    - Viewer PUT override returns 403.
    - Admin PUT override returns 200 and GET shows the effective text.
    - The audit_log has a row with old and new text.
    - Search 'punch' with an alias to 'defect' returns the defect keys.
  - **unit**:
    - Level validator rejects 'platform' from a tenant request.

## Part B — frontend i18n provider and dictionary admin screen (merged from TERMS-08)

Make the Vite web app read labels from the dictionary through a shared `packages/terms` provider, and add the admin override screen.

- **files**:
  - packages/terms/package.json
  - packages/terms/src/provider.tsx
  - packages/terms/src/useT.ts
  - packages/terms/src/bundle-cache.ts
  - packages/terms/src/index.ts
  - packages/terms/src/*.test.ts(x)
  - apps/web/src/features/settings/terms/DictionaryPage.tsx
  - apps/web/src/features/settings/terms/DictionaryPage.test.tsx
  - apps/web/src/routes/_app/settings/terms.tsx
  - apps/web/src/features/shell/t.ts (re-export `t` from `@aip/terms`)
- **steps**:
  - 1. After sign-in, fetch the effective bundle (`{version, locale, messages}`) with the generated `packages/api-client` hook for the Part A bulk-resolve endpoint. Keep it in memory and in IndexedDB (`idb-keyval`, key `terms:{tenant}:{locale}`) for offline use; on start, render from IndexedDB first, then revalidate.
  - 2. Configure i18next with `i18next-icu` and expose `<TermsProvider>` and a `useT()` hook (plus a non-hook `t` for loaders). A missing key renders `⟦key⟧`, never the raw key or an empty string. The provider runs `packages/contracts/icu-vectors/icu-v1.json` in its tests so client and server formatting agree.
  - 3. Replace labels in the app shell nav and inspection status chips as the first conversion batch. DESIGN-02's `t.ts` re-exports `t` from `@aip/terms`, so call sites do not change.
  - 4. Build the dictionary page at `/settings/terms` (TanStack Router file route, search params `q`, `module`, `overridden` validated in `validateSearch`): a table with search (using `packages/ui` table primitives or DESIGN-03's RegisterTable if merged), an override side panel (level, locale, text with live ICU validation), a where-used panel (surfaces from Part A), and a view of the coverage report (`GET /terms/coverage`, review 11 L27).
  - 5. Add a preview of the effective text on the UI, email and PDF surfaces (calls the Part A preview endpoint; no client-side template rendering).
  - 6. Invalidate the bundle when its `version` changes: refetch on window focus and after any override save, and on the `terms.pack.activated` server-sent event if the platform SSE channel exists.
- **acceptance**:
  - Shell and status labels come from the dictionary.
  - An override shows without a redeploy.
  - Offline, the last bundle is used.
  - No direct `fetch` in the feature; all calls go through `packages/api-client`.
- **tests**:
  - **e2e**:
    - Playwright (project `web`): the admin overrides `shell.nav.inspections` 'Inspection' to 'Check'; after reload the nav shows 'Check'; with `context.setOffline(true)` and a reload, the nav still shows 'Check'.
  - **integration**:
    - Vitest + Testing Library + MSW: DictionaryPage lists keys; saving an override sends `PUT /api/v1/terms/overrides` with the key, level and text, then refetches the bundle.
  - **unit**:
    - `useT()('inspection.status.completed')` returns the override text from the mocked bundle.
    - A missing key renders `⟦missing.key⟧`, not the raw key.
    - With the network mocked to fail and a bundle in IndexedDB (`fake-indexeddb`), the provider renders the cached text.
    - Every case in `icu-v1.json` formats to its `expected` value.
