# SECURITY-06 — Data classification tags, field masking and EXIF GPS control

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | PLAN-R1, SECURITY-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Mask sensitive and health fields in serializers and strip EXIF GPS per policy.

- **depends on**:
  - SECURITY-02
- **files**:
  - backend/app/modules/security/masking.py
  - backend/app/modules/security/exif.py
  - backend/tests/security/test_masking.py
  - backend/tests/fixtures/images/gps.jpg
- **steps**:
  - 1. Implement a classification registry mapping (entity, field) to public, internal, sensitive or health.
  - 2. Add a masking policy: roles with the permission pii:view see values; others see '••••'.
  - 3. Implement serializer middleware applying the policy to response dicts.
  - 4. Implement strip_gps(image_bytes) using Pillow, keeping orientation.
  - 5. Add a tenant setting keep_exif_gps (default false).
  - 6. Expose classification as metadata for the AI layer to read.
- **acceptance**:
  - A health field is masked for a role without pii:view.
  - An uploaded photo has no GPS tags after processing.
  - Masking is applied on list and detail responses.
- **tests**:
  - **e2e**:
    - The portal user opens an incident record and sees masked health fields.
  - **integration**:
    - GET incident as a viewer: injury_detail masked; as a safety manager: clear.
    - Upload gps.jpg: the stored file has no GPS EXIF; with keep_exif_gps=true, GPS is retained.
  - **unit**:
    - mask({'injury':'fracture'}, role=viewer) returns '••••'.
    - strip_gps(gps.jpg) yields no GPSInfo tags, and orientation is preserved.
