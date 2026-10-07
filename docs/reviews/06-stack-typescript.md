# Application tech stack specialist review

## Verdict
**Conditional approve: the stack is sound, but the repo is not ready for implementation until five contradictions are fixed (listed below).** TypeScript, NestJS, Node 22, Zod, pnpm, Postgres with RLS, Keycloak and Gotenberg are coherent choices. Three problems:
- The design still carries Python-era artefacts: Alembic, pytest and Hypothesis, `backend/` and `frontend/` paths, "arq or Celery", and a Vite portal.
- One structural decision is wrong for this product: the offline field PWA should not be a route inside the Next.js App Router app (see Recommended choices).
- `docs/adr/` does not exist. Every document says "ADR wins", but no ADR is written, so the conflicts below have no arbiter. STACK-01 should land first.

## Contradictions found (with file citations)
Paths are under `/home/user/Project-AIP/`.

1. **Path conventions are fragmented.**
   - TypeScript layout: `apps/api/src/modules/...`, `apps/web/src/features/...`, `apps/worker/src/...` (ARCH-01, ARCH-02 to ARCH-08, TENANCY-01 to TENANCY-07, DATABASE-02 to DATABASE-06, STACK-02, STACK-03, STACK-05).
   - `frontend/src/lib/i18n/...` and `frontend/src/features/...` (tracking/tasks/TERMS-08.md; OPS-03, OPS-05).
   - Python layout: `backend/app/modules/...`, `backend/tests/...`, `backend/migrations/versions/*.py` (TERMS-01 to TERMS-03, OPS-02, OPS-03, OPS-05, TESTING-01 to TESTING-08).
   - `docs/blueprint/04-code-layout.md` still shows `erp/services/api/app/*.py` and `frontend/`, even though its warning banner says to map to ARCH-01. Files such as `module.toml`, `importlinter.ini`, `api.py` and `pyproject.toml` have no TS equivalent defined.
2. **Migrations are in contradiction three ways.**
   - 07-task-conventions.md line 1 says "ADR 0002: migrations are TypeScript, not Alembic".
   - The same file's second bullet says "forward-only Alembic raw SQL from templates".
   - tracking/tasks/STACK-01.md step 2 keeps Alembic as the sole schema authority, run from a standalone container, with Drizzle as a query builder only.
   - Decision 01-decisions.md says "Keep Alembic raw SQL with templates".
   - Alembic means Python in the CI, Docker and dev toolchain of a TS monorepo, purely for migrations.
   - TESTING-05 and TESTING-01 also use "up-down-up", which contradicts "forward-only".
3. **Queue.**
   - Decision "Redis queue (arq or Celery)" names Python libraries.
   - STACK-01 and TENANCY-02 assume BullMQ. OPS-02 still has `jobs/runner.py` and arq.
   - arch/README.md (open questions) says the outbox transport is undecided.
   - arq jobs cannot be enqueued natively from Node.
4. **Portal framework.** The owner decision says "Separate build on its own origin" and the brief says Next.js or Vite. modules/portal/architecture.md line 78 says "Separate Vite build and origin". ARCH-01 has no `apps/portal`. ARCH-03 mentions only `apps/web`.
5. **Frontend plumbing under-specified.**
   - 04-code-layout.md puts `portal/` and `field/` inside one `frontend/src`. The offline module files sit under `frontend/src/modules/offline/...` (offline/architecture.md).
   - TERMS-08 stores the terms bundle in IndexedDB with i18next, while the field app's store is Dexie. The two need a shared offline-store contract.
6. **Test tooling is Python.**
   - TESTING-07 uses Hypothesis, with `backend/tests/sync/*.py`.
   - TESTING-08 uses `--cov-fail-under` and `backend/pyproject.toml`.
   - TESTING-02 to TESTING-06 list `.py` files.
   - ARCH-01 does not name a test runner, and the Testcontainers tasks (TESTING-01, 03, ARCH-05) are written in Python terms.
