# TENANCY-04 — Asset sharing with party-scoped visibility profiles

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TENANCY-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Let a client see status and evidence on a shared asset without seeing commercial fields.

- **depends on**:
  - TENANCY-03
- **files**:
  - migrations/versions/0141_visibility_profiles_org_asset_shares.sql
  - apps/api/src/modules/tenancy/sharing.service.ts
  - apps/api/src/modules/tenancy/sharing.controller.ts
  - apps/api/src/modules/tenancy/field-projection.ts
- **steps**:
  - 1. Migration for visibility_profiles (name, allowed_fields JSONB, deny_fields JSONB) and org_asset_shares (org_id, asset_path, profile_id, expires_at, revoked_at).
  - 2. Implement projectFields(record, profile) as an allow-list projection.
  - 3. Apply the projection in the asset read and list responses for users of a client organisation.
  - 4. Implement revoke and expiry, honoured at query time.
  - 5. Implement preview-as-organisation for admins, which is read-only.
- **acceptance**:
  - A client user never receives rate or cost fields.
  - An expired or revoked share returns 404.
  - A share on a parent path covers descendants.
- **tests**:
  - **e2e**:
    - As admin, preview as Rio Tinto. Expected: the asset page hides commercial tabs. Set the expiry to yesterday and refresh as the Rio user. Expected: the asset is no longer visible.
  - **integration**:
    - Share asset A.B with the Rio profile, then GET /assets/A.B/child as a Rio user. Expected: 200 and the response has no 'rate' key.
    - Revoke the share. Expected: 404 immediately.
    - Rio user requests an asset in an unshared path. Expected: 404.
  - **unit**:
    - projectFields({status:'ok', rate:120}, {allowed:['status']}) returns {status:'ok'}.
    - isShareActive with expires_at in the past returns false.
