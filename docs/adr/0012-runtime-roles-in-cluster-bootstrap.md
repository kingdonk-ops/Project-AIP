# ADR 0012: Runtime database roles are created by the cluster bootstrap, not by revisions

- **Status:** accepted
- **Date:** 2026-10-07
- **Affects:** database; DATABASE-02, TESTING-01, OPS-02, OPS-11, ARCH-05; `db/bootstrap/00_cluster.sql`

## Context

ADR 0002 names the roles `aip_owner`, `aip_app`, `aip_jobs` and `aip_readonly`. DATABASE-02's task
spec says to create them in an Alembic "roles revision" with `DO ... IF NOT EXISTS`. DATABASE-08
then made `aip_owner`, the only role that runs revisions, `NOCREATEROLE`. It is created by
`db/bootstrap/00_cluster.sql`, which a superuser runs once per cluster and database.

Roles are cluster-wide objects, not database objects. To create them from a revision,
`aip_owner` would need `CREATEROLE`. On PostgreSQL 16 that still lets it create and alter
`LOGIN` roles, so a compromised or buggy migration could mint new logins.

## Decision

- `db/bootstrap/00_cluster.sql` (superuser, idempotent) creates all four roles as `LOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, repairing any drift. It sets
  `aip_readonly` to read-only transactions by default. It revokes `CONNECT`/`TEMPORARY` on the
  database from `PUBLIC` and grants `CONNECT` to the three runtime roles.
- Passwords come only from the custom settings `aip.<role>_password`, for example
  `PGOPTIONS='-c aip.app_password=...'`, filled from the environment or the secrets manager.
  Production passes pre-hashed SCRAM verifiers, or clear text with logging off for that session.
  No password is in the repository.
- The Alembic revision `202610072200_platform_roles` stays re-runnable on any cluster. It checks,
  with `IF NOT EXISTS`, that each runtime role exists, is unprivileged and is not a member of
  `aip_owner`, and raises otherwise. Then it grants schema usage. Per-table grants come from
  `db/templates/tenant_table.sql.tpl`.
- `aip_owner` stays `NOCREATEROLE`.

## Consequences

- A new environment needs the bootstrap before `aip-db migrate`. This was already true for
  `aip_owner` and `vector`. A missing role now fails the migration with a clear message instead
  of failing later at runtime.
- Tasks that need another role, for example a dedicated audit writer (AUDIT-01), add it to the
  bootstrap and check it in their revision. Their grants stay in revisions.
- The application engine also refuses, at connect time, any login that is a superuser, has
  `BYPASSRLS` or owns objects. A mis-set `DATABASE_URL` therefore fails closed instead of
  silently skipping RLS.
