"""access_scope_rls

ACCESS-03: enforce project scope in Postgres as well as in ``PolicyService``.

- ``access_user_scope`` denormalises each live tenant/project ``role_assignment`` into one row the
  RLS predicate can read without a join. It comes from ``db/templates/tenant_table.sql.tpl`` (uuid
  PK, tenant_id, timestamps, FORCE RLS with the fail-closed NULLIF policy). It is maintained only
  by the ``access_user_scope_sync`` trigger on ``role_assignment`` (a soft-delete of the assignment
  removes the row), so application code never writes it: the template's INSERT/UPDATE grants are
  kept for the trigger (which runs SECURITY INVOKER, as the role writing ``role_assignment``) and a
  DELETE grant is added for the same reason. The migration backfills it from existing assignments.
- ``app_user_id()`` / ``app_principal_kind()`` read the transaction-local settings that
  ``with_principal`` sets (ADR 0002 keeps ``app.tenant_id`` the same way).
  ``access_project_visible(p_project)`` is the
  RLS predicate: true for a ``system`` or ``api_client`` principal (tenant-wide by design), or when
  the current user has a live ``access_user_scope`` row for the tenant or that project whose
  validity window covers ``now()``. Validity is checked here, at query time.
- A RESTRICTIVE policy ``project_scope`` on ``projects`` adds ``access_project_visible(id)`` on top
  of the permissive tenant-isolation policy (they combine with AND). ``sites`` stays tenant-scoped:
  it carries no ``project_id`` in the implemented schema and is shared reference data (ADR 0037).
  Future tables with a ``project_id`` record column copy ``db/templates/project-scoped-policy.sql``.

Revision ID: 202610191000
Revises: 202610181200
Create Date: 2026-10-19 10:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610191000"
down_revision: str | None = "202610181200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # role_assignment gains the tenant-safe target for access_user_scope's FK.
    op.execute(
        "ALTER TABLE role_assignment"
        " ADD CONSTRAINT uq_role_assignment_id_tenant_id UNIQUE (id, tenant_id)"
    )

    op.execute(
        render_template(
            "tenant_table",
            table="access_user_scope",
            columns=(
                "user_id uuid NOT NULL, scope_kind text NOT NULL, project_id uuid NULL, "
                "role_assignment_id uuid NOT NULL, "
                "valid_from timestamptz NOT NULL, valid_to timestamptz NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE access_user_scope
      ADD CONSTRAINT ck_access_user_scope_kind CHECK (scope_kind IN ('tenant', 'project')),
      ADD CONSTRAINT ck_access_user_scope_project CHECK (
        (scope_kind = 'tenant' AND project_id IS NULL)
        OR (scope_kind = 'project' AND project_id IS NOT NULL)
      ),
      ADD CONSTRAINT uq_access_user_scope_role_assignment_id UNIQUE (role_assignment_id),
      -- Tenant-safe references: a scope row can never point across tenants.
      ADD CONSTRAINT fk_access_user_scope_role_assignment
        FOREIGN KEY (role_assignment_id, tenant_id)
        REFERENCES role_assignment (id, tenant_id) ON DELETE CASCADE,
      ADD CONSTRAINT fk_access_user_scope_project
        FOREIGN KEY (project_id, tenant_id) REFERENCES projects (id, tenant_id);

    CREATE INDEX ix_access_user_scope_tenant_id_user_id_project_id
      ON access_user_scope (tenant_id, user_id, project_id);

    -- The trigger runs as the role writing role_assignment (aip_app in the app), so aip_app also
    -- needs DELETE here. It is still trigger-maintained; nothing else writes it.
    GRANT DELETE ON access_user_scope TO aip_app;
    """)

    # Principal-reading helpers and the project-visibility predicate (all STABLE: safe in policies).
    op.execute("""
    CREATE FUNCTION app_user_id() RETURNS uuid
      LANGUAGE sql STABLE
      AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$;

    CREATE FUNCTION app_principal_kind() RETURNS text
      LANGUAGE sql STABLE
      AS $$ SELECT NULLIF(current_setting('app.principal_kind', true), '') $$;

    CREATE FUNCTION access_project_visible(p_project uuid) RETURNS boolean
      LANGUAGE sql STABLE
      AS $$
        SELECT app_principal_kind() IN ('system', 'api_client')
          OR EXISTS (
            SELECT 1 FROM access_user_scope s
            WHERE s.user_id = app_user_id()
              AND (s.scope_kind = 'tenant' OR s.project_id = p_project)
              AND s.valid_from <= now()
              AND (s.valid_to IS NULL OR s.valid_to > now())
          )
      $$;
    """)

    # The trigger that maintains access_user_scope from role_assignment. SECURITY INVOKER: it runs
    # as the role that wrote role_assignment, which already holds app.tenant_id, so the scope row's
    # RLS WITH CHECK (tenant_id = app.tenant_id) is satisfied for the row it writes.
    op.execute("""
    CREATE FUNCTION access_user_scope_sync() RETURNS trigger
      LANGUAGE plpgsql
      AS $$
      BEGIN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN
          DELETE FROM access_user_scope WHERE role_assignment_id = OLD.id;
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE')
           AND NEW.deleted_at IS NULL
           AND NEW.scope_type IN ('tenant', 'project') THEN
          INSERT INTO access_user_scope
            (id, tenant_id, user_id, scope_kind, project_id,
             role_assignment_id, valid_from, valid_to)
          VALUES
            (gen_random_uuid(), NEW.tenant_id, NEW.user_id, NEW.scope_type, NEW.project_id,
             NEW.id, NEW.valid_from, NEW.valid_to);
        END IF;
        RETURN NULL;
      END
      $$;

    CREATE TRIGGER trg_access_user_scope_sync
      AFTER INSERT OR UPDATE OR DELETE ON role_assignment
      FOR EACH ROW EXECUTE FUNCTION access_user_scope_sync();
    """)

    # Backfill from existing assignments. In this greenfield build role_assignment is empty when
    # this revision runs (ACCESS-02 seeds roles and assignments at runtime, after migrations), so
    # this is a safety no-op today. It is also RLS-safe: the migrator (aip_owner) is NOBYPASSRLS
    # and FORCE-bound with no app.tenant_id, so the SELECT yields no rows and nothing is written
    # (a DO loop setting app.tenant_id per tenant is not available: the lint bans DO blocks and
    # session SET outside the baseline). Any assignment present at write time is denormalised by
    # the trg_access_user_scope_sync trigger instead.
    op.execute("""
    INSERT INTO access_user_scope
      (id, tenant_id, user_id, scope_kind, project_id, role_assignment_id, valid_from, valid_to)
    SELECT gen_random_uuid(), ra.tenant_id, ra.user_id, ra.scope_type, ra.project_id,
           ra.id, ra.valid_from, ra.valid_to
    FROM role_assignment ra
    WHERE ra.deleted_at IS NULL AND ra.scope_type IN ('tenant', 'project');
    """)

    # Restrictive project-scope policy on projects (combines with tenant_isolation by AND).
    op.execute("""
    CREATE POLICY project_scope ON projects
      AS RESTRICTIVE
      FOR ALL
      TO aip_app
      USING (access_project_visible(id))
      WITH CHECK (access_project_visible(id));

    CREATE INDEX ix_projects_tenant_id_id ON projects (tenant_id, id);
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
