# ASSETS-01 — Asset tree core: assets table (ltree path, internal tag, Tag Number), CRUD API and cycle-guarded move

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`assets`](../../docs/blueprint/modules/assets/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/assets/README.md`](../../docs/blueprint/modules/assets/README.md) and, for columns only, [`data-model.md`](../../docs/blueprint/modules/assets/data-model.md) (`assets`)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (Core + raw-SQL Alembic, `with_tenant`, ltree), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox in the same transaction), [0004](../../docs/adr/0004-repository-layout.md) (only `api.py` crosses modules), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0025](../../docs/adr/0025-time-and-timezones.md) (UTC storage), [0027](../../docs/adr/0027-default-role-permission-expansion.md) (how `asset.*` codes reach default roles), [0036](../../docs/adr/0036-r1-module-decisions.md) (assets start untyped; ltree stays)
4. The pattern to copy: [`PROJECTS-06.md`](PROJECTS-06.md) "As built", and the code in `apps/api/aip/modules/projects/` (`routes.py`, `service.py`, `repository.py`, `schemas.py`, `events.py`, `settings.py`, `tests/conftest.py`, `tests/test_projects_db.py`)

## Spec

Create the `assets` module with a tenant-owned asset tree on ltree: one table, a published interface other R1 modules build on, a CRUD API with an immutable internal tag and a conflict-checked Tag Number, and a move that re-parents a whole subtree in one transaction under a tenant-scoped lock and refuses cycles (tag: extend).

Out of scope: item type, version and attributes columns (ASSETS-02); the `/assets` page (ASSETS-03); bulk add and sibling reorder (ASSETS-04); asset-subtree scope predicates on reads (ASSETS-07: until then access is by permission and tenant only, and this task never reads `asset_path_scope`); open-item counts, criticality, status, GPS location and CUI fields (later rows, see the R1 board).

- **files**:
  - apps/api/migrations/versions/<timestamp>_assets_tree.py
  - apps/api/aip/modules/assets/__init__.py
  - apps/api/aip/modules/assets/manifest.toml
  - apps/api/aip/modules/assets/tables.py
  - apps/api/aip/modules/assets/schemas.py
  - apps/api/aip/modules/assets/repository.py
  - apps/api/aip/modules/assets/service.py
  - apps/api/aip/modules/assets/policies.py
  - apps/api/aip/modules/assets/events.py
  - apps/api/aip/modules/assets/settings.py
  - apps/api/aip/modules/assets/routes.py
  - apps/api/aip/modules/assets/api.py
  - apps/api/aip/modules/assets/jobs.py
  - apps/api/aip/modules/assets/tests/__init__.py
  - apps/api/aip/modules/assets/tests/conftest.py
  - apps/api/aip/modules/assets/tests/test_unit.py
  - apps/api/aip/modules/assets/tests/test_smoke.py
  - apps/api/aip/modules/assets/tests/test_assets_db.py
  - apps/api/aip/platform/http/cursor.py
  - apps/api/aip/platform/http/tests/test_cursor.py
  - apps/api/tests/isolation/overrides.toml
  - config/terms/en-AU/assets.json
  - db/schema.snapshot.sql
  - docs/architecture/module-map.md
  - infra/docker-compose.yml
  - infra/coolify/docker-compose.coolify.yml
  - infra/coolify/env.example
  - tools/tests/test_coolify.py
  - packages/api-client/openapi.json
  - packages/api-client/src/generated/
  - packages/contracts/src/permissions.generated.ts
- **steps**:
  - 1. Scaffold with `python tools/new_module.py assets`. `manifest.toml`: `id = "assets"`, `depends_on = ["tenancy"]`,
    `permission_namespaces = ["asset"]`, `settings = ["ASSETS_CURSOR_KEY"]`, permissions `asset.view`, `asset.create`,
    `asset.update`, `asset.move`, `asset.delete`, and `[[events]]` `asset.created` v1, `asset.updated` v1,
    `asset.moved` v1, `asset.deleted` v1. Regenerate `packages/contracts/src/permissions.generated.ts` with
    `tools/gen_permissions.py` and the module map with `tools/gen_module_map.py`.
    - ADR 0027 expands levels by verb: `view`, `create`, `update` and `delete` follow the access matrix's `assets`
      row; `move` is not in `LEVEL_VERBS`, so default roles get `asset.move` at `admin` only (fail closed). Do not
      change `aip.modules.access`; record the gap in "As built" for an access follow-up.
  - 2. Migration `<timestamp>_assets_tree.py` (raw SQL, forward-only, `render_template("tenant_table", table="assets", sync=True, columns=...)`
    so the table gets `client_generated_id` and `sync_version`). Create `assets` with:
    - `parent_id uuid NULL`, `path ltree NOT NULL`, `internal_tag text NOT NULL`, `tag_number text NULL`,
      `name text NOT NULL`, `sort_order integer NOT NULL DEFAULT 0`, `created_by uuid NULL`.
    - Constraints: `uq_assets_id_tenant_id UNIQUE (id, tenant_id)` (so later modules can reference
      `(asset_id, tenant_id)`); `fk_assets_parent` `FOREIGN KEY (parent_id, tenant_id) REFERENCES assets (id, tenant_id)`;
      `ck_assets_name CHECK (btrim(name) <> '' AND length(name) <= 200)`;
      `ck_assets_tag_number CHECK (tag_number IS NULL OR (btrim(tag_number) = tag_number AND tag_number <> '' AND length(tag_number) <= 64))`;
      `ck_assets_path_leaf CHECK (ltree2text(subpath(path, nlevel(path) - 1)) = replace(id::text, '-', ''))`
      (the last label is the node's own id); `ck_assets_root CHECK ((parent_id IS NULL) = (nlevel(path) = 1))`;
      `ck_assets_depth CHECK (nlevel(path) <= 15)`.
    - Indexes: `CREATE INDEX ix_assets_path_gist ON assets USING gist (path)`;
      `CREATE UNIQUE INDEX uq_assets_tenant_id_path ON assets (tenant_id, path)`;
      `CREATE UNIQUE INDEX uq_assets_tenant_id_internal_tag ON assets (tenant_id, internal_tag)`;
      `CREATE UNIQUE INDEX uq_assets_tenant_id_upper_tag_number ON assets (tenant_id, upper(tag_number)) WHERE deleted_at IS NULL AND tag_number IS NOT NULL`;
      `CREATE INDEX ix_assets_tenant_id_parent_id_sort_order ON assets (tenant_id, parent_id, sort_order)`;
      a `pg_trgm` GIN index on `name` for the `q` search.
    - A `BEFORE UPDATE` trigger `assets_internal_tag_immutable` raising `internal_tag is immutable` when
      `NEW.internal_tag IS DISTINCT FROM OLD.internal_tag`.
    - `REVOKE DELETE ON assets FROM aip_app` (soft delete only). Add the `[tables.assets]` entry to
      `apps/api/tests/isolation/overrides.toml` (the generic seed cannot satisfy `ck_assets_path_leaf`; seed
      root rows with `path` derived from `id`) and refresh `db/schema.snapshot.sql`.
  - 3. `tables.py` (SQLAlchemy Core `Table` for `assets`; `path` as a text-typed column read with `::text`).
    `repository.py` holds every SQL statement; ltree work goes through `aip.platform.db.ltree`
    (`descendants`, `ancestors`, `move_subtree`). Path labels are the asset id's 32 hex digits, so
    `path = parent.path || label` and `ck_assets_path_leaf` holds by construction.
  - 4. Internal tag (`policies.py`, pure): `internal_tag(asset_id) = "AT-" + Crockford base32 of the id's low 60 bits`,
    grouped `XXXX-XXXX-XXXX` (UUIDv7 low bits are random, so tags are unique in practice; the unique index is the
    guard, and a collision regenerates the id once, then fails 500). Tag Number normalisation: trim, collapse inner
    whitespace to one space, empty → `null`; comparisons are case-insensitive (`upper`).
  - 5. Tree lock: every write that reads a parent's path (create with a parent, move, delete) first runs
    `SELECT pg_advisory_xact_lock(hashtextextended(current_setting('app.tenant_id') || ':assets.tree', 0))`
    (the pattern in `aip.modules.approvals.repository`). Plain renames and Tag Number edits do not take it.
  - 6. `service.py` (one `with_tenant(get_context())` transaction per operation; ids from the platform UUIDv7
    generator; errors as `aip.platform.http.DomainError`):
    - (a) `create(data)`: `AssetCreate {name, parentId?, tagNumber?, clientGeneratedId?}` (strict, unknown keys → 422).
      A parent that is missing, soft-deleted or another tenant's → 422 `PARENT_NOT_FOUND` (field `parentId`). New
      depth > 15 → 422 `ASSET_TREE_TOO_DEEP`. `sort_order` = max live sibling `sort_order` + 1. A Tag Number used by a
      live asset → 409 `TAG_NUMBER_IN_USE` with `{assetId, internalTag}` of the holder. With `clientGeneratedId`
      the insert uses `aip.platform.db.idempotency.create_idempotent`: a replay returns the first row with 200
      and emits nothing. Emit `asset.created` v1.
    - (b) `update(asset_id, AssetUpdate {syncVersion, name?, tagNumber?})` through
      `aip.platform.db.concurrency.update_with_version` (stale version → 409 `VERSION_CONFLICT` with `current`);
      Tag Number conflict → 409 `TAG_NUMBER_IN_USE`. `internalTag`, `path`, `parentId` in the body → 422 (strict
      schema). Emit `asset.updated` v1 with only the changed fields in `before`/`after`; a no-change PATCH emits nothing.
    - (c) `move(asset_id, AssetMove {syncVersion, parentId: uuid | null})`: take the tree lock; load the node
      (404 if missing or another tenant's); load the new parent (422 `PARENT_NOT_FOUND`); same parent → 200 with
      the row unchanged and no event; otherwise check that the deepest descendant's new depth ≤ 15 (422
      `ASSET_TREE_TOO_DEEP`), call `update_with_version` with `{parent_id, sort_order: max sibling + 1}`, then
      `aip.platform.db.ltree.move_subtree(conn, assets, node.path, parent.path or None)`. `CycleError` (new parent is
      the node or below it) is rendered by the platform as 422 `PATH_CYCLE` and nothing is written. Emit
      `asset.moved` v1 `{assetId, fromParentId, toParentId, fromPath, toPath, movedCount}`.
    - (d) `delete(asset_id, syncVersion)`: take the tree lock; a node with live children → 409
      `ASSET_HAS_CHILDREN` `{childCount}`; otherwise soft delete (`deleted_at`, `sync_version + 1`) and emit
      `asset.deleted` v1 `{assetId, internalTag, tagNumber, reason: null}`. The Tag Number is free again at once.
    - (e) `get(asset_id)` → `AssetOut` plus `ancestors: [{id, name, internalTag, tagNumber}]` root first (from
      `ltree.ancestors`) and `childCount`.
    - (f) `list(...)`: keyset paging with the cursor codec of step 8; filters `parentId` (children of that node;
      the literal `root` for roots), `under` (the strict subtree of an asset id, via `path <@`), `q` (name, Tag
      Number or internal tag, case-insensitive substring), `tagNumber` (exact, case-insensitive); `sort` one of
      `position` (`sort_order, name, id`; the default when `parentId` is given), `name`, `tagNumber`, `updatedAt`,
      each with `-` for descending. Every item carries `childCount` (live children). `limit` 1–200, default 50.
  - 7. `events.py`: one Pydantic payload `AssetEvent {assetId, internalTag, tagNumber, parentId, before, after}`
    (camelCase, `extra="forbid"`, `before`/`after` are `dict | None`, so ASSETS-02 can add attribute fields
    without changing the released v1 schema) for `asset.created`, `asset.updated`, `asset.deleted`, and
    `AssetMovedEvent` for `asset.moved`, registered with `aip.platform.events.register_event`. Emit through
    `aip.platform.events.emit(conn, name, 1, Aggregate("asset", id), payload, asset_id=id)` in the same transaction.
  - 8. Cursor: copy `CursorCodec` / `InvalidCursorError` from `aip.modules.projects.cursor` into
    `aip.platform.http.cursor` unchanged in behaviour (projects keeps its own copy; switching it is a projects
    follow-up). `settings.py` reads `ASSETS_CURSOR_KEY` exactly like `aip.modules.projects.settings` (dev key refused
    outside development and test, checked in the router lifespan); add it to `infra/docker-compose.yml`,
    `infra/coolify/docker-compose.coolify.yml`, `infra/coolify/env.example`, the root env example and the list in
    `tools/tests/test_coolify.py`.
  - 9. `routes.py`, mounted under `/api/v1/assets`, explicit `operation_id`s, every route with `requires(...)`
    and `require_active_tenant` (deny by default):
    - `GET /assets` (`assets_list`, `asset.view`)
    - `GET /assets/{asset_id}` (`assets_get`, `asset.view`)
    - `POST /assets` (`assets_create`, `asset.create`) → 201, or 200 on an idempotent replay
    - `PATCH /assets/{asset_id}` (`assets_update`, `asset.update`)
    - `POST /assets/{asset_id}/move` (`assets_move`, `asset.move`)
    - `DELETE /assets/{asset_id}?syncVersion=N` (`assets_delete`, `asset.delete`) → 204
    Regenerate `packages/api-client/openapi.json` and the generated client.
  - 10. `api.py` (`AssetsApi`, the only file other modules import; every method takes the caller's `with_tenant`
    connection so RLS applies and the work joins the caller's transaction):
    - `get_asset(conn, asset_id) -> AssetOut | None`; `assert_asset_exists(conn, asset_id)` (raises `NotFoundError`).
    - `create_asset(conn, actor_id, data: AssetCreate) -> AssetOut` (same rules and event as step 6a; stores
      `actor_id` in `created_by`; used by DATAIO-02).
    - `find_by_tag_number(conn, tag_number) -> AssetOut | None` (live assets, case-insensitive, after normalisation).
    - `subtree_ids(conn, asset_id) -> list[UUID]` (the node and its live descendants, by path).
    - `soft_delete_assets(conn, asset_ids, *, reason: str) -> int`: takes the tree lock, deletes deepest first,
      refuses with `DomainError(409, "ASSET_HAS_CHILDREN")` if any listed asset has a live child that is not listed,
      emits one `asset.deleted` v1 per asset with `reason` (used by the DATAIO-02 batch rollback).
  - 11. Terms in `config/terms/en-AU/assets.json`: `assets.nav.title`, `assets.field.name`, `assets.field.tag_number`,
    `assets.field.internal_tag`, `assets.field.parent`, and one `assets.error.<code>` per error code above.
    `create_asset` and the routes return codes only, never English text.
- **acceptance**:
  - `assets` exists with FORCE RLS and the fail-closed policy; `aip_app` cannot `DELETE`; the generated
    isolation suite covers it.
  - Every write commits exactly one `domain_events` row per changed asset in the same transaction, or none.
  - A move re-parents the whole subtree in one statement under the tenant tree lock; a cycle, an unknown parent or
    a too-deep result writes nothing.
  - `internal_tag` never changes after insert; Tag Numbers are unique among live assets per tenant, ignoring case.
  - Another tenant's asset id answers 404 on every route; RLS and the API agree.
  - `AssetsApi` exposes exactly the methods in step 10, and the OpenAPI client regenerates without drift.
- **tests**:
  - **unit**:
    - `internal_tag(UUID("0192f3c4-5e6f-7abc-8def-0123456789ab"))` → a string matching `^AT-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$`; the same id twice → the same tag.
    - Tag Number normalisation: `"  P-101 "` → `"P-101"`; `"P  101"` → `"P 101"`; `"   "` → `None`.
    - `AssetCreate` with `{"name":"Pump","internalTag":"X"}` → validation error on `internalTag` (extra forbidden).
    - `AssetEvent` round-trip: `{assetId, internalTag, tagNumber: null, parentId: null, before: null, after: {"name":"Site A"}}` serialises with camelCase keys.
    - `aip.platform.http.cursor.CursorCodec`: a cursor with one byte changed → `InvalidCursorError`.
  - **integration**:
    - These run with testcontainers-python Postgres, migrated, and the TESTING-01 tenants `kaefer-demo` and `tenant-b`; permissions come from a test grant provider as in `projects/tests/conftest.py`.
    - Build `Site A > Unit 1 > Pump P-101` with `POST /api/v1/assets` → three 201s; `Pump`'s `path` has 3 labels ending in its own id hex; `SELECT count(*) FROM domain_events WHERE event_name = 'asset.created'` → 3.
    - `GET /api/v1/assets?parentId=root` → 1 item (`Site A`, `childCount: 1`); `GET /api/v1/assets?under=<Site A id>` → 2 items.
    - `POST` a second asset with `tagNumber: "p-101"` → 409 `TAG_NUMBER_IN_USE` with the first asset's `assetId`; after the first is deleted, the same POST → 201.
    - `PATCH` `Pump` with `{"syncVersion":1,"internalTag":"AT-0000-0000-0000"}` → 422; as the table owner, `UPDATE assets SET internal_tag = 'x'` → error `internal_tag is immutable`.
    - Move `Unit 1` (with `Pump`) under a new root `Site B` → 200, `movedCount: 2`; both rows' paths start with `Site B`'s label; `parent_id` of `Unit 1` = `Site B`; 1 `asset.moved` row.
    - Move `Site B` under `Pump` (its own descendant) → 422 `PATH_CYCLE`; the paths of all rows and the `domain_events` count are unchanged.
    - Move with `parentId` of a `tenant-b` asset → 422 `PARENT_NOT_FOUND`; move with a stale `syncVersion` → 409 `VERSION_CONFLICT`.
    - A chain of 15 levels: creating a 16th child → 422 `ASSET_TREE_TOO_DEEP`; moving a 2-level subtree under the 14th level → 422 `ASSET_TREE_TOO_DEEP`.
    - Two concurrent moves (`asyncio.gather`) of `A` under `B` and `B` under `A` → one 200 and one 422 `PATH_CYCLE`; no row's path contains its own label twice.
    - `DELETE` `Site B` while `Unit 1` is live → 409 `ASSET_HAS_CHILDREN` `{childCount: 1}`; as `aip_app`, `DELETE FROM assets` → `permission denied`.
    - `AssetsApi.soft_delete_assets(conn, [Unit 1, Pump], reason="import rollback")` → 2, and 2 `asset.deleted` rows carry `reason: "import rollback"`; `[Unit 1]` alone while `Pump` is live → `ASSET_HAS_CHILDREN`.
    - `POST` with `clientGeneratedId` twice → 201 then 200 with the same `id`; 1 `asset.created` row.
    - A forced failure in `emit` (test hook) during create → 500, and `SELECT count(*) FROM assets` is unchanged.
    - A `tenant-b` user: `GET /api/v1/assets/<kaefer asset id>` → 404, `PATCH` → 404, `POST .../move` → 404, list → 0 items.
    - Each route without its permission → 403 and nothing written (one parametrised test over the six routes).
    - Paging: 120 roots, `limit=50`, `sort=name` → 3 pages (50, 50, 20) with no duplicates; `sort=-name` the reverse; a tampered cursor → 422.
  - **e2e**:
    - API-only task: the Postgres integration tests above cover every route, tenant isolation and the outbox. The first browser journey (create, view in the tree, cross-tenant 404, axe) ships with ASSETS-03.
