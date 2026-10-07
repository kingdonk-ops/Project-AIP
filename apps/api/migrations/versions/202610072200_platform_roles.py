"""platform_roles

DATABASE-02 / ADR 0002 / ADR 0012: the runtime roles aip_app, aip_jobs and aip_readonly.

Roles are cluster objects, so db/bootstrap/00_cluster.sql (run by a superuser) creates them;
aip_owner has no CREATEROLE. This revision is re-runnable on any cluster: it checks, with
IF NOT EXISTS, that each role exists, can log in, is not privileged (no SUPERUSER, CREATEDB,
CREATEROLE, REPLICATION or BYPASSRLS) and cannot become aip_owner, and refuses to continue
otherwise. Then it lets the roles use the public schema and lets aip_app read the applied
revision for the readiness probe. Table grants come from
db/templates/tenant_table.sql.tpl; aip_jobs gets its grants with OPS-02 / ARCH-05.

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
    DO $$
    DECLARE
      r text;
    BEGIN
      FOREACH r IN ARRAY ARRAY['aip_app', 'aip_jobs', 'aip_readonly']
      LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
          RAISE EXCEPTION 'missing role %: run db/bootstrap/00_cluster.sql as a superuser', r;
        END IF;
        IF EXISTS (
          SELECT 1 FROM pg_roles
          WHERE rolname = r
            AND (NOT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication
                 OR rolbypassrls)
        ) THEN
          RAISE EXCEPTION 'role % is privileged or cannot log in; rerun the bootstrap', r;
        END IF;
        IF pg_has_role(r, 'aip_owner', 'MEMBER') THEN
          RAISE EXCEPTION 'role % must not be a member of aip_owner', r;
        END IF;
      END LOOP;
    END
    $$;
    """)
    op.execute("""
    GRANT USAGE ON SCHEMA public TO aip_app, aip_jobs, aip_readonly;
    -- The readiness probe (OPS-04) compares the applied revision with the build's head.
    GRANT USAGE ON SCHEMA aip_meta TO aip_app;
    GRANT SELECT ON aip_meta.alembic_version TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
