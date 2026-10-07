# DATABASE-08 — Alembic env, migrator role, baseline revision + extensions
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

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
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (Alembic forward-only raw SQL in `apps/api/migrations/versions/`, roles, extensions), [0001](../../docs/adr/0001-greenfield-python-backend.md) (no AIP schema or Alembic history is imported), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if a step needs it: [`docs/reviews/05-stack-data.md`](../../docs/reviews/05-stack-data.md) (migration and role notes)

## Spec

Make `apps/api/migrations/versions/` the single schema authority: forward-only Alembic revisions written as raw SQL (`op.execute`), applied as `aip_owner`, a baseline revision that installs the extension set, a migration lint, a deterministic schema snapshot and a CI check that the migrated schema matches the declared SQLAlchemy Core tables.

- **files**:
  - db/bootstrap/00_cluster.sql
  - apps/api/alembic.ini
  - apps/api/migrations/env.py
  - apps/api/migrations/script.py.mako (blank revision template: `upgrade()` with `op.execute("""...""")`, `downgrade()` raising)
  - apps/api/migrations/versions/202610071200_baseline_extensions.py
  - apps/api/aip/platform/db/metadata.py (single `MetaData` that platform and module `tables.py` attach to)
  - apps/api/aip/platform/db/migrator/{__init__.py,run.py,new.py,lint.py,snapshot.py,schema_check.py,cli.py}
  - apps/api/pyproject.toml (add `alembic`, `asyncpg`, `sqlalchemy[asyncio]`; script `aip-db = "aip.platform.db.migrator.cli:main"`; dev `testcontainers[postgres]`)
  - db/schema.snapshot.sql (generated, committed)
  - infra/docker/migrator.Dockerfile
  - apps/api/tests/platform/db/test_migration_lint.py
  - apps/api/tests/platform/db/test_migrator.py
  - .github/workflows/ci.yml (`db` job)
- **steps**:
  - 1. Alembic config: `script_location = migrations`, `file_template = %%(rev)s_%%(slug)s`, version table `alembic_version` in schema `aip_meta` (`version_table_schema`), `transaction_per_migration = True`, no `target_metadata` (autogenerate is not used). `env.py` uses the async template on asyncpg with `DATABASE_MIGRATOR_URL` (a direct connection, never through PgBouncer), takes `pg_advisory_lock(hashtext('aip_migrations'))` before running so concurrent runs serialise, and refuses to run unless `select current_user` returns `aip_owner` (`migrator must run as aip_owner`). `aip-db migrate` = `alembic upgrade head`; there is no downgrade command.
  - 2. Write `db/bootstrap/00_cluster.sql`, run once per cluster by a superuser (testcontainers fixture, compose init and the RDS bootstrap runbook). It is idempotent. It creates the `aip_owner` LOGIN role (NOSUPERUSER, NOCREATEDB, NOBYPASSRLS), makes it owner of the database and of schema `aip_meta`, runs `REVOKE CREATE ON SCHEMA public FROM PUBLIC`, and creates the `vector` extension (pgvector is not a trusted extension, so a superuser must create it). Do not create `aip_app`, `aip_jobs` or `aip_readonly` here: DATABASE-02 owns them.
  - 3. Write the baseline revision (revision id `202610071200`, `down_revision = None`). It runs `CREATE EXTENSION IF NOT EXISTS` for the trusted extensions `ltree`, `pgcrypto`, `pg_trgm`, `citext` and `btree_gist`, then a `DO` block that raises `missing extension %` if any of those six (including `vector`) is absent. No PostGIS (ADR 0002: only when a module needs it). The schema is greenfield: nothing is derived from any existing AIP schema or Alembic history (ADR 0001).
  - 4. Write `migrator/lint.py` (`aip-db lint`), working on the Python AST and SQL strings of each file in `migrations/versions/`. It fails on: a filename not matching `^\d{12}_[a-z0-9_]+\.py$` or a `revision` that differs from the filename prefix; `downgrade()` whose body is anything other than `raise NotImplementedError("forward-only")`; `upgrade()` statements other than `op.execute(<str>)` calls (plus `with op.get_context().autocommit_block():` only around `CREATE INDEX CONCURRENTLY`); explicit `BEGIN`/`COMMIT` in SQL; a session-level `SET` (only `set_config(..., true)` is allowed); `CREATE EXTENSION` outside the baseline; `DROP TABLE`, `DROP COLUMN` or `SET NOT NULL` without a `# contract: <expand revision id>` comment; more than one head; and any file under `migrations/versions/` that is modified or deleted relative to `origin/main` (`git diff --name-status`).
  - 5. Write `migrator/new.py` (`aip-db new <slug>`): rejects slugs that are not snake_case, uses the current UTC time `YYYYMMDDHHMM` as `--rev-id`, refuses to overwrite, and calls `alembic revision -m <slug> --rev-id <id>` so the file is rendered from `script.py.mako`. The tenant-table and append-only SQL templates in `db/templates/` come from DATABASE-02 and AUDIT-01.
  - 6. Snapshot and declared-tables check. `aip-db snapshot` writes a normalised `pg_dump --schema-only` to `db/schema.snapshot.sql`: version and comment header lines and `SET`/`SELECT pg_catalog.set_config` lines are stripped and objects sorted so the output is deterministic. `aip-db check-schema` reflects the migrated database and compares it with `aip.platform.db.metadata` (tables, columns, types, nullability), ignoring schemas `aip_meta` and `procrastinate`; it prints one line per difference. Add a CI `db` job that starts `pgvector/pgvector:pg16`, runs the bootstrap, `aip-db migrate`, `aip-db snapshot` + `git diff --exit-code db/schema.snapshot.sql`, `aip-db check-schema` and `aip-db lint`. This replaces "up-down-up" (TESTING-05 builds on it).
  - 7. Write `infra/docker/migrator.Dockerfile`: `python:3.12-slim`, uv, `uv sync --frozen --no-dev`, non-root user, copies only `apps/api/pyproject.toml`, `uv.lock`, `apps/api/alembic.ini`, `apps/api/migrations/`, the `aip` package skeleton needed by `aip.platform.db.migrator` and `db/`; entrypoint `aip-db migrate`. It runs as a one-shot task (an ECS task in AWS; a compose service the API waits on with `service_completed_successfully`).
