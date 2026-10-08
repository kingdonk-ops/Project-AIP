"""identity_login_directory

IDENTITY-01 (ADR 0005): the global, pre-tenant ``login_directory`` that maps an email domain or a
tenant slug to a tenant and (for SSO) a Keycloak IdP alias. It is read before any tenant context
exists, so it has no RLS; instead ``aip_app`` gets no table privileges at all and reads only
through the SECURITY DEFINER function ``identity_resolve_login``.

- ``tenant_id`` has no foreign key yet: ``tenants`` arrives with TENANCY-01, which adds
  ``fk_login_directory_tenant_id_tenants``.
- ``aip_app`` is created by DATABASE-02. The grant below runs only when the role already exists;
  a later roles revision must ``GRANT EXECUTE ON FUNCTION identity_resolve_login(text, citext)
  TO aip_app`` if it creates the role after this revision.
- Dev rows come from ``python -m aip.modules.identity.seeds``, not from this revision.

Revision ID: 202610080454
Revises: 202610071200
Create Date: 2026-10-08 04:54:00+00:00
"""

from alembic import op

revision: str = "202610080454"
down_revision: str | None = "202610071200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE login_directory (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      kind text NOT NULL,
      key citext NOT NULL,
      tenant_id uuid NOT NULL,
      idp_alias text NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_login_directory_kind CHECK (kind IN ('email_domain', 'tenant_slug')),
      CONSTRAINT uq_login_directory_kind_key UNIQUE (kind, key)
    );
    CREATE INDEX ix_login_directory_tenant_id ON login_directory (tenant_id);
    REVOKE ALL ON TABLE login_directory FROM PUBLIC;
    """)
    op.execute("""
    CREATE FUNCTION identity_resolve_login(p_kind text, p_key citext)
    RETURNS TABLE (tenant_id uuid, idp_alias text)
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
      SELECT d.tenant_id, d.idp_alias
      FROM public.login_directory AS d
      WHERE d.kind = p_kind AND d.key = p_key
    $fn$;
    REVOKE ALL ON FUNCTION identity_resolve_login(text, citext) FROM PUBLIC;
    """)
    op.execute("""
    DO $grants$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aip_app') THEN
        REVOKE ALL ON TABLE login_directory FROM aip_app;
        GRANT EXECUTE ON FUNCTION identity_resolve_login(text, citext) TO aip_app;
      END IF;
    END
    $grants$;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
