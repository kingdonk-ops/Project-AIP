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
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, repairing any drift. It also
  sets `default_transaction_read_only` for `aip_readonly`, but only as a convenience: the role can
  switch it off. What keeps `aip_readonly` read-only is that it is granted nothing but `SELECT`.
  It revokes `CONNECT`/`TEMPORARY` on the
  database from `PUBLIC` and grants `CONNECT` to the three runtime roles.
- Passwords come only from the custom settings `aip.<role>_password`, for example
  `PGOPTIONS='-c aip.app_password=...'`, filled from the environment or the secrets manager.
  Production passes pre-hashed SCRAM verifiers, or clear text with logging off for that session.
  No password is in the repository.
- The Alembic revision `202610072200_platform_roles` stays re-runnable on any cluster. It checks,
  in plain SQL (no `DO` block: those are reserved for the baseline), that each runtime role
  exists, is unprivileged and is not a member of `aip_owner`, and fails otherwise. Then it grants schema usage. Per-table grants come from
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

## Amendment (SECURITY-13, 2026-10-24): RLS is advisory for roles that run arbitrary SQL

The Decision above (and the original `00_cluster.sql` comment) said `aip_readonly` is "still
subject to RLS", implying RLS bounds what the reporting login can read. That is not true for a role
that runs arbitrary SQL. Tenant isolation keys on `current_setting('app.tenant_id', true)`, and any
role can set that GUC with `set_config`. So RLS stops a role only from reading *another* tenant
while it is bound to the first; it does not stop a reporting user from iterating every tenant id and
reading each tenant's rows in turn. For such a role RLS is **advisory**: a correctness guard for
honest, tenant-scoped sessions, not a confidentiality boundary against the role itself.

Confidentiality against `aip_readonly` therefore comes from **what it is granted**, not from RLS:

- `aip_readonly` holds no SELECT on the session, auth and PII tables (`user_session`, `app_user`,
  `auth_event`, `audit_log`, `security_audit_events`, `breach_incidents`). Review 11 M3.
- Reporting is served by the `reporting` schema: one security-barrier view per table exposing only
  non-PII columns. The views are owned by `aip_owner` and are not `security_invoker`, so base-table
  access runs with the owner's privileges while the owner's FORCE RLS still filters by
  `app.tenant_id` — a reporting session sees only the tenant it set, and never a PII column.

The same reasoning applies to any future role that can run arbitrary SQL: grant it the narrowest set
of tables or views it needs and treat RLS as defence in depth, not as the isolation boundary.
