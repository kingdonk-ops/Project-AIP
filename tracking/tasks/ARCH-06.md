# ARCH-06 — Versioned event registry and catalogue API

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-02, ARCH-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Define the event catalogue with typed schemas and expose it for the admin pages.

- **depends on**:
  - ARCH-02
  - ARCH-05
- **files**:
  - apps/api/src/platform/events/registry.ts
  - apps/api/src/platform/events/catalogue.controller.ts
  - packages/contracts/src/events.ts
- **steps**:
  - 1. Define registerEvent({name, version, schema: ZodType, owner}) and load the events declared in each manifest.
  - 2. Reject duplicate name+version registrations and reject payload changes on an already-released version.
  - 3. Add GET /api/v1/admin/platform/events with module, status and version filters and a 24h published and failed count.
  - 4. Add GET /api/v1/admin/platform/events/:eventName (schema as JSON Schema plus subscribers).
  - 5. Add a Deprecate action that is permission-gated.
- **acceptance**:
  - Duplicate registration throws at boot.
  - The catalogue lists each event's subscribers.
  - A deprecated event still validates but is flagged.
- **tests**:
  - **e2e**:
    - Open /admin/platform/events as a platform admin. Expected: the table renders the seeded events. As a plain user: 403.
  - **integration**:
    - Seed 3 events and 5 outbox rows (2 failed). GET the catalogue. Expected: published24h=3 and failed24h=2 for the matching event.
    - GET ?module=inspections. Expected: only events owned by that module.
  - **unit**:
    - registerEvent twice with name 'inspection.signed_off' and version 1 throws DuplicateEventError.
    - validate('inspection.signed_off',1,{}) throws with the missing field names.
