# ADR 0004: Canonical repository layout; field PWA and portal as separate Vite apps

- **Status:** accepted, except the field-app framework, which is **proposed (owner to confirm)**
- **Date:** 2026-10-07
- **Affects:** every task's `files` list; ARCH-01, ARCH-03, STACK-03, STACK-05, TERMS-08, offline, portal

## Context

Task paths mix `apps/web/...`, `frontend/src/...` and `backend/app/...`. The owner chose Next.js and a
separate-origin portal. The offline field app must boot with no network, which the Next.js App Router
(server components, RSC fetches) handles poorly. See docs/reviews/06-stack-typescript.md.

## Decision

```
apps/
  api/      NestJS (Fastify). src/platform/{db,context,access,events,files,flags}
            src/modules/<name>/{module,api,service,controller,schemas,events,permissions}.ts, manifest.json, tests/
  worker/   BullMQ processors + outbox dispatcher (imports modules' api.ts only)
  web/      Next.js App Router: desktop app + admin (src/features/<module>/)
  field/    Vite + React SPA, installable offline PWA (Dexie, service worker)   <- proposed
  portal/   Vite + React SPA on its own origin and session
packages/   contracts, api-client (orval, generated), permissions, terms, ui, form-renderer,
            markup, offline-core, config-eslint, config-ts, config-vitest
services/sidecar/        Python (ADR 0003)
db/migrations/ db/templates/   (ADR 0002)
config/     workflows/, report-templates/, terms/en-AU/, licence-policy.json
infra/      docker-compose.yml, terraform/ (OpenTofu), coolify/
e2e/        Playwright projects: web, field (mobile Chrome, iPad, WebKit), portal
tests/      cross-module: isolation, permission-matrix, audit-chain, sidecar-contract
tools/      new-module.ts, codegen, tracking scripts
```

- **Tooling:** pnpm + Turborepo, TS project references, Vitest (`unplugin-swc` in apps/api),
  Testcontainers-node, Playwright, fast-check.
- **Boundaries:** dependency-cruiser (only `modules/<x>/api.ts` crosses modules; `platform` never imports
  `modules`; apps never import each other; packages never import apps), plus ESLint for frontend features
  and hard-coded strings.
- **API contract:** NestJS + nestjs-zod → OpenAPI → orval → `packages/api-client`, with a CI drift check.
  Non-REST shapes (sync, events, manifests) live in `packages/contracts`.

## Consequences

ARCH-01 creates this tree, and CI rejects new files under `backend/` or `frontend/`. If the owner keeps
Next.js for the field app, it becomes a client-only static export, and offline boot must be proven in
TESTING-08 before P2.