7. **Client generation text.** 04-code-layout says "generated from FastAPI OpenAPI". STACK-03 says NestJS, with orval for the TanStack client. This only needs the layout text updating. There is also a gap: `packages/api-client` (STACK-03) versus `packages/contracts` (ARCH-01) have no stated relationship.
8. **Component boundaries.** ARCH-03 enforces `apps/web` may import only `packages/*`. But 04-code-layout's `platform/` and `features/` frontend rules (ESLint `no-restricted-imports`) are not carried into any task. Neither is the hard-coded-string lint rule, which is a conventions requirement.
9. **Sidecar boundary.**
   - 04-code-layout and arch/README say the sidecar is called via a job queue and signed callbacks.
   - STACK-02's capability list (`Ocr`) hides the sidecar behind an interface.
   - STACK-05 builds `services/sidecar/Dockerfile`, but no task defines its protocol, generated models or contract tests.
10. **Coverage and CI.** TESTING-08 refers to `backend/pyproject.toml` and `ci.yml` with Python job names.

## Canonical repository layout (tree)
```
aip/
  pnpm-workspace.yaml  turbo.json  package.json  tsconfig.base.json  .dependency-cruiser.cjs
  apps/
    api/                 NestJS (Fastify adapter), Node 22
      src/main.ts  app.module.ts
      src/platform/      db, context, access, events(outbox), files, capabilities, flags, version
      src/modules/<kebab-name>/{module.ts,api.ts,service.ts,controller.ts,schemas.ts,events.ts,permissions.ts,manifest.json,db/,tests/}
      src/modules/_template/
    worker/              BullMQ processors + outbox dispatcher; imports module api.ts only
    web/                 Next.js App Router: internal desktop app + admin (src/features/<module>/)
    field/               Vite + React SPA, installable PWA (offline-first). Dexie, sync engine, SW
    portal/              Vite SPA (or Next, see Q1), own origin, own session, narrow API client
  packages/
    contracts/           Zod: manifest, events, sync protocol, forms/rules/workflow schemas, errors
    api-client/          orval-generated TanStack Query hooks + Zod (from apps/api OpenAPI); read-only
    permissions/         generated catalogue
    terms/               keys + en-AU defaults + useT/provider (no framework coupling)
    ui/                  Radix-based design system, tokens
    form-renderer/       FormRenderer + JSONLogic evaluator wrapper (shared by web, field, portal, api)
    markup/              PDF.js + Konva viewer/editor, JSON annotation model
    offline-core/        Dexie schema, sync engine, outbox, media queue (consumed by apps/field; web read-only cache optional)
    config-eslint/ config-ts/ config-vitest/
  services/
    sidecar/             Python (uv, FastAPI) IFC/CAD/OCR; own pyproject; generated pydantic models from contracts
  db/
    migrations/          forward-only raw SQL, per-module prefix (runner: see choices)
    tests/
  config/                workflows/, report-templates/, terms/, ref-packs/, licence-policy.json
  infra/                 docker-compose.yml, terraform/, coolify/
  tools/                 new-module.ts, codegen/, ci/
  e2e/                   Playwright projects (web, field-mobile, ipad, portal)
  tests/                 cross-module: isolation, permission-matrix, audit-chain, sidecar-contract
  docs/                  adr/ (create now), blueprint/
```
Each of `apps/*` and `packages/*` has its own `package.json`, `exports` map and `tsconfig` (TS project references). Module code lives only in `apps/api`. UI and offline code is shared through packages, never imported across apps.

