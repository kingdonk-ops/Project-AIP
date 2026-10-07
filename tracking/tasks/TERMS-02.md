# TERMS-02 — Resolver with fallback chain and cache invalidation

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TERMS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Resolve a key through default, market pack, tenant, client and project overrides.

- **depends on**:
  - TERMS-01
- **files**:
  - backend/app/modules/terms/resolver.py
  - backend/tests/terms/test_resolver.py
- **steps**:
  - 1. Implement resolve(key, locale, tenant, client=None, project=None), checking the most specific level first.
  - 2. Fall back from locale to the tenant default locale, then to en-AU.
  - 3. Cache per tenant in Redis under t:{tenant}:terms:{version}.
  - 4. Invalidate on the terms.pack.activated event and on override writes.
  - 5. Never return an internal code or raw key: on a total miss return a visible fallback and log it.
  - 6. Add bulk_resolve(keys) for UI bundles.
- **acceptance**:
  - Project beats client beats tenant beats market pack beats default.
  - The cache is invalidated on activation.
  - A missing key does not show a raw code.
- **tests**:
  - **e2e**:
    - Admin overrides 'Inspection' to 'Check' and the app shell label changes on reload.
  - **integration**:
    - Rio client override 'Hold Point' leaves Kaefer's tenant label unchanged for non-Rio projects.
    - Activate a pack: the next resolve returns the new text with no stale value.
    - Tenant B's override is never returned for tenant A.
  - **unit**:
    - With overrides at tenant and project, resolve returns the project text.
    - A missing locale falls back to en-AU.
