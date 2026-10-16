# DATABASE-07 — Isolation test generator across all tables

<!-- hand-edited: converted to the Python backend per ADR 0001 and narrowed with the owner (2026-10-16): route IDOR moved to TESTING-04, raw-key checks and key-builder Testcontainers tests to TESTING-03, up-down-up is TESTING-05 -->

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, STACK-03, TESTING-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (FORCE RLS, roles)

## Why this was narrowed

TESTING-02 already fails CI when a table lacks `tenant_id` or RLS (a static guard). This task adds
the behavioural proof that each table's policy really isolates tenants, generated from the
catalogue so new tables inherit it. The route half (GET `/{id}` as tenant A with B's id gives 404)
is TESTING-04's generated IDOR suite; the Redis/S3 key checks are TESTING-03's; the up-down-up
migration test is TESTING-05. The compose runtime-role passwords (a DATABASE-02 carry-forward) are
already in place: the stack connects as `aip_app` and `aip_jobs`.

## Spec

Generate a cross-tenant isolation test for every tenant-scoped table, so new tables inherit
coverage and a table without a working policy fails CI.

- **files**:
  - apps/api/tests/isolation/test_rls_generated.py (the generated cases)
  - apps/api/tests/isolation/generator.py (catalogue reader, row seeder, results)
  - apps/api/tests/isolation/overrides.toml (per-table seed values and exceptions, each with a reason)
  - apps/api/tests/arch/test_tenant_setting_boundary.py, apps/api/tests/arch/test_db_engine_boundary.py
  - .github/workflows/ci.yml (upload the results artefact)
- **steps**:
  - 1. Read every table with a `tenant_id` column in `public` from `pg_catalog` on the migrated database.
  - 2. Per table: seed one row for tenant A and one for B as the superuser (FKs and triggers off via `session_replication_role = replica`), with values generated from column types and overridden per table where a CHECK needs a specific value. Then, as `aip_app` (refused if superuser, BYPASSRLS or the table owner) with tenant A set, each probe rolled back: A's row is visible; B's row is invisible by id, in a full scan and in every child partition; UPDATE and DELETE of B's row by id affect 0 rows; an unqualified UPDATE or DELETE touches at most A's row; A's row can be neither moved nor copied into tenant B. A missing grant counts as isolation for that command; a table `aip_app` cannot SELECT fails unless `overrides.toml` sets `no_app_select` with a reason and `aip_app` holds no write grant on it.
  - 3. A table that cannot be seeded, or is skipped, without an `overrides.toml` entry that has a `reason` fails the run.
  - 4. Write per-table results to `isolation-results.json` (`AIP_ISOLATION_RESULTS` path) and upload it from CI as evidence.
  - 5. Carried forward from DATABASE-02: a static test that no `app.tenant_id` string appears in `aip/` outside `aip/platform/db/session.py`; the engine-boundary arch test resolves aliased imports (`import asyncpg as pg`, `from sqlalchemy.ext.asyncio import create_async_engine as mk`).
- **acceptance**:
  - A table whose policy lets other tenants' rows through fails CI with "cross-tenant read returned rows"; a table with RLS but no policy fails with "own row is not visible".
  - The artefact lists per-table results.
- **tests**:
  - **unit**: the generator emits one case per catalogue table (a fixture of 3 tables gives 3 cases); a table without an exception reason is reported.
  - **integration**: a fixture table with RLS but a permissive policy fails with "cross-tenant read returned rows"; with the real schema, every generated case passes.
