"""ops_active_tenant_ids

OPS-13 (ADR 0032): the scheduled-job trigger (``python -m aip.modules.ops.schedule enqueue <job>
--all-tenants``) must enqueue one job per active tenant, but the runtime role cannot list tenants
(RLS on ``tenants``). This adds the narrowest read that allows it:

- policy ``scheduler_list_active`` lets ``aip_owner`` SELECT active tenants only while
  ``aip.scheduler_list_active`` is ``on``, which only the function below sets (``set_config``
  local to the transaction, switched off again before it returns). Outside it the owner still
  sees no tenants with no tenant set: FORCE RLS keeps binding it, as TENANCY-01 requires;
- the SECURITY DEFINER function ``ops_active_tenant_ids()``, owned by ``aip_owner``, returns only
  the ids of active tenants, in id order; EXECUTE goes to ``aip_app`` alone.

Revision ID: 202610161800
Revises: 202610161400
Create Date: 2026-10-16 18:00:00+00:00
"""

from alembic import op

revision: str = "202610161800"
down_revision: str | None = "202610161400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE POLICY scheduler_list_active ON tenants FOR SELECT TO aip_owner
      USING (status = 'active'
             AND current_setting('aip.scheduler_list_active', true) = 'on');
    """)
    # contract: 202610161800 - SECURITY DEFINER on purpose (ADR 0032): the scheduler's only way to
    # list tenants; owned by aip_owner, fixed search_path, returns ids only, EXECUTE to aip_app.
    op.execute("""
    CREATE FUNCTION ops_active_tenant_ids()
    RETURNS SETOF uuid
    LANGUAGE plpgsql
    VOLATILE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
    BEGIN
      -- The flag the owner-only policy needs; transaction-local, and switched off again below.
      PERFORM set_config('aip.scheduler_list_active', 'on', true);
      RETURN QUERY SELECT t.id FROM public.tenants AS t WHERE t.status = 'active' ORDER BY t.id;
      PERFORM set_config('aip.scheduler_list_active', 'off', true);
    END
    $fn$;
    REVOKE ALL ON FUNCTION ops_active_tenant_ids() FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION ops_active_tenant_ids() TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
