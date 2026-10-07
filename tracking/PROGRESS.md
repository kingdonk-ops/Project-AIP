# Progress

Board: [BOARD.md](BOARD.md) · Next task: `python3 tools/next_task.py` · Owner questions: [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md)

## Milestones

| Milestone | Goal | Status |
|---|---|---|
| Setup | Blueprint evaluated by specialist panel, split into agent-sized files, tracking in place | done |
| M0 | Walking skeleton: monorepo, Postgres + RLS, tenant context, sign-in, one register, deploy to staging | todo |
| P0 | Foundations and proof of isolation | todo |
| R1 | "Kaefer live": cut-down P1 on the new platform (ADR 0007) | not yet broken into tasks |
| P2–P4 | See [06-build-order.md](../docs/blueprint/06-build-order.md) | not yet broken into tasks |

Later phases get tasks **just in time**. When the current phase is about 70% done, the `PLAN-*`
task on the board generates the next phase's task files from its module docs.

## Log

<!-- newest first: YYYY-MM-DD · TASK-ID · PR · one-sentence outcome -->
- 2026-10-07 · OPS-04 · #15 · `/api/v1/health/live` (no dependencies) and `/api/v1/health/ready` (Postgres `select 1`, Redis `PING`, `alembic_version` vs script head, 2 s each, 503 naming the failing check), an outermost `RequestIdMiddleware` (safe `X-Request-ID` or UUIDv7, shared with the ARCH-04 context), structlog JSON logs on stdout with stdlib/uvicorn routed through them and `request_id`/`tenant_id` on every request line, a recursive PII/credential scrubber run before rendering, and OTLP tracing for FastAPI/SQLAlchemy/Redis when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; the compose e2e probe waits for STACK-05's `infra/docker-compose.yml`.
- 2026-10-07 · ARCH-03 · #11 · Module boundaries are a CI gate: import-linter contracts `no-deep-module-import` (custom `module_public_api`) and `platform-never-imports-modules`, `check_manifests.py`, `check_layout.py` and shared `@aip/config-eslint` boundaries (apps never import apps), run in a `boundaries` job and `make check`.

- 2026-10-07 · STACK-02 · #12 · `aip.platform.capabilities`: `ObjectStore`/`PdfRenderer`/`Sealer`/`Ocr`/`IdentityProvider` protocols, env-only `CapabilitySettings` (SecretStr creds), `get_object_store()` (`OBJECT_STORE=s3|minio`, aioboto3, SSE-KMS on puts and signed presigned-PUT headers) and `get_pdf_renderer()` (Gotenberg via httpx, 30 s timeout, 25 MB cap), `tenant_key()`, `parse_adapter_config()` rejecting secret-like keys, and startup failing on an unknown adapter; one conformance suite runs against RustFS and LocalStack (Testcontainers) plus a Gotenberg render-store-download test.
- 2026-10-07 · STACK-03 · #13 · `tools/codegen/export_openapi.py` writes a byte-stable `packages/api-client/openapi.json` (operation ids `<tag>_<function>`, health now a `HealthResponse` model); `pnpm --filter api-client generate` builds openapi-typescript types and orval TanStack Query hooks with an `@generated` header, `tools/ci/check_generated_header.py` and `tools/ci/check_client_drift.sh` fail CI on hand edits or drift (new `api-client` job), and `apps/web` renders the status from `usePlatformHealth()`, covered by Playwright + axe in `e2e/web` (new `e2e` job).
- 2026-10-07 · REVIEW-09 · (this PR) · Tablet hand-over signing reviewed: client picks name + own PIN on the inspector's tablet (`aal1`); hold points need the client's own key or phone (`aal2`) unless the client agrees in writing; witness-note + portal confirmation fallback. ADR 0010 amendment and tasks IDENTITY-08, APPROVALS-07, FIELD-01 proposed, waiting on owner questions 12–16.
- 2026-10-07 · ARCH-04 · #7 · Request context (tenant, project, actor, asset scope) set by middleware on every request; default resolvers deny everyone; missing context returns 401; test-only `/_debug/context`.
- 2026-10-07 · ARCH-02 · #8 · Module registry loads manifests, checks dependencies and mounts routers in order; `GET /api/v1/modules` and a generated module map.
- 2026-10-07 · DATABASE-08 · #9 · `apps/api/migrations/versions/` is the single schema authority: async Alembic env (asyncpg, `aip_meta.alembic_version`, advisory lock, refuses any role but `aip_owner`), idempotent `db/bootstrap/00_cluster.sql`, baseline `202610071200` installing ltree/pgcrypto/pg_trgm/citext/btree_gist and asserting vector, `aip-db` CLI (migrate, new, lint, snapshot, check-schema), committed `db/schema.snapshot.sql`, non-root migrator image, and a CI `db` job plus a pgvector service container for the Python tests; SECURITY-01 marked done (PR #6).
- 2026-10-07 · SECURITY-01 · (PR pending) · `docs/security/threat-model.md` covers the six required threat areas (assets, STRIDE threats, ADR-cited controls, residual risk, open items keyed to the security review's top risks) and `docs/security/provenance-log.md` records AIP as not read or copied and no OpenConstructionERP viewed yet (legal advice `LEGAL-TBD`), enforced by stdlib `tools/ci/check_security_docs.py` in CI `docs` job and `make check-docs`; STACK-01 marked done (PR #5).
- 2026-10-07 · STACK-01 · (PR pending) · ADR statuses verified against owner answers (0001–0005, 0009, 0010 accepted; 0006–0008 owner to confirm), errata block appended to `01-decisions.md`, `docs/stack/versions.md` with `.python-version` 3.12 / `.nvmrc` 22 pins from the lockfiles, and stdlib `tools/ci/check_adrs.py` lint wired into CI (`docs` job) and `make check`.
- 2026-10-07 · ARCH-01 · (PR pending) · ADR 0004 skeleton in place: uv workspace with FastAPI `aip` package (health route, `ModuleManifest`, `_template` module), `tools/new_module.py` scaffolder, pnpm workspace with a Vite + React + TanStack Router web shell, `make check` and CI.
- 2026-10-07 · IDENTITY-07 (spec) · — · Sign-off assurance decided (ADR 0010): one quick check at signing, per-tenant minimum, countersign fallback; APPROVALS-02 wired to it.
- 2026-10-07 · DOCS-01 · #1 · Owner chose Python backend, AIP code not used: ADRs 0001–0007 revised; 44 M0 specs converted to FastAPI/SQLAlchemy/Alembic/Procrastinate + Vite; depends-on synced from board; shared fixtures and permission-code rule fixed.
- 2026-10-07 · DOCS-01 · #1 · Board of 103 tasks in waves (M0 = waves 0–5); 44 new P0 specs for identity, access, projects, design, audit, approvals, uploads, ops, ENT-01 and PLAN-R1; stack decision review (08) added, rebuild-vs-Python question open.
- 2026-10-07 · SETUP · — · Blueprint split into 64 module folders, 559 page specs and 59 task files; seven-specialist review panel run; ADRs recorded; board, agent workflow and CI board check created.
