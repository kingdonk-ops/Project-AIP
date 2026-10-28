"""access_teams

ACCESS-04: teams, team membership and roles assigned to a whole team.

- ``team`` and ``team_member`` come from ``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id,
  timestamps, soft delete, FORCE RLS with the fail-closed NULLIF policy). Deletes are soft, so
  ``aip_app`` loses the template's DELETE grant. A team's name is unique per tenant and project
  among live rows, case-insensitively, with every tenant-level team (``project_id`` NULL) in one
  bucket. A user is a live member of a team at most once. Every reference carries ``tenant_id``.
- ``role_assignment.user_id`` becomes nullable: a ``team`` assignment names the team and no user
  (its members hold the role), every other scope names a user. ``ck_role_assignment_scope`` is
  replaced to say so, and a team assignment carries no ``project_id`` (it is the team's). One live
  assignment per team and role (``uq_role_assignment_team_live``).
- ``access_user_scope`` (ACCESS-03, ADR 0037) gains ``team_member_id``: a team assignment keeps one
  scope row per live member, scoped to the team's project (``tenant`` when the team has none). The
  ``role_assignment`` trigger now also expands team assignments, and a new trigger on
  ``team_member`` adds or removes a member's rows as the membership changes. Both stay SECURITY
  INVOKER, as in ACCESS-03. Rows are unique per (assignment, user) instead of per assignment.

Revision ID: 202610291000
Revises: 202610281500
Create Date: 2026-10-29 10:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610291000"
down_revision: str | None = "202610281500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="team",
            columns=(
                "organisation_id uuid NULL, project_id uuid NULL, name text NOT NULL, "
                "team_type text NOT NULL, scim_group_id text NULL, created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE team
      ADD CONSTRAINT uq_team_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_team_team_type CHECK (team_type IN ('internal', 'subcontractor', 'client')),
      ADD CONSTRAINT ck_team_name CHECK (length(btrim(name)) BETWEEN 1 AND 120),
      ADD CONSTRAINT fk_team_organisation_id_tenant_id_organisations
        FOREIGN KEY (organisation_id, tenant_id) REFERENCES organisations (id, tenant_id),
      ADD CONSTRAINT fk_team_project_id_tenant_id_projects
        FOREIGN KEY (project_id, tenant_id) REFERENCES projects (id, tenant_id),
      ADD CONSTRAINT fk_team_created_by_tenant_id_app_user
        FOREIGN KEY (created_by, tenant_id) REFERENCES app_user (id, tenant_id);

    -- One live team per name in a project; every tenant-level team shares one bucket.
    CREATE UNIQUE INDEX uq_team_live_name
      ON team (tenant_id, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid),
               lower(name))
      WHERE deleted_at IS NULL;
    CREATE UNIQUE INDEX uq_team_tenant_id_scim_group_id
      ON team (tenant_id, scim_group_id) WHERE scim_group_id IS NOT NULL AND deleted_at IS NULL;
    CREATE INDEX ix_team_tenant_id_project_id ON team (tenant_id, project_id);

    REVOKE DELETE ON team FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="team_member",
            columns=(
                "team_id uuid NOT NULL, user_id uuid NOT NULL, source text NOT NULL, "
                "created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE team_member ALTER COLUMN source SET DEFAULT 'manual';
    ALTER TABLE team_member
      ADD CONSTRAINT uq_team_member_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_team_member_source CHECK (source IN ('manual', 'scim')),
      ADD CONSTRAINT fk_team_member_team_id_tenant_id_team
        FOREIGN KEY (team_id, tenant_id) REFERENCES team (id, tenant_id),
      ADD CONSTRAINT fk_team_member_user_id_tenant_id_app_user
        FOREIGN KEY (user_id, tenant_id) REFERENCES app_user (id, tenant_id),
      ADD CONSTRAINT fk_team_member_created_by_tenant_id_app_user
        FOREIGN KEY (created_by, tenant_id) REFERENCES app_user (id, tenant_id);

    CREATE UNIQUE INDEX uq_team_member_live
      ON team_member (team_id, user_id) WHERE deleted_at IS NULL;
    CREATE INDEX ix_team_member_tenant_id_user_id ON team_member (tenant_id, user_id);

    REVOKE DELETE ON team_member FROM aip_app;
    """)

    # role_assignment: a team assignment names a team and no user; every other scope a user.
    op.execute("""
    ALTER TABLE role_assignment ALTER COLUMN user_id DROP NOT NULL;
    ALTER TABLE role_assignment DROP CONSTRAINT ck_role_assignment_scope;
    ALTER TABLE role_assignment
      ADD CONSTRAINT ck_role_assignment_scope CHECK (
        (scope_type = 'tenant' AND user_id IS NOT NULL AND project_id IS NULL
            AND team_id IS NULL AND asset_path IS NULL)
        OR (scope_type = 'project' AND user_id IS NOT NULL AND project_id IS NOT NULL
            AND team_id IS NULL AND asset_path IS NULL)
        OR (scope_type = 'team' AND user_id IS NULL AND team_id IS NOT NULL
            AND project_id IS NULL AND asset_path IS NULL)
        OR (scope_type = 'asset_subtree' AND user_id IS NOT NULL AND asset_path IS NOT NULL
            AND team_id IS NULL)
      ),
      ADD CONSTRAINT fk_role_assignment_team_id_tenant_id_team
        FOREIGN KEY (team_id, tenant_id) REFERENCES team (id, tenant_id);

    CREATE UNIQUE INDEX uq_role_assignment_team_live
      ON role_assignment (tenant_id, team_id, role_id)
      WHERE deleted_at IS NULL AND scope_type = 'team';
    CREATE INDEX ix_role_assignment_tenant_id_team_id ON role_assignment (tenant_id, team_id);
    """)

    # access_user_scope: one row per live member of a team assignment.
    op.execute("""
    ALTER TABLE access_user_scope ADD COLUMN team_member_id uuid NULL;
    ALTER TABLE access_user_scope DROP CONSTRAINT uq_access_user_scope_role_assignment_id;
    ALTER TABLE access_user_scope
      ADD CONSTRAINT uq_access_user_scope_role_assignment_id_user_id
        UNIQUE (role_assignment_id, user_id),
      ADD CONSTRAINT fk_access_user_scope_team_member
        FOREIGN KEY (team_member_id, tenant_id)
        REFERENCES team_member (id, tenant_id) ON DELETE CASCADE;

    CREATE INDEX ix_access_user_scope_team_member_id ON access_user_scope (team_member_id);
    """)

    # The role_assignment trigger also expands a team assignment to the team's live members.
    op.execute("""
    CREATE OR REPLACE FUNCTION access_user_scope_sync() RETURNS trigger
      LANGUAGE plpgsql
      AS $$
      BEGIN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN
          DELETE FROM access_user_scope WHERE role_assignment_id = OLD.id;
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.deleted_at IS NULL THEN
          IF NEW.scope_type IN ('tenant', 'project') THEN
            INSERT INTO access_user_scope
              (id, tenant_id, user_id, scope_kind, project_id,
               role_assignment_id, valid_from, valid_to)
            VALUES
              (gen_random_uuid(), NEW.tenant_id, NEW.user_id, NEW.scope_type, NEW.project_id,
               NEW.id, NEW.valid_from, NEW.valid_to);
          ELSIF NEW.scope_type = 'team' THEN
            INSERT INTO access_user_scope
              (id, tenant_id, user_id, scope_kind, project_id,
               role_assignment_id, team_member_id, valid_from, valid_to)
            SELECT gen_random_uuid(), NEW.tenant_id, tm.user_id,
                   CASE WHEN t.project_id IS NULL THEN 'tenant' ELSE 'project' END,
                   t.project_id, NEW.id, tm.id, NEW.valid_from, NEW.valid_to
            FROM team t
            JOIN team_member tm ON tm.team_id = t.id AND tm.deleted_at IS NULL
            WHERE t.id = NEW.team_id AND t.tenant_id = NEW.tenant_id AND t.deleted_at IS NULL;
          END IF;
        END IF;
        RETURN NULL;
      END
      $$;

    CREATE FUNCTION access_team_member_scope_sync() RETURNS trigger
      LANGUAGE plpgsql
      AS $$
      BEGIN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN
          DELETE FROM access_user_scope WHERE team_member_id = OLD.id;
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.deleted_at IS NULL THEN
          INSERT INTO access_user_scope
            (id, tenant_id, user_id, scope_kind, project_id,
             role_assignment_id, team_member_id, valid_from, valid_to)
          SELECT gen_random_uuid(), NEW.tenant_id, NEW.user_id,
                 CASE WHEN t.project_id IS NULL THEN 'tenant' ELSE 'project' END,
                 t.project_id, ra.id, NEW.id, ra.valid_from, ra.valid_to
          FROM team t
          JOIN role_assignment ra
            ON ra.team_id = t.id AND ra.scope_type = 'team' AND ra.deleted_at IS NULL
          WHERE t.id = NEW.team_id AND t.tenant_id = NEW.tenant_id AND t.deleted_at IS NULL;
        END IF;
        RETURN NULL;
      END
      $$;

    CREATE TRIGGER trg_access_team_member_scope_sync
      AFTER INSERT OR UPDATE OR DELETE ON team_member
      FOR EACH ROW EXECUTE FUNCTION access_team_member_scope_sync();
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
