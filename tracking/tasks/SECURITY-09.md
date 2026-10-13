# SECURITY-09 — No public API docs or OpenAPI schema in production

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | ACCESS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. ADRs: 0001

## Spec

Owner decision (2026-10-12, raised in the ACCESS-01 review): FastAPI's `/docs`, `/redoc` and `/openapi.json` must not be served when `AIP_ENV=production`. Other environments keep them.

- **files**:
  - apps/api/aip/main.py
  - apps/api/tests/test_api_docs.py
- **steps**:
  - 1. `create_app()` passes `openapi_url=None, docs_url=None, redoc_url=None` to `FastAPI(...)` when the environment is `production`.
  - 2. The schema stays available in process (`app.openapi()`), so `tools/codegen/export_openapi.py` and the strip check keep working.
- **acceptance**:
  - With `AIP_ENV=production`, `GET /openapi.json`, `/docs`, `/docs/oauth2-redirect` and `/redoc` return 404; with `test`, `development` or unset they return 200.
- **tests**:
  - **unit**: the four paths per environment over `httpx.ASGITransport`; `app.openapi()` still returns the schema in production.