## Recommended choices (table: concern, choice, alternatives, why)
| Concern | Choice | Alternatives | Why |
|---|---|---|---|
| Field PWA shell | **Separate Vite + React SPA (`apps/field`)** with a Workbox/Serwist service worker and client-side TanStack Router | Next.js in the same app (static export or App Router); Next serwist plugin | The field app must boot with no network, from a precached static shell. App Router depends on server components, RSC payload fetches and server rendering, which do not exist offline. A Next static export would remove every reason to choose Next. Next stays right for the desktop admin app. Sharing happens through `packages/ui`, `form-renderer` and `offline-core`. |
| Portal | Vite SPA on its own origin, own session cookies and CSP | Next.js for SSR magic-link pages | No offline need, narrow surface, easiest to lock down. Matches portal/architecture.md. If the owner prefers one framework for all three, Next is acceptable for the portal only. |
| Offline store | **Dexie** over IndexedDB with a custom pull/push engine | RxDB (premium plugins), PowerSync, ElectricSQL, wa-sqlite + OPFS, TinyBase | The sync protocol is already designed (cursor pull, idempotent batch push, `sync_version`). Replication libraries would fight it. Dexie is small and mature, and has a good migration story. Revisit wa-sqlite only if SQL queries over large offline data become necessary. Do not use Dexie Cloud. |
| Offline encryption | WebCrypto AES-GCM, data key wrapped by a PIN-derived key (PBKDF2 or Argon2-wasm), non-extractable device key (ECDSA) for the `devices.public_key` binding | Plain Dexie; SQLCipher (native only) | Encryption protects a lost device, not XSS. State this in the security notes. Remote wipe needs a lock-on-next-contact policy plus a local TTL. |
| API contract | **OpenAPI from NestJS (nestjs-zod, Zod to OpenAPI) then orval (TanStack Query + Zod) in `packages/api-client`.** Shared Zod in `packages/contracts` for non-REST: sync payloads, events, manifests, form/rule/workflow schemas, errors | ts-rest (contract first); tRPC | Keeps the committed-drift CI check (STACK-03), gives an external portal and sidecar a language-neutral spec, and lets Customers and Keycloak-integrated tooling read OpenAPI. tRPC is a poor fit for external, non-TS clients. |
| Event/outbox | Postgres outbox plus polling dispatcher in `apps/worker`, publishing to BullMQ per tenant-aware queue | SNS/SQS later | One mechanism. Decide it in ADR, close the open question in arch/README. |
| Queue | **BullMQ (Redis)** for all Node jobs. Python sidecar exposes HTTP/JSON endpoints with an async job-id pattern, called by a BullMQ job (signed callback or poll). No arq, no Celery | arq in the sidecar | One queue surface, one retry/DLQ model, no cross-language job format. Update the decision text. |
| DB access | **Drizzle as query builder, hand-written SQL migrations, per-request transaction with `SET LOCAL app.tenant_id` and `FORCE RLS`** | Kysely (more SQL-honest, better with ltree and pgvector), Prisma (poor RLS and ltree support) | Kysely is a defensible alternative. Both must be wrapped in a tenant-bound repository so nothing queries outside a tenant transaction. |
| Migrations | **TS-driven SQL runner (node-pg-migrate in SQL mode, or dbmate / Atlas)**, forward-only, with a CI "apply on empty and on previous release schema" check. Drop up-down-up | Alembic (Python toolchain), drizzle-kit generate | Removes Python from the build. Alembic only makes sense if the owner explicitly wants it, in which case say so in ADR 0002 and drop the "TypeScript migrations" line. |
| Sidecar contract | JSON Schema generated from Zod in `packages/contracts` to pydantic via datamodel-codegen; contract tests in `tests/sidecar-contract`. Python tooling: uv, ruff, pytest, cyclonedx-py | Hand-written types on both sides | Honours "versioned JSON contracts". Python stays isolated to `services/sidecar`. |
| Workspace | pnpm workspaces + **Turborepo** (task cache, `--affected`) | Nx (heavier, own conventions), plain pnpm -r | Light, fits Coolify and ECS pipelines. Nx is not needed. |
| Module boundaries | **dependency-cruiser** for graph rules (ARCH-03: only `modules/x/api.ts` crosses, `platform` never imports `modules`) + ESLint `no-restricted-imports` and `eslint-plugin-boundaries` for frontend features and platform. Custom ESLint rule for hard-coded JSX strings | Nx module boundaries | Cruiser is already in ARCH-03. Keep it. Add ESLint for frontend and for the terms rule. |
| NestJS boundaries | One Nest `Module` per bounded module. Its `exports` list only a single service token (the published interface); the `api.ts` barrel re-exports types and the token. Cross-module side effects go through the outbox, not `@nestjs/event-emitter` or direct service calls inside the request transaction. Module registry loads manifests. Forbid circular imports, use `forwardRef` only with an ADR. Prefer Fastify adapter. Controllers are thin, they parse with Zod pipes | Nest CQRS | Nest DI does not enforce boundaries by itself, so the lint gate is the real enforcement. |
| Unit/integration tests | **Vitest** everywhere, using `unplugin-swc` in `apps/api` (esbuild drops `emitDecoratorMetadata`, which Nest DI needs) | Jest for the API only | One runner across the monorepo. The swc plugin is a known requirement. Add vitest `projects`. |
| DB integration | **Testcontainers-node** (Postgres with PostGIS, ltree, pgvector, Redis), one container per worker with schema/template DB cloning per test file | Shared dev database | Matches "no mocked DB". Needs a custom Postgres image with extensions, which STACK-05 already implies. |
| E2E | **Playwright** with projects: web, field (Pixel 5, iPad, WebKit), portal; `context.setOffline`; one real-device smoke (BrowserStack or equivalent) per release | Cypress | Playwright's WebKit is not Safari. Offline and storage-eviction behaviour needs real iOS. |
| Property tests | **fast-check** (replaces Hypothesis) over the pure sync model in `packages/offline-core` | none | Same intent as TESTING-07. |
| Forms/rules | JSONLogic wrapped in a shared package with a JSON-schema-validated rule set, operations allow-listed, no custom ops with side effects; evaluated identically in browser, API and worker | CEL | Single implementation avoids client/server drift. Add golden test vectors in `packages/contracts`. |
| Reports | Gotenberg driven from `apps/worker` via the `PdfRenderer` capability. Templates are server-rendered HTML (React SSR or Handlebars) with fonts and photos inlined, no outbound network | Render in `apps/api` | Matches report_engine. Keep rendering out of the API process. |
| Terms (i18n) | `packages/terms` with i18next/ICU plus the bundle cached in the offline store, shared by web, field and portal | Per-app i18n | TERMS-08 targets only one app today. |

