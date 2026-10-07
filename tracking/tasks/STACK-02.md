# STACK-02 — Capability interfaces and adapter selection
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`stack`](../../docs/blueprint/modules/stack/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/stack/README.md`](../../docs/blueprint/modules/stack/README.md) (capability interfaces, S3 / RustFS conformance)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (sealing and OCR run in sandbox workers), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md) (SSE-KMS key per tenant on every put), [0004](../../docs/adr/0004-repository-layout.md)

## Spec

Allow libraries to be swapped by changing one adapter file and an environment setting, never calling code.

- **depends on**:
  - ARCH-01
- **files**:
  - apps/api/aip/platform/capabilities/__init__.py (factory `get_object_store()`, `get_pdf_renderer()`)
  - apps/api/aip/platform/capabilities/settings.py (pydantic-settings `CapabilitySettings`)
  - apps/api/aip/platform/capabilities/protocols.py (`ObjectStore`, `PdfRenderer`, `Sealer`, `Ocr`, `IdentityProvider`)
  - apps/api/aip/platform/capabilities/keys.py (tenant key builder)
  - apps/api/aip/platform/capabilities/adapters/s3.py (aioboto3; AWS S3 and LocalStack)
  - apps/api/aip/platform/capabilities/adapters/minio.py (S3-compatible endpoint, path-style; RustFS/MinIO on Coolify and dev)
  - apps/api/aip/platform/capabilities/adapters/gotenberg.py (httpx)
  - apps/api/tests/platform/capabilities/test_factory.py
  - apps/api/tests/platform/capabilities/test_object_store_conformance.py
  - apps/api/tests/platform/capabilities/test_gotenberg.py
- **steps**:
  - 1. Define the five capabilities as `typing.Protocol`s in `protocols.py`. `ObjectStore`: `put(key, body, *, content_type, kms_key_id=None)`, `get(key)`, `presign_put(key, *, expires_s, kms_key_id=None)`, `presign_get(key, *, expires_s)`, `delete(key)`. `PdfRenderer.render_html(html, *, assets=None) -> bytes`. `Sealer` and `Ocr` are protocols only here; their implementations dispatch sandbox jobs (ADR 0003) in later tasks. `IdentityProvider` describes the Keycloak broker calls (ADR 0005).
  - 2. Env-driven factory: `OBJECT_STORE=s3|minio`, `PDF_RENDERER=gotenberg`. Settings come only from environment variables via pydantic-settings; credentials are `SecretStr`.
  - 3. Implement both `ObjectStore` adapters. Keys are built only by `tenant_key(tenant_id, *parts)` → `tenant/<uuid>/<parts...>`, rejecting empty, `.` or `..` segments and leading `/`. When `kms_key_id` is given the S3 adapter sets `ServerSideEncryption=aws:kms` and `SSEKMSKeyId` (header `x-amz-server-side-encryption-aws-kms-key-id`) on puts and presigned PUTs; UPLOADS-01 enforces that it is always given.
  - 4. Implement the Gotenberg `PdfRenderer` (`POST /forms/chromium/convert/html`) with a request timeout (default 30 s) and a response size cap (default 25 MB), raising `RenderTimeoutError` / `RenderTooLargeError`.
  - 5. Fail app startup if a configured adapter key is unknown (`UnknownAdapterError` naming the variable and the allowed values).
  - 6. Non-secret per-deployment adapter config (if later stored in `capability_adapter_settings`) is parsed by `parse_adapter_config(dict)`, which rejects any key matching `secret|password|token|access_key` so secrets can only come from the environment.
- **acceptance**:
  - Switching `OBJECT_STORE` changes behaviour with no change in calling code.
  - An unknown adapter key stops startup with a clear message.
  - Secrets are never read from `capability_adapter_settings`.
- **tests**:
  - **unit**:
    - Factory with `OBJECT_STORE=minio` returns `MinioObjectStore`.
    - Factory with `OBJECT_STORE=bogus` raises `UnknownAdapterError` mentioning `OBJECT_STORE` and `s3, minio`.
    - `tenant_key(T1, "uploads", "a.pdf")` returns `f"tenant/{T1}/uploads/a.pdf"`; `tenant_key(T1, "..", "x")` raises `ValueError`.
    - `parse_adapter_config({"access_key": "x"})` raises `SecretInConfigError`.
  - **integration** (testcontainers-python):
    - Run the same parametrised conformance suite (put, get round-trip, presigned PUT then GET via httpx, delete, `ObjectNotFoundError` on a missing key) against a RustFS container with the `minio` adapter and against LocalStack S3 with the `s3` adapter. Both pass identically.
    - On LocalStack with a KMS key created in LocalStack KMS: `put(..., kms_key_id=K)` then `head_object` reports `SSEKMSKeyId == K`.
    - POST `<h1>Hi</h1>` through the Gotenberg adapter against a `gotenberg/gotenberg:8` container. Expected: output starts with `%PDF` and is under 1 MB.
    - Gotenberg adapter with `timeout_s=0.001`. Expected: `RenderTimeoutError`.
  - **e2e**:
    - On the docker-compose stack, render the fixture `apps/api/tests/fixtures/report.html` (contains reference `FX-0001`) through `get_pdf_renderer()` and store it via `get_object_store()`; download via a presigned GET. Expected: a valid PDF whose extracted text contains `FX-0001`.
