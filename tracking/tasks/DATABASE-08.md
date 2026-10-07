# DATABASE-08 — Raw-SQL migration runner (node-pg-migrate), migrator role, baseline + extensions

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (wins over the module docs: no Alembic, no `migrations/versions/`), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: [`docs/reviews/05-stack-data.md`](../../docs/reviews/05-stack-data.md) (migration and role notes)

## Spec

Make `db/migrations/` the single schema authority: forward-only plain-SQL migrations applied by node-pg-migrate as `aip_owner`, a baseline that installs the extension set, generated Kysely types and CI drift checks.

- **files**:
  - db/bootstrap/00_cluster.sql
  - db/migrations/<timestamp>_baseline_extensions.sql
  - db/templates/blank.sql
  - db/schema.snapshot.sql
  - tools/db/migrate.ts
  - tools/db/new-migration.ts
  - tools/db/lint-migrations.ts
  - tools/db/schema-snapshot.ts
  - apps/api/src/platform/db/schema.generated.ts
  - infra/docker/migrator.Dockerfile
  - tests/db/migrations.spec.ts
  - package.json (root scripts `db:migrate`, `db:new`, `db:lint`, `db:codegen`, `db:snapshot`)
- **steps**:
  - 1. Add `node-pg-migrate`, `pg`, `kysely` and `kysely-codegen`. `tools/db/migrate.ts` calls node-pg-migrate programmatically in SQL mode: directory `db/migrations`, migrations table `aip_meta.schema_migrations`, filename format `utc` (`YYYYMMDDHHmmss_slug.sql`), direction `up` only, one transaction per file, connection from `DATABASE_MIGRATOR_URL` (direct connection, never through PgBouncer). It refuses to run unless `select current_user` returns `aip_owner`. Concurrent runs are serialised by node-pg-migrate's advisory lock.
  - 2. Write `db/bootstrap/00_cluster.sql`, run once per cluster by a superuser (Testcontainers setup, compose init and the RDS bootstrap runbook). It is idempotent. It creates the `aip_owner` LOGIN role (NOSUPERUSER, NOCREATEDB, NOBYPASSRLS), makes it owner of the database and of schema `aip_meta`, runs `REVOKE CREATE ON SCHEMA public FROM PUBLIC`, and creates the `vector` extension (pgvector is not a trusted extension, so a superuser must create it). Do not create `aip_app`, `aip_dispatcher` or `aip_readonly` here: DATABASE-02 owns them.
  - 3. Write the baseline migration. It runs `CREATE EXTENSION IF NOT EXISTS` for the trusted extensions `ltree`, `pgcrypto`, `pg_trgm`, `citext` and `btree_gist`, then a `DO` block that raises `missing extension %` if any of those six (including `vector`) is absent. No PostGIS (ADR 0002: only when a module needs it). No AIP tables and no Alembic history are ported. If the owner chooses to carry AIP data over, that is a separate data-baseline task.
  - 4. Write `tools/db/lint-migrations.ts`. It fails on: a filename not matching `^\d{14}_[a-z0-9_]+\.sql$`; a non-empty `-- Down Migration` section; an explicit `BEGIN`/`COMMIT` (the runner wraps each file), unless the file starts with `-- no-transaction` (needed for `CREATE INDEX CONCURRENTLY`); a session-level `SET` (only `set_config(..., true)` is allowed); `CREATE EXTENSION` outside the baseline; `DROP TABLE`, `DROP COLUMN` or `SET NOT NULL` without a `-- contract: <expand migration filename>` comment; and any file under `db/migrations/` that is modified or deleted relative to `origin/main` (`git diff --name-status`).
  - 5. Write `tools/db/new-migration.ts`. `pnpm db:new <slug>` copies `db/templates/blank.sql` (Up and Down markers, Down left empty) to `db/migrations/<UTC timestamp>_<slug>.sql`. It rejects slugs that are not snake_case and refuses to overwrite. The tenant-table and append-only templates come from DATABASE-02 and AUDIT-01.
  - 6. Codegen and snapshot. `pnpm db:codegen` runs kysely-codegen against a freshly migrated database and writes `apps/api/src/platform/db/schema.generated.ts`. `pnpm db:snapshot` writes a normalised `pg_dump --schema-only` to `db/schema.snapshot.sql`: version and comment header lines and `SET` lines are stripped, and objects are sorted so the output is deterministic. Add a CI job that starts `pgvector/pgvector:pg16`, runs the bootstrap, migrations, codegen and snapshot, then `git diff --exit-code` and `pnpm db:lint`. This replaces "up-down-up" (TESTING-05 builds on it).
  - 7. Write `infra/docker/migrator.Dockerfile`: `node:22-alpine`, non-root user, copies only `db/`, `tools/db/` and their dependencies, entrypoint `migrate`. It runs as a one-shot task (an ECS task in AWS; a compose service the API waits on with `service_completed_successfully`).
- **acceptance**:
  - On an empty `pgvector/pgvector:pg16` container, the bootstrap followed by `pnpm db:migrate` exits 0, and `pg_extension` lists ltree, pgcrypto, pg_trgm, citext, btree_gist and vector.
  - A second `pnpm db:migrate` applies 0 migrations and exits 0.
  - Running as any role other than `aip_owner` exits 1 with `migrator must run as aip_owner`.
  - CI fails when `schema.generated.ts` or `schema.snapshot.sql` is stale, or when the lint finds a violation.
  - The repository contains no Alembic, Python migration or `migrations/versions/` paths.
- **tests**:
  - **unit**:
    - Lint `20261007120000_add_widgets.sql` with an empty Down section. Expected: no findings.
    - Lint `0001_widgets.sql`. Expected: error `invalid migration filename`.
    - Lint a file whose Down section contains `DROP TABLE widgets;`. Expected: error `down migrations are not allowed`.
    - Lint `SET search_path = x;`. Expected: error `session-level SET is forbidden; use set_config(..., true)`.
    - Lint `ALTER TABLE t DROP COLUMN c;` with no `-- contract:` comment. Expected: error `destructive change needs a contract comment`.
    - `db:new 'Add Widgets'`. Expected: exit 1 with `invalid slug`.
    - Normalise a dump containing `-- Dumped by pg_dump version 16.4`. Expected: the line is removed, and normalising the same input twice gives byte-identical output.
  - **integration**:
    - Testcontainers (`pgvector/pgvector:pg16`): bootstrap then migrate an empty DB. Expected: 1 row in `aip_meta.schema_migrations`, all six extensions present, and for a freshly created role `probe`, `has_schema_privilege('probe', 'public', 'CREATE')` is false.
    - Start two migrate processes at the same time. Expected: both exit 0 and the baseline is recorded once.
    - Add a fixture migration containing `CREATE TABLE t1(id int); SELECT 1/0;`. Expected: non-zero exit, no `schema_migrations` row for it and no table `t1`.
    - Set `DATABASE_MIGRATOR_URL` to the `postgres` superuser. Expected: exit 1 with `migrator must run as aip_owner`.
    - Run the bootstrap without the `vector` line, then migrate. Expected: the baseline fails with `missing extension vector`.
  - **e2e**:
    - Build the migrator image and run it against the compose Postgres. Expected: exit 0, `id -u` inside the image is non-zero, and the API then boots and `GET /api/v1/health` returns 200.
