# TERMS-08 — Frontend i18n provider and dictionary admin screen

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Make the UI read labels from the dictionary and add the admin override screen.

- **depends on**:
  - TERMS-05
- **files**:
  - frontend/src/lib/i18n/provider.tsx
  - frontend/src/lib/i18n/useT.ts
  - frontend/src/features/settings/terms/DictionaryPage.tsx
  - frontend/src/features/settings/terms/DictionaryPage.test.tsx
- **steps**:
  - 1. Fetch the effective bundle with bulk_resolve at login, and cache it in memory and IndexedDB for offline use.
  - 2. Configure i18next with ICU and a useT() hook.
  - 3. Replace labels in the app shell nav and inspection status chips as the first conversion batch.
  - 4. Build the dictionary table with search, an override blade and a where-used panel.
  - 5. Add a preview of the effective text on the UI, email and PDF surfaces.
  - 6. Invalidate the bundle on the pack-activated event.
- **acceptance**:
  - Shell and status labels come from the dictionary.
  - An override shows without a redeploy.
  - Offline, the last bundle is used.
- **tests**:
  - **e2e**:
    - Playwright: the admin overrides 'Inspection' to 'Check'; after reload the nav shows 'Check'; the offline context still shows 'Check'.
  - **integration**:
    - Vitest: DictionaryPage lists keys, saving an override calls PUT /terms/overrides with the key, level and text.
  - **unit**:
    - useT('inspection.status.approved') returns the override text from the mocked bundle.
    - Missing key renders the fallback text, not the raw key.
