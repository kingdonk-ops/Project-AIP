# TERMS-02 — Resolver with fallback chain and cache invalidation
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0002](../../docs/adr/0002-data-access-and-migrations.md) (`with_tenant`), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox events, Redis for cache only), [0004](../../docs/adr/0004-repository-layout.md) (`aip/platform/terms`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Resolve a key through default, market pack, tenant, client and project overrides, with a per-tenant Redis cache invalidated on pack activation and override writes.

- **depends on**:
  - TERMS-01
- **files**:
  - apps/api/aip/modules/terms/repository.py
  - apps/api/aip/modules/terms/service.py (resolver)
  - apps/api/aip/modules/terms/events.py
  - apps/api/aip/modules/terms/api.py
  - apps/api/aip/platform/terms/__init__.py (the `TermResolver` Protocol and registration hook; no module imports)
  - apps/api/aip/modules/terms/tests/test_resolver.py
- **steps**:
  - 1. Implement `async resolve(conn, key, locale, *, tenant_id, client_id=None, project_id=None) -> str` in `service.py`, checking the most specific level first: project override, client override, tenant override, the tenant's active market pack version, then the platform default. Reads go through `repository.py` on the caller's `with_tenant` connection.
  - 2. Fall back from the requested locale to the tenant default locale (`locale_settings`), then to `en-AU`.
  - 3. Cache the tenant's merged map in Redis (`redis.asyncio`) under `t:{tenant}:terms:{version}`, where `version` is a per-tenant counter also kept in Redis. Client and project overrides are cached under the same version with their level suffix. Redis is a cache only: a Redis outage falls back to the database.
  - 4. Invalidate by bumping the version: subscribe to the outbox event `terms.pack.activated` (declared in `events.py`, dispatched by the ARCH-05/07 outbox), and bump after commit on every override write made through `service.py`.
  - 5. Never return an internal code or raw key. On a total miss return a visible fallback (`⟦key⟧`) and log a structured warning `terms.miss` with key, locale and tenant.
  - 6. Add `bulk_resolve(conn, keys | None, locale, ...) -> dict[str, str]` for UI bundles (all keys when `None`). Export `resolve` and `bulk_resolve` from `api.py`, and register the module's implementation with the `aip.platform.terms` `TermResolver` port at startup so platform code (emails, PDFs) can format text without importing a module.
- **acceptance**:
  - Project beats client beats tenant beats market pack beats default.
  - The cache is invalidated on activation.
  - A missing key does not show a raw code.
- **tests** (pytest; integration uses testcontainers-python Postgres and Redis):
  - **e2e**:
    - None here; TERMS-08 covers "admin overrides 'Inspection' to 'Check' and the shell label changes on reload".
  - **integration**:
    - A Rio client override of `itp.point_type.hold` ("Inspection stop") applies on a Rio project, while Kaefer's tenant label "Hold point" stays unchanged for non-Rio projects.
    - Activate a pack (insert a version and emit `terms.pack.activated` through the outbox, then run the dispatcher once). Expected: the next `resolve` returns the new text with no stale value.
    - Write a tenant override through `service.py`, then resolve. Expected: the new text, with no stale cache hit.
    - Tenant B's override is never returned for tenant A.
    - Stop the Redis container. Expected: `resolve` still returns the correct text from Postgres.
  - **unit**:
    - With overrides at tenant and project, `resolve` returns the project text.
    - A missing locale (`fr-FR`) with tenant default `en-AU` returns the en-AU text.
    - A key in no level returns `⟦ghost.key⟧` and logs `terms.miss`.
