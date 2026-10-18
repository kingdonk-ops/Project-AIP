# ITEMTYPES-02 — Item-type schema versions (draft, publish, pin) and attribute validation in the published interface

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`item_types`](../../docs/blueprint/modules/item_types/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ITEMTYPES-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`ITEMTYPES-01.md`](ITEMTYPES-01.md) (the module, tables and field-type registry this builds on)
3. [`docs/blueprint/modules/item_types/README.md`](../../docs/blueprint/modules/item_types/README.md) ("Item-type schema versioning") and, for columns only, [`data-model.md`](../../docs/blueprint/modules/item_types/data-model.md) (`item_type_versions`)
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (`with_tenant`, raw-SQL migrations), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) and [0030](../../docs/adr/0030-outbox-dispatch-semantics.md) (outbox in the same transaction), [0025](../../docs/adr/0025-time-and-timezones.md) (UTC storage), [0036](../../docs/adr/0036-r1-module-decisions.md) (choice 2: assets pin a version)
5. Code: `aip.platform.db.jsonb_schema.validate_attributes` (`apps/api/aip/platform/db/jsonb_schema.py`), `aip.platform.events.outbox.emit`, `aip.platform.db.concurrency.update_with_version`

## Spec

Give each item type immutable, numbered schema versions edited as one draft at a time and frozen on publish, and publish `get_version`, `get_published_version` and `validate_attributes` so assets can pin a version and have their attributes checked against it on the server (tag: extend).

