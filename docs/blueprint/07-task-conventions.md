# Task conventions (definition of done)

Every agent follows these on every task. Where a line conflicts with an ADR in `docs/adr/`, the ADR wins (e.g. Alembic revisions live in `apps/api/migrations/versions/` and are forward-only — ADR 0002).

- **task conventions**:
  - Branch per task from main, named phase/module-short-description (e.g. p1/inspections-hold-points); small PRs, one module folder plus at most one migration.
  - Tests first: write failing tests before code, run against real Postgres via Testcontainers with no mocked database. Port AIP behaviour as golden tests before reimplementing it.
  - Every new table has tenant_id, uuid key, timestamps, soft delete (except append-only tables) and FORCE ROW LEVEL SECURITY. Migrations are forward-only Alembic raw SQL from templates.
  - Each module exposes only its published interface and domain events. Boundaries are enforced by lint in CI, and cross-module table access is forbidden.
  - All user-facing strings use terminology keys with en-AU defaults, and workflow logic uses stable internal codes. Never hard-code labels or status names.
  - Authorisation goes through the single policy service and RLS, deny by default. Each module adds permissions to the catalogue and generates matrix and IDOR tests.
  - Rules and form logic use JSONLogic. Anything that touches files goes through the upload pipeline. Any AI call goes through the AI gateway.
  - Definition of done: tests green in CI including isolation and permission tests, migration reviewed, OpenAPI client and permission catalogue regenerated without drift, audit events emitted, docs and ADR updated, security checks passed, and the change demonstrated on staging.
  - Mark each task as extend, harden or port from AIP, and cite the AIP phase or spec it carries over so parity is checkable.
  - Do not build removed modules (cost_items, cases) and strip their hooks. OpenConstructionERP (AGPL) is a feature reference only, so copy no code.
