# PORTAL-13 — Portal client sets their own time zone on `/api/v1/portal/me`

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | XS |
| Depends on | IDENTITY-11, PORTAL-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. ADRs: 0025 (the stored zone preference), 0036 choice 7 (portal sessions reach only `/api/v1/portal/`)

## Spec

Let a signed-in portal client read and set their preferred IANA time zone (tag: extend). Found by IDENTITY-11:
IDENTITY-11 asked for `PATCH /api/v1/me` to serve portal sessions too, but ADR 0036 choice 7 keeps portal
principals on the `/api/v1/portal/` allow-list, so the portal needs its own route.

- **files**:
  - apps/api/aip/modules/portal/ (routes, schemas, service)
  - apps/api/aip/modules/portal/tests/
- **steps**:
  - 1. `GET /api/v1/portal/me` adds `timeZone` (from identity's `get_time_zones`).
  - 2. `PATCH /api/v1/portal/me` with `{"timeZone": "<IANA name>" | null}` calls identity's `set_time_zone`;
    `InvalidTimeZoneError` → 422 `INVALID_TIME_ZONE`. Same session, rate-limit and tenant checks as the other
    client routes.
- **acceptance**:
  - A portal client sets `Australia/Perth` and `GET /api/v1/portal/me` returns it; `AWST` is refused.
- **tests**:
  - **integration**:
    - set and read back; invalid name → 422; a staff session gets 404 on the route; another tenant's client is untouched