- **acceptance**:
  - On an empty `pgvector/pgvector:pg16` container, the bootstrap followed by `aip-db migrate` exits 0, and `pg_extension` lists ltree, pgcrypto, pg_trgm, citext, btree_gist and vector.
  - A second `aip-db migrate` applies 0 revisions and exits 0.
  - Running as any role other than `aip_owner` exits 1 with `migrator must run as aip_owner`.
  - CI fails when `schema.snapshot.sql` is stale, the migrated schema differs from the declared tables, or the lint finds a violation.
  - The repository contains no node-pg-migrate, Kysely, `db/migrations/` or TypeScript migration paths.
- **tests**:
  - **unit**:
    - Lint `202610071300_add_widgets.py` with `upgrade()` = one `op.execute("CREATE TABLE widgets (...)")` and the standard `downgrade()`. Expected: no findings.
    - Lint `0001_widgets.py`. Expected: error `invalid migration filename`.
    - Lint a file whose `downgrade()` runs `op.execute("DROP TABLE widgets")`. Expected: error `downgrades are not allowed`.
    - Lint `op.execute("SET search_path = x")`. Expected: error `session-level SET is forbidden; use set_config(..., true)`.
    - Lint `op.execute("ALTER TABLE t DROP COLUMN c")` with no `# contract:` comment. Expected: error `destructive change needs a contract comment`.
    - Lint `upgrade()` containing `op.create_table(...)`. Expected: error `only op.execute(raw SQL) is allowed`.
    - `aip-db new 'Add Widgets'`. Expected: exit 1 with `invalid slug`.
    - Normalise a dump containing `-- Dumped by pg_dump version 16.4`. Expected: the line is removed, and normalising the same input twice gives byte-identical output.
  - **integration** (testcontainers-python, `pgvector/pgvector:pg16`):
    - Bootstrap then migrate an empty DB. Expected: `aip_meta.alembic_version` holds `202610071200`, all six extensions are present, and for a freshly created role `probe`, `has_schema_privilege('probe', 'public', 'CREATE')` is false.
    - Start two `aip-db migrate` processes at the same time. Expected: both exit 0 and the baseline is applied once.
    - Add a fixture revision containing `CREATE TABLE t1(id int); SELECT 1/0;`. Expected: non-zero exit, `alembic_version` still at the baseline and no table `t1`.
    - Set `DATABASE_MIGRATOR_URL` to the `postgres` superuser. Expected: exit 1 with `migrator must run as aip_owner`.
    - Run the bootstrap without the `vector` line, then migrate. Expected: the baseline fails with `missing extension vector`.
    - Declare a fixture `Table("ghost", metadata, Column("id", Uuid))` that no revision creates; run `check-schema`. Expected: exit 1 with `table ghost declared but not migrated`.
  - **e2e**:
    - Build the migrator image and run it against the compose Postgres. Expected: exit 0, `id -u` inside the image is non-zero, and the API then boots and `GET /api/v1/health` returns 200.
