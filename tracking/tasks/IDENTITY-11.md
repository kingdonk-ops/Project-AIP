# IDENTITY-11 — User time-zone preference on the profile

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | IDENTITY-10 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md)
3. ADRs: 0025 (the consequence that users get a stored zone preference)

## Spec

Store each user's preferred IANA time zone so emails and pages can show times in it (PORTAL-12 first; owner
2026-11-03) (tag: extend).

- **files**:
  - apps/api/migrations/versions/202611100930_identity_user_time_zone.py (new; take the real timestamp when building)
  - apps/api/aip/modules/identity/ (profile schema, service, `IdentityApi.get_time_zones`)
  - config/terms/en-AU/identity.json
  - apps/api/aip/modules/identity/tests/
- **steps**:
  - 1. A nullable `time_zone` (IANA name, validated against `zoneinfo.available_timezones()`) on the user profile,
    tenant-scoped like the rest of the profile row.
  - 2. `GET/PATCH /api/v1/me` reads and sets it for staff and portal sessions; an unknown name is 422
    `INVALID_TIME_ZONE`. The portal and web profile pages get a zone picker in their own tasks.
  - 3. `IdentityApi.get_time_zones(conn, user_ids) -> dict[user_id, str | None]` for other modules.
- **acceptance**:
  - A user sets `Australia/Sydney` and `IdentityApi.get_time_zones` returns it; `AWST` is refused.
- **tests**:
  - **integration**:
    - set and read back; invalid name → 422; another tenant's user id → absent from the result
