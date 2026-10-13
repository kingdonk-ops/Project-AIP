"""tenancy_real_customer_flag

OPS-11 (ADR 0007): the Coolify demo holds synthetic data only. ``tenants.is_real_customer`` marks
a tenant that carries real customer data (false for every fixture and demo tenant), and
``tenancy_has_real_customer()`` lets the API refuse to start in ``AIP_ENV=demo`` when any tenant
has it set. The function runs before any tenant is bound, so, like the session lookups, it runs as
the owner under a SELECT-only owner policy limited to real-customer rows and returns a single
boolean, nothing else.

Revision ID: 202610131600
Revises: 202610131500
Create Date: 2026-10-13 16:00:00+00:00
"""

from alembic import op

revision: str = "202610131600"
down_revision: str | None = "202610131500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenants ADD COLUMN is_real_customer boolean NOT NULL DEFAULT false")

    # contract: 202610131600 owner-only SELECT policy for the SECURITY DEFINER check below (FORCE
    # RLS binds the owner too). It shows the owner only real-customer rows, which is all the check
    # needs; with no tenant bound the owner still sees no demo or fixture tenant. aip_app is
    # unaffected.
    op.execute(
        "CREATE POLICY real_customer_check ON tenants FOR SELECT TO aip_owner "
        "USING (is_real_customer)"
    )

    # contract: 202610131600 SECURITY DEFINER: the demo start-up guard runs before any tenant is
    # bound and must see every tenant; it returns only whether a real-customer tenant exists.
    op.execute("""
    CREATE FUNCTION tenancy_has_real_customer()
    RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
      SELECT EXISTS (SELECT 1 FROM tenants WHERE is_real_customer AND deleted_at IS NULL)
    $$;

    REVOKE ALL ON FUNCTION tenancy_has_real_customer() FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION tenancy_has_real_customer() TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
