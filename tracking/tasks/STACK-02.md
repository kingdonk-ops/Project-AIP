# STACK-02 — Capability interfaces and adapter selection

| Field | Value |
|---|---|
| Module | [`stack`](../../docs/blueprint/modules/stack/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/stack/README.md`](../../docs/blueprint/modules/stack/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Allow libraries to be swapped by changing one adapter file and an environment setting.

- **depends on**:
  - ARCH-01
- **files**:
  - apps/api/src/platform/capabilities/index.ts
  - apps/api/src/platform/capabilities/object-store.ts
  - apps/api/src/platform/capabilities/adapters/s3.adapter.ts
  - apps/api/src/platform/capabilities/adapters/minio.adapter.ts
  - apps/api/src/platform/capabilities/pdf-renderer.ts
  - apps/api/src/platform/capabilities/adapters/gotenberg.adapter.ts
- **steps**:
  - 1. Define the interfaces ObjectStore, PdfRenderer, Sealer, Ocr and IdentityProvider as TypeScript types.
  - 2. Implement an env-driven factory (OBJECT_STORE=s3|minio, PDF_RENDERER=gotenberg).
  - 3. Implement the ObjectStore adapters (put, get, presign, delete) with tenant-prefixed keys.
  - 4. Implement the Gotenberg PdfRenderer with a timeout and a size cap.
  - 5. Fail boot if a configured adapter key is unknown.
- **acceptance**:
  - Switching OBJECT_STORE changes behaviour with no change in calling code.
  - An unknown adapter key stops boot with a clear message.
  - Secrets are never read from capability_adapter_settings.
- **tests**:
  - **e2e**:
    - Render a sample inspection report PDF through the API on the docker-compose stack. Expected: the download opens and contains the inspection reference.
  - **integration**:
    - Run the conformance suite (put, get, presign, delete, 404 on a missing key) against RustFS and then against the S3 adapter on localstack. Both must pass identically.
    - POST HTML '<h1>Hi</h1>' to the Gotenberg adapter. Expected: the output begins with %PDF and is under 1MB.
  - **unit**:
    - Factory with OBJECT_STORE=minio returns the Minio adapter.
    - Factory with OBJECT_STORE=bogus throws UnknownAdapterError.
    - Key builder produces 'tenant/<id>/...' and rejects '..' segments.
