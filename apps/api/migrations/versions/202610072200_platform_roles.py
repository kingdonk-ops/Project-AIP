"""platform_roles

DATABASE-02 / ADR 0002 / ADR 0012: the runtime roles aip_app, aip_jobs and aip_readonly.

Roles are cluster objects, so db/bootstrap/00_cluster.sql (run by a superuser) creates them;
aip_owner has no CREATEROLE. This revision is re-runnable on any cluster and plain SQL (DO blocks
are reserved for the baseline). It refuses to continue unless each role exists (the ::regrole
cast fails with "role ... does not exist"), can log in, is not privileged (no SUPERUSER,
CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS) and cannot become aip_owner. Then it lets the
roles use the public schema and lets aip_app read the applied revision for the readiness probe.
Table grants come from db/templates/tenant_table.sql.tpl; aip_jobs gets its grants with
OPS-02 / ARCH-05.

Revision ID: 202610072200
Revises: 202610071200
Create Date: 2026-10-07 22:00:00+00:00
"""

from alembic import op

revision: str = "202610072200"
down_revision: str | None = "202610071200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    SELECT 'aip_app'::regrole, 'aip_jobs'::regrole, 'aip_readonly'::regrole;
    -- One output row (and so a failing cast whose error names the roles) only if a role is wrong.
    SELECT (
      'runtime role is privileged, cannot log in or can become aip_owner; rerun '
      || 'db/bootstrap/00_cluster.sql as a superuser: ' || string_agg(rolname, ', ')
    )::int
    FROM pg_roles
    WHERE rolname IN ('aip_app', 'aip_jobs', 'aip_readonly')
      AND (NOT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication
           OR rolbypassrls OR pg_has_role(oid, 'aip_owner', 'MEMBER'))
    HAVING count(*) > 0;
    """)
    op.execute("""
    GRANT USAGE ON SCHEMA public TO aip_app, aip_jobs, aip_readonly;
    -- The readiness probe (OPS-04) compares the applied revision with the build's head.
    GRANT USAGE ON SCHEMA aip_meta TO aip_app;
    GRANT SELECT ON aip_meta.alembic_version TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
