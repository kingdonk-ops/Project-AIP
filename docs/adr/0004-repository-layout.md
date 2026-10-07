# ADR 0004: Repository layout: Python API and worker, three Vite TypeScript apps

- **Status:** accepted. Moving from Next.js to Vite for all three apps follows the stack review; **owner to confirm**.
- **Date:** 2026-10-07 (revised for the Python backend)
- **Affects:** every task's `files` list; ARCH-01, ARCH-03, STACK-03, STACK-05, TERMS-08, design, offline, portal

## Decision

```
apps/
  api/            Python package `aip` (uv project)
    aip/main.py               FastAPI app factory
    aip/platform/             db, context, access, events (outbox), files, flags, terms, jobs
    aip/modules/<name>/       __init__.py (exports api only), api.py (published interface), tables.py,
                              schemas.py, repository.py, service.py, policies.py, events.py, routes.py,
                              jobs.py, manifest.toml, tests/
    aip/modules/_template/
    aip/worker.py             Procrastinate worker entrypoint (same package)
    migrations/               Alembic env + versions/ (raw SQL, forward-only)
    tests/                    cross-module: isolation, permission matrix, audit chain
  sandbox/        hardened Python images: ifc, ocr, pdfsign, image (ADR 0003)
  web/            Vite + React + TanStack Router: desktop app + admin
  field/          Vite + React PWA, offline-first (Dexie, service worker), Capacitor-wrappable
  portal/         Vite + React on its own origin and session
packages/         (TypeScript, pnpm workspace)
  api-client/     generated from apps/api OpenAPI (openapi-typescript + orval TanStack Query); never hand-edited
  contracts/      JSON Schemas (sync protocol, events, form/rule/workflow) + jsonlogic golden vectors
  ui/ terms/ form-renderer/ markup/ offline-core/ config-eslint/ config-ts/
db/templates/     SQL templates for new tables
config/           workflows/, report-templates/, terms/en-AU/, licence-policy.json
infra/            docker-compose.yml, terraform/ (OpenTofu), coolify/
e2e/              Playwright projects: web, field (mobile Chrome, iPad, WebKit), portal
tools/            new_module.py, codegen, tracking scripts
```

- **Python tooling:** uv workspace, ruff, pyright (strict on `aip/platform`), pytest, testcontainers-python,
  Hypothesis, and import-linter (modules import only other modules' `api`; `platform` never imports `modules`).
- **TS tooling:** pnpm workspace, Vitest, Playwright, and ESLint boundaries (apps never import each other; no
  hard-coded UI strings).
- **Delivery:** each SPA is served from S3 + CloudFront, with `/api/*` path-routed to the ALB, so cookies are same-origin
  `__Host-` cookies. The portal uses its own domain.
- **API contract:** FastAPI generates OpenAPI, which feeds `packages/api-client`. A CI drift check fails on uncommitted changes.

## Consequences

ARCH-01 creates this tree. CI rejects `backend/`, `frontend/` and `services/` paths, and TypeScript under `apps/api`.
