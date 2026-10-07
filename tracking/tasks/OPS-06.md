# OPS-06 — Storage lifecycle renderer with evidence-expiry guard

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Render s3-lifecycle.json from settings and refuse any expiration rule on evidence.

- **files**:
  - backend/app/modules/ops/storage_lifecycle.py
  - infrastructure/s3-lifecycle.json
  - scripts/apply-s3-lifecycle.sh
  - backend/tests/ops/test_storage_lifecycle.py
- **steps**:
  - 1. Define defaults: STANDARD_IA at 365 days, GLACIER_IR at 2555 days (7 years).
  - 2. render(policy) produces the S3 lifecycle JSON by prefix, with per-project overrides.
  - 3. validate() rejects any rule with Expiration or NoncurrentVersionExpiration on evidence prefixes.
  - 4. Check the existing s3-lifecycle.json against validate() in a test.
  - 5. Update apply-s3-lifecycle.sh to take the rendered file.
  - 6. Add a permission check storage_lifecycle:manage on the endpoint.
- **acceptance**:
  - An expiration rule on evidence is rejected.
  - Rendered JSON equals the committed file for default settings.
  - Only users with storage_lifecycle:manage can apply.
- **tests**:
  - **e2e**:
    - Super-admin changes an override and the JSON preview updates before Apply.
  - **integration**:
    - PUT policy with expiration returns 422.
    - User without the permission gets 403.
    - The committed s3-lifecycle.json passes validate().
  - **unit**:
    - render(defaults) has 365 and 2555 transitions.
    - validate with {'Expiration':{'Days':30}} on prefix evidence/ raises.