## Offline PWA guidance
- **Design for the iOS floor.**
  - iOS has no Background Sync API, so foreground and visibility-triggered sync is the primary path. Background Sync is an Android/Chromium enhancement only.
  - Safari evicts site data after about 7 days of non-use unless the PWA is installed to the Home Screen. Document install as a deployment requirement.
  - Call `navigator.storage.persist()` and `estimate()`, and surface the result on the storage screen.
  - Test on real devices at the edge of the storage quota.
- **Sync engine.** Put it in `packages/offline-core` as a pure state machine (no DOM) so fast-check can exercise it.
  - Use a Web Locks leader so only one tab syncs.
  - Use idempotent push keyed by `batch_id` plus op id (already designed).
  - Make the Dexie schema versioned, with migrations tested against stored fixtures. Version-skew handling: a cached client must tolerate an API that moved on (`min_client_version` in the sync scope manifest, forced update, no silent drop).
- **Service worker.** Precache the app shell and PDF.js worker, with `skipWaiting` only behind an explicit update prompt, because users may be mid-inspection. Cache drawings and tiles through a size-capped, LRU, scoped manifest (Selective download). Serve photos and media via the Dexie/OPFS queue, not the HTTP cache.
- **Media.** Store blobs in IndexedDB (or OPFS where available) with a prioritised, resumable presigned upload queue (S3 multipart or tus). Compress client-side. Enforce per-device quota.
- **Auth offline.** Keycloak refresh tokens will not be valid for days offline. Use PIN login to unlock local data and the device key to authenticate re-sync, with a short grace policy for offline writes (accept the ops, reject on stale revoked device, log `sync.op_rejected`). Specify the maximum offline period and token flow in an ADR.
- **Markup.** Store annotations as vector JSON (not bitmaps) in Dexie. Konva on mobile has canvas size and memory limits (iOS about 16 MP). Render large drawings in tiles, and test the biggest realistic A0 PDF.
- **Forms/rules.** Evaluate JSONLogic offline from the cached published template version, and pin the template version per draft.
- **Clock and ids.** Client-generated UUIDv7 ids. Do not trust device clock for ordering, use server-assigned `sync_version`.
- **Observability.** Ship client error and sync-health telemetry (OPS-05) with an offline buffer.

