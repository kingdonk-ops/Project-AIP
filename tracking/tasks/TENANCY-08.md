# TENANCY-08 — Organisations settings page and invite journey

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TENANCY-03, IDENTITY-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md) and `routes.md` (`/settings/organisations`)
3. ADRs: [0005](../../docs/adr/0005-identity-architecture.md), [0018](../../docs/adr/0018-module-groups-and-navigation.md)

## Spec

Split from TENANCY-03 (2026-10-16): the web pages over the organisations API, and the original
"create a subcontractor organisation and invite a user" journey, which needs IDENTITY-04 invites.

- **files**:
  - apps/web/src/features/organisations/
  - e2e/organisations.spec.ts
- **steps**:
  - 1. `/settings/organisations`: RegisterTable (type, registration number, status), filters, create, deactivate; tenant admin edits, project manager read-only.
  - 2. `/settings/organisations/:id`: profile with edit and deactivate, and "Invite user" that creates an IDENTITY-04 invite with the organisation set on the membership.
- **acceptance**:
  - A tenant admin can create a subcontractor organisation and invite a user into it.
- **tests**:
  - **e2e**:
    - As tenant admin, create a subcontractor organisation and invite a user. Expected: the organisation shows in the list and the invite email is queued.
    - Tenant B opens tenant A's organisation URL. Expected: not found. Axe check on both pages.
