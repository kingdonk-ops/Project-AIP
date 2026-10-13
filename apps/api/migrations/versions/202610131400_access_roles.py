"""access_roles

ACCESS-02: roles, their permissions and who holds them where. All three tables come from
``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with
the fail-closed NULLIF policy). Deletes are soft, so ``aip_app`` loses the template's DELETE grant.

- ``role``: ``code`` is unique per tenant among live rows. System roles (``is_system``) are seeded
  from the access matrix; ``customised_at`` is set when a tenant admin first edits one (ADR 0020)
  and cleared by a reset. A role is named by a term key or, for custom roles, a plain name.
- ``role_permission``: one live row per (role, permission). ``permission_code`` references the
  global catalogue, and ``(role_id, tenant_id)`` references ``role`` so a role can never hold a row
  of another tenant.
- ``role_assignment``: a user holds a role at tenant or project scope (team and asset subtree are
  reserved for ACCESS-04 and later). The scope CHECK ties ``project_id`` to the scope type. Every
  reference carries ``tenant_id``, so an assignment can never point across tenants. A user holds a
  role at most once per scope among live rows (``uq_role_assignment_live``).

``projects`` gains ``UNIQUE (id, tenant_id)`` as the target of the tenant-safe project reference.

Revision ID: 202610131400
Revises: 202610131300
Create Date: 2026-10-13 14:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610131400"
down_revision: str | None = "202610131300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="role",
            columns=(
                "code text NOT NULL, name_term_key text NULL, name text NULL, "
                "is_system boolean NOT NULL DEFAULT false, customised_at timestamptz NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE role
      ADD CONSTRAINT uq_role_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_role_code CHECK (code ~ '^[a-z][a-z0-9_]{1,62}$'),
      ADD CONSTRAINT ck_role_named CHECK (name_term_key IS NOT NULL OR name <> ''),
      ADD CONSTRAINT ck_role_customised_system CHECK (customised_at IS NULL OR is_system),
      ADD CONSTRAINT fk_role_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES tenants (id);

    CREATE UNIQUE INDEX uq_role_tenant_id_code ON role (tenant_id, code) WHERE deleted_at IS NULL;

    REVOKE DELETE ON role FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="role_permission",
            columns="role_id uuid NOT NULL, permission_code text NOT NULL",
        )
    )
    op.execute("""
    ALTER TABLE role_permission
      ADD CONSTRAINT fk_role_permission_role_id_tenant_id_role
        FOREIGN KEY (role_id, tenant_id) REFERENCES role (id, tenant_id),
      ADD CONSTRAINT fk_role_permission_permission_code_permission
        FOREIGN KEY (permission_code) REFERENCES permission (code);

    CREATE UNIQUE INDEX uq_role_permission_role_id_permission_code
      ON role_permission (role_id, permission_code) WHERE deleted_at IS NULL;

    REVOKE DELETE ON role_permission FROM aip_app;
    """)

    op.execute(
        "ALTER TABLE projects ADD CONSTRAINT uq_projects_id_tenant_id UNIQUE (id, tenant_id)"
    )

    op.execute(
        render_template(
            "tenant_table",
            table="role_assignment",
            columns=(
                "user_id uuid NOT NULL, role_id uuid NOT NULL, scope_type text NOT NULL, "
                "project_id uuid NULL, team_id uuid NULL, asset_path ltree NULL, "
                "source text NOT NULL, valid_from timestamptz NOT NULL DEFAULT now(), "
                "valid_to timestamptz NULL, approved_by uuid NULL, created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE role_assignment ALTER COLUMN source SET DEFAULT 'manual';
    ALTER TABLE role_assignment
      ADD CONSTRAINT ck_role_assignment_scope_type
        CHECK (scope_type IN ('tenant', 'project', 'team', 'asset_subtree')),
      ADD CONSTRAINT ck_role_assignment_scope CHECK (
        (scope_type = 'tenant' AND project_id IS NULL AND team_id IS NULL AND asset_path IS NULL)
        OR (scope_type = 'project' AND project_id IS NOT NULL AND team_id IS NULL
            AND asset_path IS NULL)
        OR (scope_type = 'team' AND team_id IS NOT NULL AND asset_path IS NULL)
        OR (scope_type = 'asset_subtree' AND asset_path IS NOT NULL AND team_id IS NULL)
      ),
      ADD CONSTRAINT ck_role_assignment_source CHECK (source IN ('manual', 'scim', 'delegation')),
      ADD CONSTRAINT ck_role_assignment_valid CHECK (valid_to IS NULL OR valid_to > valid_from),
      ADD CONSTRAINT fk_role_assignment_user_id_tenant_id_app_user
        FOREIGN KEY (user_id, tenant_id) REFERENCES app_user (id, tenant_id),
      ADD CONSTRAINT fk_role_assignment_role_id_tenant_id_role
        FOREIGN KEY (role_id, tenant_id) REFERENCES role (id, tenant_id),
      ADD CONSTRAINT fk_role_assignment_project_id_tenant_id_projects
        FOREIGN KEY (project_id, tenant_id) REFERENCES projects (id, tenant_id),
      ADD CONSTRAINT fk_role_assignment_approved_by_tenant_id_app_user
        FOREIGN KEY (approved_by, tenant_id) REFERENCES app_user (id, tenant_id),
      ADD CONSTRAINT fk_role_assignment_created_by_tenant_id_app_user
        FOREIGN KEY (created_by, tenant_id) REFERENCES app_user (id, tenant_id);

    CREATE INDEX ix_role_assignment_tenant_id_user_id ON role_assignment (tenant_id, user_id);
    CREATE INDEX ix_role_assignment_tenant_id_project_id ON role_assignment (tenant_id, project_id);
    -- One live assignment per user, role and scope (expired ones must be removed first).
    CREATE UNIQUE INDEX uq_role_assignment_live
      ON role_assignment (tenant_id, user_id, role_id, scope_type,
                          COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid))
      WHERE deleted_at IS NULL AND scope_type IN ('tenant', 'project');
    CREATE INDEX ix_role_assignment_tenant_id_role_id ON role_assignment (tenant_id, role_id);

    REVOKE DELETE ON role_assignment FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
