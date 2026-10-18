# ASSETS-02 — Typed assets: pinned item-type version and attributes validated against the published schema

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`assets`](../../docs/blueprint/modules/assets/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ASSETS-01, ITEMTYPES-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`ASSETS-01.md`](ASSETS-01.md) (and its "As built") and [`ITEMTYPES-02.md`](ITEMTYPES-02.md) (the published `ItemTypesApi`)
3. [`docs/blueprint/modules/assets/README.md`](../../docs/blueprint/modules/assets/README.md); for columns only, [`data-model.md`](../../docs/blueprint/modules/assets/data-model.md) (`assets.item_type_id`, `item_type_version`, `attributes`)
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (JSONB attributes validated in the app), [0004](../../docs/adr/0004-repository-layout.md) (call item_types only through its `api.py`), [0036](../../docs/adr/0036-r1-module-decisions.md) (assets pin item-type versions; migration preview is not R1)

## Spec

Give assets a type: each asset may carry an item type, is pinned to the version of that type's schema that was published when it was typed, and stores JSONB attributes that the item_types module validates against that pinned version on every create and edit (tag: extend).

Out of scope: migrating existing assets to a newer schema with an impact preview (OPEN-QUESTIONS #39), parent/child type rules (modules, items, components), custom status sets (ITEMTYPES-05), reference attributes that point at assets, users or documents (ITEMTYPES-04), and the generated form (ASSETS-03).

- **files**:
  - apps/api/migrations/versions/<timestamp>_assets_item_types.py
  - apps/api/aip/modules/assets/manifest.toml
  - apps/api/aip/modules/assets/tables.py
  - apps/api/aip/modules/assets/schemas.py
  - apps/api/aip/modules/assets/repository.py
  - apps/api/aip/modules/assets/service.py
  - apps/api/aip/modules/assets/routes.py
  - apps/api/aip/modules/assets/api.py
  - apps/api/aip/modules/assets/tests/conftest.py
  - apps/api/aip/modules/assets/tests/test_unit.py
  - apps/api/aip/modules/assets/tests/test_assets_typed_db.py
  - apps/api/tests/isolation/overrides.toml
  - config/terms/en-AU/assets.json
  - db/schema.snapshot.sql
  - packages/api-client/openapi.json
  - packages/api-client/src/generated/
- **steps**:
  - 1. Migration `<timestamp>_assets_item_types.py` (raw SQL, forward-only) alters `assets`:
    - `ADD COLUMN item_type_id uuid NULL`, `ADD COLUMN item_type_version_id uuid NULL`,
      `ADD COLUMN attributes jsonb NOT NULL DEFAULT '{}'::jsonb`.
    - `ck_assets_item_type_pinned CHECK ((item_type_id IS NULL) = (item_type_version_id IS NULL))`;
      `ck_assets_attributes_object CHECK (jsonb_typeof(attributes) = 'object')`;
      `ck_assets_untyped_attributes CHECK (item_type_id IS NOT NULL OR attributes = '{}'::jsonb)`.
    - Foreign keys to the item_types tables created by ITEMTYPES-01/02: `item_type_id → item_types (id)` and
      `item_type_version_id → item_type_versions (id)`; if ITEMTYPES-01/02 added `(id, tenant_id)` unique
      constraints, reference `(…, tenant_id)` instead so an asset can never point at another tenant's type.
    - Indexes: `CREATE INDEX ix_assets_tenant_id_item_type_id ON assets (tenant_id, item_type_id)`;
      `CREATE INDEX ix_assets_attributes ON assets USING gin (attributes jsonb_path_ops)`.
    - Update the `[tables.assets]` isolation override if the new checks need seed values, and refresh
      `db/schema.snapshot.sql`.
  - 2. `schemas.py`: `AssetCreate` gains `itemTypeId: uuid | null` and `attributes: dict` (default `{}`);
    `AssetUpdate` gains `itemTypeId` and `attributes` (both optional); `AssetOut` gains `itemTypeId`,
    `itemTypeVersionId` and `attributes`. `itemTypeVersionId` is never accepted in a body (strict schema → 422):
    the server picks the version.
  - 3. Pinning (`service.py`, inside the operation's `with_tenant` transaction, through
    `aip.modules.item_types.api.ItemTypesApi` only):
    - Create with `itemTypeId`: `ItemTypesApi.get_published_version(conn, item_type_id)`; `None` (unknown type,
      another tenant's, archived, or no published version) → 422 `ITEM_TYPE_NOT_PUBLISHED` (field `itemTypeId`).
      Store the returned version's id in `item_type_version_id`.
    - Create without `itemTypeId` and with non-empty `attributes` → 422 `ATTRIBUTES_WITHOUT_TYPE`.
    - Update with `attributes` only: validate against the asset's **pinned** version, never the newest one.
    - Update with `itemTypeId` (the same type or another): re-pin to that type's current published version and
      validate the resulting attributes (the body's `attributes`, or the stored ones when absent) against it.
      Setting `itemTypeId: null` clears the type and requires `attributes` to be `{}` or absent (then stored `{}`).
  - 4. Validation: `ItemTypesApi.validate_attributes(conn, version_id, attributes)`; a non-empty list → 422
    `ATTRIBUTES_INVALID` with `errors: [{path, code}]` taken from each `AttributeValidationError` (the field path
    such as `attributes.diameter_mm` and a stable code such as `required` or `type`), nothing written. The
    service never reads item_types tables and never re-implements schema checks; `aip.platform.db.jsonb_schema`
    is reached only through `ItemTypesApi`.
  - 5. `AssetsApi.create_asset(conn, actor_id, data)` applies steps 3–4 (DATAIO-02 creates typed assets through
    it). `AssetsApi.get_asset` returns the new fields. Add `itemTypeId` as a list filter on `GET /api/v1/assets`
    (repeatable) and `itemTypeId`, `itemTypeVersionId` to the list items. Regenerate the OpenAPI client.
  - 6. Events stay v1: the new fields go inside `asset.created` `after` and `asset.updated` `before`/`after`
    (`itemTypeId`, `itemTypeVersionId`, `attributes` when changed). `aip.platform.events.registry.verify_released_schemas`
    must still pass unchanged.
  - 7. `manifest.toml`: add `"item_types"` to `depends_on`. Terms: `assets.field.item_type`,
    `assets.field.attributes`, `assets.error.ITEM_TYPE_NOT_PUBLISHED`, `assets.error.ATTRIBUTES_WITHOUT_TYPE`,
    `assets.error.ATTRIBUTES_INVALID`.
- **acceptance**:
  - A typed asset always has both `item_type_id` and `item_type_version_id`; an untyped asset has neither and `{}` attributes (enforced by the database, not only the service).
  - Attributes are validated against the pinned version on every create and edit; publishing a newer type version changes nothing on existing assets until an edit re-pins them explicitly with `itemTypeId`.
  - An invalid payload writes no `assets` change and no outbox row, and the 422 lists every failing field path.
  - The assets module reaches item types only through `ItemTypesApi`; no SQL in `assets` names an item_types table except the migration's foreign keys.
- **tests**:
  - **unit**:
    - `AssetCreate` with `{"name":"P-101","itemTypeVersionId":"…"}` → validation error (extra forbidden).
    - Mapping `[AttributeValidationError(path="diameter_mm", code="required")]` → response `errors: [{"path":"attributes.diameter_mm","code":"required"}]`.
    - `AssetCreate` with `{"name":"Folder","attributes":{"x":1}}` and no `itemTypeId` → the service raises `ATTRIBUTES_WITHOUT_TYPE` before any SQL (repository stubbed).
  - **integration**:
    - testcontainers-python Postgres, migrated, tenants `kaefer-demo` and `tenant-b`; item types are created through `ItemTypesApi` / the item_types routes from ITEMTYPES-01/02 (never by inserting into their tables). Fixture: item type `Pump` v1 published with `diameter_mm` (number, required) and `service` (dropdown: `water`, `steam`).
    - `POST /api/v1/assets {"name":"P-101","itemTypeId":<Pump>,"attributes":{"diameter_mm":150,"service":"steam"}}` → 201 with `itemTypeVersionId` = v1's id.
    - The same with `{"service":"oil"}` → 422 `ATTRIBUTES_INVALID` whose `errors` contain `attributes.diameter_mm` (`required`) and `attributes.service`; `SELECT count(*) FROM assets` and the `domain_events` count are unchanged.
    - Publish `Pump` v2 (adds required `material`). `PATCH P-101 {"syncVersion":1,"attributes":{"diameter_mm":200,"service":"steam"}}` → 200 and still pinned to v1. `PATCH {"syncVersion":2,"itemTypeId":<Pump>}` → 422 `ATTRIBUTES_INVALID` (`attributes.material`); with `attributes` including `material` → 200 pinned to v2, and the `asset.updated` row's `after` has the new `itemTypeVersionId`.
    - `itemTypeId` of a draft-only type → 422 `ITEM_TYPE_NOT_PUBLISHED`; of a `tenant-b` type → 422 `ITEM_TYPE_NOT_PUBLISHED`.
    - `POST {"name":"Area 1","attributes":{"x":1}}` → 422 `ATTRIBUTES_WITHOUT_TYPE`; as the table owner, `UPDATE assets SET attributes = '{"x":1}'` on an untyped row → violates `ck_assets_untyped_attributes`.
    - `PATCH {"syncVersion":3,"itemTypeId":null,"attributes":{}}` → 200 with all three fields cleared.
    - `GET /api/v1/assets?itemTypeId=<Pump>` → only the typed pumps; as `tenant-b` → 0 items.
    - `AssetsApi.create_asset(conn, actor_id, AssetCreate(name="P-102", item_type_id=<Pump>, attributes={...valid v2...}))` → pinned to v2, `created_by` = `actor_id`.
  - **e2e**:
    - API-only task: the Postgres integration tests above cover pinning, validation and tenant isolation through the real routes. The browser journey for typed create and edit ships with ASSETS-03.
