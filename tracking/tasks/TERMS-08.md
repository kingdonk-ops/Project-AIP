# TERMS-08 — Frontend i18n provider and dictionary admin screen
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TERMS-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`packages/terms`, `packages/api-client`, Vite + TanStack Router, Vitest, Playwright), [0001](../../docs/adr/0001-greenfield-python-backend.md) (TS frontends; shared golden vectors)
4. Only if the step needs it: `architecture.md` / `data-model.md` / `routes.md` in the module folder

## Spec

Make the Vite web app read labels from the dictionary through a shared `packages/terms` provider, and add the admin override screen.

- **depends on**:
  - TERMS-05
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
  - 1. After sign-in, fetch the effective bundle (`{version, locale, messages}`) with the generated `packages/api-client` hook for the TERMS-05 bulk-resolve endpoint. Keep it in memory and in IndexedDB (`idb-keyval`, key `terms:{tenant}:{locale}`) for offline use; on start, render from IndexedDB first, then revalidate.
  - 2. Configure i18next with `i18next-icu` and expose `<TermsProvider>` and a `useT()` hook (plus a non-hook `t` for loaders). A missing key renders `⟦key⟧`, never the raw key or an empty string. The provider runs `packages/contracts/icu-vectors/icu-v1.json` in its tests so client and server formatting agree.
  - 3. Replace labels in the app shell nav and inspection status chips as the first conversion batch. DESIGN-02's `t.ts` re-exports `t` from `@aip/terms`, so call sites do not change.
  - 4. Build the dictionary page at `/settings/terms` (TanStack Router file route, search params `q`, `module`, `overridden` validated in `validateSearch`): a table with search (using `packages/ui` table primitives or DESIGN-03's RegisterTable if merged), an override side panel (level, locale, text with live ICU validation) and a where-used panel (surfaces from TERMS-05).
  - 5. Add a preview of the effective text on the UI, email and PDF surfaces (calls the TERMS-05 preview endpoint; no client-side template rendering).
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