## Required task changes (task ID, change)
- **STACK-01**: Create `docs/adr/` first (it does not exist). Add ADRs for (a) repo layout and apps split, (b) migrations tool (remove Alembic or justify it), (c) BullMQ-only queue with sidecar HTTP contract, (d) offline PWA as a Vite app, (e) API contract strategy, (f) test toolchain. Close the open queue item instead of leaving it "awaiting".
- **ARCH-01**: Add `apps/field`, `apps/portal`, `packages/{api-client,ui,terms,form-renderer,markup,offline-core,permissions,config-*}`, `turbo.json`, `tsconfig.base.json`, shared lint/test configs, Vitest with swc. Define the exact tree above in the spec, with a canonical-paths rule. Add a CI "paths lint" that rejects `backend/` and `frontend/`.
- **ARCH-03**: Extend dependency-cruiser rules to `apps/field`, `apps/portal` and `apps/web` (only `packages/*`), forbid app-to-app imports, forbid `packages/*` importing `apps/*`. Add ESLint rules for frontend features and the hard-coded-string rule. Add fixtures per rule.
- **ARCH-05, ARCH-07**: Say Testcontainers-node. Decide dispatcher transport (Postgres outbox poll to BullMQ) in the spec.
- **STACK-03**: Add `nestjs-zod`, and state the split between `packages/api-client` (REST) and `packages/contracts` (shared Zod). Add runtime Zod validation of sync responses in the field app. Make drift check also cover the sidecar JSON Schema.
- **STACK-02**: Add the sidecar adapter (HTTP client with timeout, retries, signed callbacks) and fix `Ocr`/IFC/CAD interfaces to use it. Rename `minio.adapter.ts` (decision is RustFS) or document S3-compatible naming.
- **STACK-05**: Add Vite builds for field and portal, Dockerfile or static hosting config for them (CDN origin), Python sidecar built with uv.
- **TERMS-08**: Move paths to `apps/web/src/features/settings/terms/*` and `packages/terms/src/*`. Reuse the shared offline store from `packages/offline-core` for the cached bundle, and add the field app as a consumer.
- **TERMS-01 to TERMS-03, OPS-02, OPS-03, OPS-05**: Rewrite `backend/app/...py` paths into `apps/api/src/modules/...ts`. OPS-02: BullMQ runner replaces arq. OPS-05: `reportError.ts` goes to a shared package.
- **TESTING-01 to TESTING-08**: Translate to TS: Vitest and Testcontainers-node fixtures (`apps/api/test/` or `tests/`), `fast-check` for TESTING-07 (500 runs), v8 coverage threshold in `vitest.config`, `.github/workflows/ci.yml` with the Node jobs, Playwright projects for web, field (mobile Chrome, iPad, WebKit) and portal. TESTING-05: replace up-down-up with an apply-on-previous-release check. TESTING-08: replace `backend/pyproject.toml`.
- **OFFLINE tasks (not reviewed in detail)**: move `frontend/src/modules/offline/*` to `packages/offline-core` and `apps/field/src`. Add device storage-persistence and iOS eviction acceptance criteria, `min_client_version`, and offline auth grace policy.
- **PORTAL tasks**: record the Vite-vs-Next choice and add the `apps/portal` path.
- **07-task-conventions.md and 04-code-layout.md**: replace the Python module template and tree with the TS tree above, remove Alembic and `importlinter.ini`, and state `module.toml` is now `manifest.json`. Fix the "forward-only" versus "up-down-up" wording.
- **01-decisions.md**: Update the queue decision text (BullMQ) and the ORM/migrations decision text, with an owner sign-off.

## Questions for the owner
1. **Frontend split.** Do you accept Next.js for the desktop admin app only, with the offline field PWA (and the portal) as separate Vite SPAs? This is the one place my recommendation departs from the "Next.js" decision. If you want a single Next app, say whether you accept a statically exported field route group with client-only rendering.
2. **Migrations.** Is Alembic really wanted, or should the tool be a TS-driven SQL runner? The decision text and ADR 0002 line currently disagree. Do you want forward-only or reversible migrations?
3. **Queue and sidecar.** Confirm BullMQ only, with the Python sidecar as an HTTP service and no arq or Celery.
4. **Drizzle versus Kysely** as the query builder over raw-SQL migrations (ltree, pgvector, RLS-heavy). Drizzle is fine, but this is a one-way door.
5. **Offline security.** What is the maximum offline period, and is PIN-unlock plus a device key sufficient for IRAP and SOC 2? What is the remote-wipe expectation when a device never reconnects?
6. **iOS.** Will field users install the PWA to the Home Screen (needed to avoid the 7-day eviction)? Are managed devices (MDM) available at Kaefer or Rio Tinto sites?
7. **Offline scope.** Is inspection capture plus markup the full offline scope, or must drawing packs (large PDFs, IFC) also be available offline?
8. **Portal framework.** Vite SPA or Next.js (the owner decision says only "separate build")?
9. **Monorepo tool.** Is Turborepo acceptable, or do you want plain pnpm only?
10. **Python sidecar toolchain.** Is uv-based Python acceptable in the same repo, or should the sidecar live in its own repository?