Out of scope here: the migration preview with impact counts and roll-forward of pinned assets (OPEN-QUESTIONS #39, no R1 row); publish-with-approval; deprecation; expiry flags and scoped reference checks (ITEMTYPES-04); tolerances and out-of-range flags (no R1 row); conditional and calculated attributes (JSONLogic when built, ADR 0036; no R1 row).

- **files**:
  - apps/api/migrations/versions/<timestamp>_item_types_versions.py
  - apps/api/aip/modules/item_types/attribute_schema.py
  - apps/api/aip/modules/item_types/tables.py
  - apps/api/aip/modules/item_types/schemas.py
  - apps/api/aip/modules/item_types/repository.py
  - apps/api/aip/modules/item_types/service.py
  - apps/api/aip/modules/item_types/routes.py
  - apps/api/aip/modules/item_types/events.py
  - apps/api/aip/modules/item_types/api.py
  - apps/api/aip/modules/item_types/manifest.toml
  - apps/api/aip/modules/item_types/tests/test_attribute_schema.py
  - apps/api/aip/modules/item_types/tests/test_versions_db.py
  - packages/contracts/events/item_type.version_published.v1.json
  - packages/api-client/openapi.json (regenerated)
  - config/terms/en-AU/item_types.json
- **steps**:
  - 1. Migration `<timestamp>_item_types_versions.py`:
    - create `item_type_versions` from `db/templates/tenant_table.sql.tpl` with `item_type_id uuid NOT NULL, version integer NOT NULL, status text NOT NULL DEFAULT 'draft', attributes jsonb NOT NULL DEFAULT '[]', compiled_schema jsonb NULL, change_summary text NULL, published_at timestamptz NULL, published_by uuid NULL, created_by uuid NULL, sync_version integer NOT NULL DEFAULT 1`.
    - Constraints: `CHECK (status IN ('draft','published'))`, `CHECK (version >= 1)`, `CHECK (jsonb_typeof(attributes) = 'array')`, `CHECK ((status = 'published') = (compiled_schema IS NOT NULL AND published_at IS NOT NULL))`, FK `(item_type_id, tenant_id) REFERENCES item_types (id, tenant_id)`, `UNIQUE (id, tenant_id)`.
    - Indexes: unique `(tenant_id, item_type_id, version) WHERE deleted_at IS NULL`; unique `(tenant_id, item_type_id) WHERE status = 'draft' AND deleted_at IS NULL` (at most one draft).
    - Freeze: a `BEFORE UPDATE` trigger `item_type_versions_freeze` raises SQLSTATE `55000` ("published item type version is immutable") when `OLD.status = 'published'`. Drafts stay editable and soft-deletable. `REVOKE DELETE ON item_type_versions FROM aip_app`.
    - Alter `item_types`: add `published_version_id uuid NULL` with FK `(published_version_id, tenant_id) REFERENCES item_type_versions (id, tenant_id)`.
  - 2. `attribute_schema.py` (pure functions, no database):
    - An attribute definition is `{key, label, fieldType, required?, config?, helpText?}` (`required` default false). `attributes` is a list of them, in display order.
    - `lint_attributes(attributes) -> list[AttributeDefinitionIssue]` (`path`, `code`), paths like `attributes[2].config.unit`. Codes: `ATTRIBUTE_KEY_INVALID` (not `^[a-z][a-z0-9_]{0,62}$`), `ATTRIBUTE_KEY_DUPLICATE`, `ATTRIBUTE_LABEL_MISSING`, `ATTRIBUTE_FIELD_TYPE_UNKNOWN` (not in `field_types()`), `ATTRIBUTE_FIELD_TYPE_NOT_ALLOWED` (not usable as an attribute, e.g. `photo`), `ATTRIBUTE_CONFIG_INVALID` (fails the field type's `config_schema`), `ATTRIBUTE_RANGE_INVALID` (`min` > `max`), `ATTRIBUTE_OPTION_DUPLICATE`, `ATTRIBUTES_TOO_MANY` (> 200).
    - `compile_schema(attributes) -> dict` builds the Draft 2020-12 schema `{"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": false, "properties": {key: value_schema(config)}, "required": [required keys in order]}` from the ITEMTYPES-01 registry. It is only called on a lint-clean list.
  - 3. Service, each operation in one `with_tenant` transaction; the item type is locked `FOR UPDATE` for draft creation and publish:
    - `create_draft(item_type_id)`: version = highest live version + 1; `attributes` copied from the published version (or `[]`). A live draft already exists → 409 `DRAFT_EXISTS` with `draftId`.
    - `update_draft(version_id, {attributes?, changeSummary?, syncVersion})` through `update_with_version`. Not a draft → 409 `VERSION_NOT_DRAFT`. Lint issues → 422 `ATTRIBUTES_INVALID` with `issues: [{path, code}]` and nothing written.
    - `discard_draft(version_id)`: soft delete; not a draft → 409 `VERSION_NOT_DRAFT`.
    - `publish(version_id, {changeSummary?, syncVersion})`: re-lint (issues → 422 `ATTRIBUTES_INVALID`), set `status = 'published'`, `compiled_schema`, `published_at = now()` (UTC), `published_by` = actor, point `item_types.published_version_id` at it, and `emit(conn, "item_type.version_published", 1, Aggregate("item_type", item_type_id), {itemTypeId, itemTypeKey, versionId, version, previousVersionId})` in the same transaction.
    - Item-type delete (ITEMTYPES-01) gains the rule: any published version → 409 `ITEM_TYPE_PUBLISHED`.
    - Older published versions stay readable and usable: pinning means a caller keeps the version id it was given; nothing here moves pinned records.
  - 4. Permissions: add `item_type.publish` to `manifest.toml` (an unlisted verb, so only `admin` roles get it by default, ADR 0027 §3). Declare `[[events]] name = "item_type.version_published" version = 1`, register the payload model in `events.py` (`extra="forbid"`), and export the JSON with `tools/codegen/export_event_schemas.py`.
  - 5. Routes under `/api/v1/item-types/{item_type_id}/versions` (`requires(...)` on each, `item_types_versions_*` operation ids):
    - `GET` (`item_type.view`) → versions newest first, without `compiledSchema`.
    - `GET /{version_id}` (`item_type.view`) → one version with `attributes` and, when published, `compiledSchema`.
    - `POST` (`item_type.edit`) → 201 draft; `PATCH /{version_id}` and `DELETE /{version_id}` (`item_type.edit`).
    - `POST /{version_id}/publish` (`item_type.publish`) → 200 the published version.
    - `POST /{version_id}/validate {attributes}` (`item_type.view`) → `{valid, errors: [{path, termKey, params}]}` for a published version, so the editor and later the asset form can check a sample.
    - `GET /api/v1/item-types/{id}` gains `publishedVersionId`, `publishedVersion` and `draftVersionId`.
  - 6. `api.py` (`ItemTypesApi`; all take the caller's tenant-bound connection so RLS applies):
    - `get_version(conn, version_id) -> ItemTypeVersionOut | None` — published versions only (a draft or another tenant's id → `None`).
    - `get_published_version(conn, item_type_id) -> ItemTypeVersionOut | None` — the current published version, or `None` when there is none yet.
    - `validate_attributes(conn, version_id, attributes) -> list[AttributeValidationError]` — loads the published version (`NotFoundError` if `get_version` would return `None`) and wraps `aip.platform.db.jsonb_schema.validate_attributes(compiled_schema, attributes)`; errors carry `validation.attribute.<keyword>` term keys.
    - Re-export `AttributeValidationError` so callers need not import the platform type themselves.
  - 7. Term keys (`config/terms/en-AU/item_types.json`): `item_types.version.status.draft|published`, one key per issue code (`item_types.issue.<code lower-case>`); `validation.attribute.*` keys already exist or are added here if missing.
- **acceptance**:
  - A published version can never change: the API refuses edits with 409, and a direct `UPDATE` as `aip_app` fails with SQLSTATE 55000.
  - Each item type has at most one draft, version numbers increase by one, and publish writes the version, the item type pointer and one outbox event in one transaction.
  - `ItemTypesApi.validate_attributes` against an older published version still uses that version's schema after a newer one is published.
  - Every rejection has a stable code and a term-keyed path; no English messages leave the API.
- **tests**:
  - **unit** (`test_attribute_schema.py`):
    - `lint_attributes([{"key":"wall_thickness","label":"Wall thickness","fieldType":"measurement","required":true,"config":{"unit":"mm","min":0,"max":100}}])` → `[]`.
    - `compile_schema` of that list → `{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"properties":{"wall_thickness":{"type":"number","minimum":0,"maximum":100}},"required":["wall_thickness"]}`.
    - Two attributes with key `material` → `[("attributes[1].key","ATTRIBUTE_KEY_DUPLICATE")]`.
    - `{"key":"Material","label":"x","fieldType":"text"}` → `ATTRIBUTE_KEY_INVALID` at `attributes[0].key`.
    - `fieldType: "gps"` → `ATTRIBUTE_FIELD_TYPE_UNKNOWN`; `fieldType: "photo"` → `ATTRIBUTE_FIELD_TYPE_NOT_ALLOWED`.
    - `measurement` with `{"unit":"in"}` → `ATTRIBUTE_CONFIG_INVALID` at `attributes[0].config`; with `{"unit":"mm","min":10,"max":5}` → `ATTRIBUTE_RANGE_INVALID`.
    - `dropdown` with options values `cs`, `cs` → `ATTRIBUTE_OPTION_DUPLICATE` at `attributes[0].config.options[1].value`.
    - 201 valid attributes → `ATTRIBUTES_TOO_MANY` at `attributes`.
    - Against the compiled schema above, `aip.platform.db.jsonb_schema.validate_attributes(schema, {"wall_thickness": 120})` → one error `$.wall_thickness`, `validation.attribute.maximum`, `params.limit = 100`; `{}` → `$.wall_thickness`, `validation.attribute.required`; `{"wall_thickness": 5, "colour": "red"}` → `validation.attribute.additionalProperties`.
  - **integration** (`test_versions_db.py`, pytest + testcontainers-python Postgres, the TESTING-01 tenants `kaefer-demo` (A) and `tenant-b` (B), item type `pipe_spool` from the ITEMTYPES-01 fixtures):
    - A `POST /api/v1/item-types/<pipe_spool>/versions` → 201 `{version: 1, status: "draft", attributes: []}`; again → 409 `DRAFT_EXISTS` with the same `draftId`.
    - `PATCH` the draft with the `wall_thickness` attribute and `syncVersion: 1` → 200 `syncVersion: 2`; with `fieldType: "photo"` → 422 `ATTRIBUTES_INVALID` with `issues[0] = {path: "attributes[0].fieldType", code: "ATTRIBUTE_FIELD_TYPE_NOT_ALLOWED"}` and the stored draft unchanged.
    - A user with `item_type.edit` but not `item_type.publish`: `POST .../publish` → 403, and `SELECT count(*) FROM domain_events WHERE event_name = 'item_type.version_published'` is unchanged.
    - An admin `POST .../publish {"syncVersion": 2}` → 200 `status: "published"`, `publishedAt` in UTC; `GET /api/v1/item-types/<pipe_spool>` → `publishedVersion: 1`, `draftVersionId: null`; exactly 1 `domain_events` row `item_type.version_published` with `version: 1`, `previousVersionId: null`.
    - `PATCH` the published version → 409 `VERSION_NOT_DRAFT`. As `aip_app` in tenant A: `UPDATE item_type_versions SET attributes = '[]'` on it → SQLSTATE 55000; `DELETE FROM item_type_versions` → `permission denied`.
    - Create draft v2 (copies `wall_thickness`), change `max` to 50, publish → `publishedVersion: 2`, event `previousVersionId` = v1's id. Then `ItemTypesApi.validate_attributes(conn, v1_id, {"wall_thickness": 80})` → `[]` and `validate_attributes(conn, v2_id, {"wall_thickness": 80})` → 1 error `validation.attribute.maximum` (pinning).
    - `ItemTypesApi.get_version(conn, <draft id>)` → `None`; `validate_attributes(conn, <draft id>, {})` → `NotFoundError`; `get_published_version(conn, <type with no versions>)` → `None`.
    - `POST .../versions/<v2>/validate {"attributes": {"wall_thickness": "thick"}}` → 200 `{valid: false, errors: [{path: "$.wall_thickness", termKey: "validation.attribute.type", ...}]}`.
    - Two concurrent `publish` calls on the same draft (asyncio.gather) → one 200 and one 409; `item_type_versions` has one published row for that version number and `domain_events` has one event for it.
    - Force `emit` to raise (test hook) during publish → 500; the draft is still `draft` and `item_types.published_version_id` unchanged.
    - `DELETE /api/v1/item-types/<pipe_spool>` → 409 `ITEM_TYPE_PUBLISHED`.
    - B user: `GET /api/v1/item-types/<A's pipe_spool>/versions/<v1>` → 404; `ItemTypesApi.get_version` on a B connection with A's v1 id → `None`.
  - **e2e**:
    - None in this task: it adds API only, and the paths, permissions, freeze and cross-tenant 404s are covered by the integration tests against the real app and Postgres. ITEMTYPES-03 drives draft, edit and publish from the browser.
