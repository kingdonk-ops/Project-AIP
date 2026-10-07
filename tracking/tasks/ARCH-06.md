# ARCH-06 — Versioned event registry and catalogue API
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-02, ARCH-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md) (event catalogue feature and the `/admin/platform/events` page)
3. ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md) (`packages/contracts` holds event JSON Schemas)

## Spec

Define the event catalogue with Pydantic payload models, freeze released versions as JSON Schema in `packages/contracts`, and expose the catalogue API for the admin pages.

- **depends on**:
  - ARCH-02
  - ARCH-05
- **files**:
  - apps/api/aip/platform/events/registry.py
  - apps/api/aip/platform/events/routes.py (catalogue endpoints)
  - apps/api/migrations/versions/<YYYYMMDDHHMM>_event_catalogue.py (`platform_event_status` global table + `platform_event_counts` function)
  - tools/codegen/export_event_schemas.py
  - packages/contracts/events/<event_name>.v<version>.json (generated, committed)
  - apps/api/tests/platform/events/test_registry.py
  - apps/api/tests/platform/events/test_catalogue_routes.py
- **steps**:
  - 1. `register_event(name, version, schema: type[BaseModel], owner: str)`. At boot the module registry (ARCH-02) loads every module's `events.py`, which registers the events listed under `events` in its `manifest.toml`; a manifest entry without a registered model (or the reverse) fails boot. The registry implements ARCH-05's `EventSchemaLookup`.
  - 2. Reject a duplicate `name`+`version` registration (`DuplicateEventError`). `tools/codegen/export_event_schemas.py` writes `model_json_schema()` (sorted keys) for each event to `packages/contracts/events/`; at boot, a registered model whose schema differs from a committed file for the same name+version raises `ReleasedSchemaChangedError` (a payload change needs a new version). CI runs the exporter and fails on `git diff`.
  - 3. Migration: global table `platform_event_status (event_name, event_version, status, deprecated_at, deprecated_by)`, no `tenant_id`, added to the global-table CI allow-list; and a `SECURITY DEFINER` function `platform_event_counts(since timestamptz)` owned by `aip_owner`, returning only `(event_name, event_version, published, failed)` aggregates across tenants (no payloads), `EXECUTE` granted to `aip_app`.
  - 4. `GET /api/v1/admin/platform/events` with `module`, `status` and `version` filters, returning name, version, owner module, status, subscribers (from manifests' `subscribes`), `published_24h` and `failed_24h`. `GET /api/v1/admin/platform/events/{event_name}` returns each version's JSON Schema and subscribers.
  - 5. `POST /api/v1/admin/platform/events/{event_name}/versions/{version}/deprecate`, gated by permission `platform.events.manage` via the policy service (platform operators only). It writes `platform_event_status` and emits `platform.event.deprecated`.
- **acceptance**:
  - Duplicate registration fails boot.
  - Changing a released payload model without bumping the version fails boot and CI.
  - The catalogue lists each event's subscribers.
  - A deprecated event still validates but is flagged `status: deprecated`.
- **tests**:
  - **unit**:
    - `register_event("widget.created", 1, WidgetCreatedV1, "widgets")` twice raises `DuplicateEventError`.
    - `registry.validate("widget.created", 1, {})` raises `EventValidationError` listing `widget_id` and `name`.
    - Registering a `WidgetCreatedV1` with an extra required field while the committed `widget.created.v1.json` lacks it raises `ReleasedSchemaChangedError`.
  - **integration** (testcontainers-python):
    - Register 3 fixture events; insert 5 outbox rows for `widget.created` v1 in the last 24 h, 2 of them with `dead_lettered_at` set, across two tenants. `GET` the catalogue as a platform operator. Expected: `published_24h=3`, `failed_24h=2` for that event.
    - `GET ?module=widgets`. Expected: only events owned by `widgets`.
    - Deprecate `widget.created` v1, then `emit` it. Expected: insert succeeds and the catalogue shows `status: deprecated`.
  - **e2e**:
    - Against the running API: `GET /api/v1/admin/platform/events` as the fixture platform operator returns 200 with the seeded events; as a plain `tenant-a` user returns 403. (The `/admin/platform/events` web page is built by a later web task against the generated client.)
