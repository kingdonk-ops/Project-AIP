# ITEMTYPES-01 — Content types, item categories and item types with the shared field-type registry

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`item_types`](../../docs/blueprint/modules/item_types/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/item_types/README.md`](../../docs/blueprint/modules/item_types/README.md) and, for columns only, [`data-model.md`](../../docs/blueprint/modules/item_types/data-model.md) (`content_types`, `item_categories`, `item_types`)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (names), [0002](../../docs/adr/0002-data-access-and-migrations.md) (Core + raw-SQL Alembic, `with_tenant`), [0004](../../docs/adr/0004-repository-layout.md) (only `api.py` crosses modules), [0027](../../docs/adr/0027-default-role-permission-expansion.md) (permission verbs), [0036](../../docs/adr/0036-r1-module-decisions.md) (choice 3: one field-type registry)
4. The pattern to copy: the projects module (its routes, service, repository and tests) and its migration revision `202610131300` (`projects_sites`)

## Spec

Create the `item_types` module with tenant-scoped content types, item categories and item types, and the one field-type registry that item-type attributes and form fields both use, published to Python callers and as a JSON contract for TypeScript (tag: extend).

Out of scope here: schema versions and attribute validation (ITEMTYPES-02); admin pages (ITEMTYPES-03); expiry flags and scoped references (ITEMTYPES-04); status sets (ITEMTYPES-05, blocked on OPEN-QUESTIONS #40); starter packs (ITEMTYPES-06, blocked on #41); inheritance (`parent_type_id`, OPEN-QUESTIONS #38, after R1); `auto_create_itp`/`auto_create_inspection` and default templates (no R1 row); the shared attributes registry (no R1 row).

- **files**:
  - apps/api/migrations/versions/<timestamp>_item_types_core.py
  - apps/api/aip/modules/item_types/__init__.py
  - apps/api/aip/modules/item_types/manifest.toml
  - apps/api/aip/modules/item_types/field_types.py
  - apps/api/aip/modules/item_types/tables.py
  - apps/api/aip/modules/item_types/schemas.py
  - apps/api/aip/modules/item_types/repository.py
  - apps/api/aip/modules/item_types/service.py
  - apps/api/aip/modules/item_types/policies.py
  - apps/api/aip/modules/item_types/routes.py
  - apps/api/aip/modules/item_types/api.py
  - apps/api/aip/modules/item_types/tests/conftest.py
  - apps/api/aip/modules/item_types/tests/test_field_types.py
  - apps/api/aip/modules/item_types/tests/test_item_types_db.py
  - tools/codegen/export_field_types.py
  - packages/contracts/field-types/field-types.json
  - packages/contracts/package.json (export `./field-types`)
  - packages/api-client/openapi.json (regenerated)
  - config/terms/en-AU/item_types.json
- **steps**:
  - 1. Scaffold with `python tools/new_module.py item_types`. In `manifest.toml` set `permission_namespaces = ["item_type"]`, `depends_on = ["tenancy"]`, and declare (ADR 0027 verbs, so the default roles get them at the access-matrix levels: view → view, edit → edit, admin → manage):
    - `item_type.view` — read content types, categories, item types and the field-type registry
    - `item_type.edit` — create, edit and delete item categories and item types
    - `item_type.manage` — create, edit, reorder and delete content types

    List the term keys in `term_keys`. Existing tenants' default roles pick the new codes up on the next `aip-access seed-roles` run (ADR 0027 §5).
  - 2. `field_types.py`: a frozen `FieldType` dataclass `{key, term_key, usable_in: frozenset[{"attribute","form"}], config_schema: dict, value_schema: Callable[[dict], dict]}` and `field_types() -> tuple[FieldType, ...]` in this order, with `get_field_type(key) -> FieldType | None`:

    | key | usable in | config (all optional unless marked) | `value_schema(config)` |
    |---|---|---|---|
    | `text` | attribute, form | `maxLength` (1–10000, default 2000) | `{"type":"string","maxLength":n}` |
    | `number` | attribute, form | `min`, `max` (integers) | `{"type":"integer"}` + `minimum`/`maximum` |
    | `decimal` | attribute, form | `min`, `max`, `decimals` (0–6, display only) | `{"type":"number"}` + `minimum`/`maximum` |
    | `date` | attribute, form | — | `{"type":"string","format":"date"}` |
    | `dropdown` | attribute, form | `options` **required**: 1–200 `{value, label}`, unique `value` | `{"type":"string","enum":[values]}` |
    | `multi_select` | attribute, form | `options` **required** as above | `{"type":"array","items":{"enum":[values]},"uniqueItems":true}` |
    | `measurement` | attribute, form | `unit` **required**, `min`, `max` | `{"type":"number"}` + `minimum`/`maximum` |
    | `boolean` | attribute, form | — | `{"type":"boolean"}` |
    | `photo` | form | `maxCount` (1–20, default 1) | `{"type":"array","items":{"type":"string","format":"uuid"},"maxItems":n}` |
    | `signature` | form | — | `{"type":"string","format":"uuid"}` |
    | `asset_ref` | attribute, form | — (scopes arrive with ITEMTYPES-04) | `{"type":"string","format":"uuid"}` |
    | `user_ref` | attribute, form | — (scopes arrive with ITEMTYPES-04) | `{"type":"string","format":"uuid"}` |

    - `config_schema` is a Draft 2020-12 JSON Schema of the allowed config keys with `additionalProperties: false`.
    - A `measurement` unit is a storage (SI) unit from the TERMS-03 contract `packages/contracts/unit-vectors/units-v1.json`: an entry whose `si` equals its key (`mm`, `bar`, `degC` today). Values are stored in that unit; display conversion is `aip.modules.terms.api.to_display` at presentation.
    - `photo` and `signature` values are uploads file ids; they are form-only in R1 because asset attributes do not hold files.
    - The labels are term keys `item_types.field_type.<key>` with en-AU defaults in `config/terms/en-AU/item_types.json`; no English in Python.
  - 3. `tools/codegen/export_field_types.py` writes `packages/contracts/field-types/field-types.json` as `{"version": 1, "fieldTypes": [{key, termKey, usableIn, configSchema}]}` (sorted keys, 2-space indent, trailing newline). Add `"./field-types": "./field-types/field-types.json"` to the `@aip/contracts` exports. A test fails when the committed file differs from the generator output.
  - 4. Migration `<timestamp>_item_types_core.py` (raw SQL, `render_template("tenant_table", ...)` for each table, forward-only like the `projects_sites` revision):
    - create `content_types` with `key text NOT NULL, name text NOT NULL, icon text NOT NULL DEFAULT 'folder', sort_order integer NOT NULL DEFAULT 0, show_in_nav boolean NOT NULL DEFAULT true, is_system boolean NOT NULL DEFAULT false, sync_version integer NOT NULL DEFAULT 1`; `CHECK (key ~ '^[a-z][a-z0-9_]{0,62}$')`, `CHECK (name <> '')`, `CHECK (icon ~ '^[a-z][a-z0-9-]{0,39}$')` (an `IconName` from `@aip/ui`; the web falls back to `folder` for a name it does not know), `UNIQUE (id, tenant_id)`, unique index `(tenant_id, key) WHERE deleted_at IS NULL`.
    - create `item_categories` with `content_type_id uuid NOT NULL, key text NOT NULL, name text NOT NULL, applicable_for text NOT NULL DEFAULT 'any', sort_order integer NOT NULL DEFAULT 0, sync_version integer NOT NULL DEFAULT 1`; `CHECK (applicable_for IN ('any','item','module'))`, the same key and name checks, FK `(content_type_id, tenant_id) REFERENCES content_types (id, tenant_id)`, `UNIQUE (id, tenant_id)`, unique index `(tenant_id, content_type_id, key) WHERE deleted_at IS NULL`, index `(tenant_id, content_type_id, sort_order)`.
    - create `item_types` with `category_id uuid NOT NULL, key text NOT NULL, name text NOT NULL, description text NULL, is_component boolean NOT NULL DEFAULT false, allows_components boolean NOT NULL DEFAULT false, sync_version integer NOT NULL DEFAULT 1`; the key and name checks, FK `(category_id, tenant_id) REFERENCES item_categories (id, tenant_id)`, `UNIQUE (id, tenant_id)` (ITEMTYPES-02 and ASSETS-02 reference it), unique index `(tenant_id, key) WHERE deleted_at IS NULL`, index `(tenant_id, category_id)`.
    - Each table gets the template's FORCE RLS fail-closed policy and grants; `REVOKE DELETE ... FROM aip_app` (deletes are soft).
  - 5. `tables.py` (SQLAlchemy Core `Table`s matching the migration), `repository.py` (all SQL; ids are UUIDv7 from the app), `schemas.py` (Pydantic, camelCase JSON, `extra="forbid"`), `service.py` (each operation in one `aip.platform.db.with_tenant` transaction).
    - Updates go through `aip.platform.db.concurrency.update_with_version` with the client's `syncVersion`; a stale version → 409 `VERSION_CONFLICT` with `current`.
    - Duplicate live key → 409 `CONTENT_TYPE_KEY_TAKEN` / `CATEGORY_KEY_TAKEN` / `ITEM_TYPE_KEY_TAKEN` (`DomainError`).
    - Keys are immutable after create (a PATCH with `key` → 422).
    - Delete only if unused: a content type with live categories → 409 `CONTENT_TYPE_IN_USE` with `{categories: n}`; a category with live item types → 409 `CATEGORY_IN_USE` with `{itemTypes: n}`. `is_system` content types → 409 `CONTENT_TYPE_SYSTEM`. ITEMTYPES-02 adds the item-type rule (published versions).
    - Caps (config lists are small and returned whole): 50 live content types per tenant, 200 categories per content type, 1000 item types per tenant; above → 409 `LIMIT_REACHED` with `{limit}`.
    - An item type's category must be live in the caller's tenant (another tenant's id → 404 `NOT_FOUND`, same as a missing one).
  - 6. `routes.py` under `/api/v1`, every route with `requires(...)` (deny by default) and `require_active_tenant`, explicit `operation_id`s (`item_types_*`):
    - `GET /field-types` (`item_type.view`) → the registry as in the JSON contract.
    - `GET /content-types` (`item_type.view`) → `{items}` ordered by `sort_order, key`, each with `itemTypeCount`; filter `showInNav`. `GET /content-types/{id}`; `POST` and `PATCH /content-types/{id}` and `DELETE` (`item_type.manage`); `PUT /content-types/order {ids: [...]}` (`item_type.manage`) sets `sort_order` 10, 20, 30… in the given order and requires exactly the tenant's live ids (else 422 `ORDER_MISMATCH`).
    - `GET /item-categories?contentTypeId=` (`item_type.view`), `GET /item-categories/{id}`; `POST`, `PATCH`, `DELETE` (`item_type.edit`).
    - `GET /item-types?contentTypeId=&categoryId=&q=` (`item_type.view`, `q` matches key or name, case-insensitive) → `{items}` with `contentTypeId` resolved through the category; `GET /item-types/{id}`; `POST`, `PATCH`, `DELETE` (`item_type.edit`).
  - 7. `api.py`: `field_types()`, `get_field_type(key)`, and `ItemTypesApi` with `get_item_type(conn, item_type_id) -> ItemTypeOut | None` and `assert_item_type_exists(conn, item_type_id)` (raises `NotFoundError`). Other modules import only this file. Regenerate `packages/api-client/openapi.json` (`tools/codegen/export_openapi.py`).
- **acceptance**:
  - `field_types()` returns the 12 keys in the order above, and `packages/contracts/field-types/field-types.json` matches the generator byte for byte.
  - A tenant admin can create a content type, a category under it and an item type under that category through the API; each read returns the same values, and a second tenant sees none of them.
  - Deleting a content type or category that is still used is refused with 409 and nothing changes.
  - No route answers without its permission (route check in `aip.platform.access.route_check` passes); every label is a term key.
- **tests**:
  - **unit** (`test_field_types.py`):
    - `[f.key for f in field_types()]` → `["text","number","decimal","date","dropdown","multi_select","measurement","boolean","photo","signature","asset_ref","user_ref"]`.
    - `get_field_type("dropdown").value_schema({"options":[{"value":"cs","label":"Carbon steel"},{"value":"ss","label":"Stainless"}]})` → `{"type":"string","enum":["cs","ss"]}`.
    - `get_field_type("measurement").value_schema({"unit":"mm","min":0,"max":50})` → `{"type":"number","minimum":0,"maximum":50}`.
    - `get_field_type("number").value_schema({})` → `{"type":"integer"}`; `get_field_type("gps")` → `None`.
    - Draft 2020-12 check of each `config_schema`: `measurement` config `{"unit":"furlong"}` → invalid (unit not in the SI list); `{"unit":"in"}` → invalid (`in` is a display unit); `{"unit":"mm"}` → valid; `dropdown` config `{}` → invalid (`options` required); `text` config `{"colour":"red"}` → invalid (additional property).
    - `"photo" in [f.key for f in field_types() if "attribute" in f.usable_in]` → `False`.
    - Running `export_field_types.py` into a temp dir and comparing with the committed `packages/contracts/field-types/field-types.json` → identical.
  - **integration** (`test_item_types_db.py`, pytest + testcontainers-python Postgres, the TESTING-01 tenants `kaefer-demo` (A) and `tenant-b` (B), a test grant provider, as the projects tests use):
    - A admin `POST /api/v1/content-types {"key":"asset","name":"Asset","icon":"folder"}` → 201 with `syncVersion: 1`, `isSystem: false`. Repeat with key `asset` → 409 `CONTENT_TYPE_KEY_TAKEN`. Key `Asset Type` → 422.
    - `POST /api/v1/item-categories {"contentTypeId":<asset>,"key":"piping","name":"Piping","applicableFor":"item"}` → 201; `applicableFor: "widget"` → 422.
    - `POST /api/v1/item-types {"categoryId":<piping>,"key":"pipe_spool","name":"Pipe spool"}` → 201; `GET /api/v1/item-types?contentTypeId=<asset>` → 1 item with `contentTypeId` = asset; `q=SPOOL` → 1 item; `q=valve` → 0.
    - `DELETE /api/v1/content-types/<asset>` while `piping` is live → 409 `CONTENT_TYPE_IN_USE` with `categories: 1`; the `content_types` row keeps `deleted_at` NULL.
    - `PATCH /api/v1/item-types/<id> {"name":"Spool","syncVersion":1}` → 200 `syncVersion: 2`; the same body again → 409 `VERSION_CONFLICT` with `current.name = "Spool"`.
    - With three content types (`asset`, `staff`, `vehicle`), `PUT /api/v1/content-types/order` with their ids reversed → 200 and `GET` lists them in that order with `sortOrder` 10, 20, 30; with one id missing → 422 `ORDER_MISMATCH`.
    - B user `GET /api/v1/item-types/<A's id>` → 404; B `POST /api/v1/item-types` with A's `categoryId` → 404; B `GET /api/v1/content-types` → `items: []`.
    - A user with only `item_type.view`: `POST /api/v1/item-types` → 403 and the `item_types` row count is unchanged; with `item_type.edit` but not `item_type.manage`: `POST /api/v1/content-types` → 403.
    - As `aip_app` with `app.tenant_id` unset: `SELECT count(*) FROM item_categories` → 0 rows visible; `INSERT INTO item_types` → SQLSTATE 42501. `DELETE FROM content_types` as `aip_app` → `permission denied`.
    - Creating the 51st content type → 409 `LIMIT_REACHED` with `limit: 50`.
  - **e2e**:
    - None in this task: there is no page yet, and the API paths, permissions and cross-tenant 404s are covered by the integration tests against the real app and Postgres. ITEMTYPES-03 adds the browser journeys and the skeleton-lane cross-tenant check.
